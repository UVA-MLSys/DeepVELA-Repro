"""Reads a run's human interventions and executions from the agent harness's session transcript
(Claude Code JSONL), not from the ledger the agent writes. The agent cannot skip or edit these
records, so effort is counted the same way for every arm (protocol.md, "Effort").

    python -m evaluation.transcript extract <workspace or session.jsonl> [--out <dir>]
    python -m evaluation.transcript label <interventions.jsonl> <labels.json> --labeled-by <model>

Subagent transcripts under `<session>/subagents/` are read with the main one. Each intervention is
written with `type: null`; the judge then writes
`labels.json`, `{"<index>": "<type>"}`, and `label` validates it and writes the types back. Slurm
job states come from `sacct`, because a submitted job fails after the submitting command exits 0.
The jobs are `sacct`'s too, not parsed from command output, which depends on how each script prints
them (`--parsable`, a wrapper's own echo): the user's jobs whose `WorkDir` is the workspace or below it.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import shlex
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from .schema import Execution, Intervention, InterventionType

# Text the harness or IDE injects into a user turn; what remains after removing it is the human's.
_INJECTED = re.compile(
    r"<(ide_opened_file|ide_selection|system-reminder|local-command-stdout|command-name|command-message)>.*?</\1>",
    re.S,
)
# A slash command's arguments are what the human typed after it, e.g. the task prompt after `/<skill>`.
_COMMAND_ARGS = re.compile(r"<command-args>(.*?)</command-args>", re.S)
_COMMAND_NAME = re.compile(r"<command-name>/([^<\s]+)</command-name>")
_INTERRUPTED = "[Request interrupted by user"
_EXIT_CODE = re.compile(r"^Exit code (\d+)")
_CONTEXT_CHARS = 2000


def _records(path: Path) -> list[dict[str, Any]]:
    out = []
    for line in path.read_text().splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _blocks(record: dict[str, Any]) -> list[dict[str, Any]]:
    content = (record.get("message") or {}).get("content")
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return [b for b in content or [] if isinstance(b, dict)]


def _result_text(block: dict[str, Any]) -> str:
    content = block.get("content")
    if isinstance(content, list):
        return "\n".join(c.get("text", "") for c in content if isinstance(c, dict))
    return str(content or "")


def _human_text(record: dict[str, Any]) -> str | None:
    if record.get("type") != "user" or record.get("isMeta"):
        return None
    # The harness records who produced the turn; a task notification or other system turn is not
    # human even though it is stored as a user message.
    if "origin" in record and (record["origin"] or {}).get("kind") != "human":
        return None
    texts = [b["text"] for b in _blocks(record) if b.get("type") == "text"]
    if not texts:
        return None
    text = _COMMAND_ARGS.sub(r"\1", _INJECTED.sub("", "\n".join(texts))).strip()
    return text or None


def slash_commands(sessions: list[Path], before: str | None = None) -> list[tuple[str, str]]:
    """(timestamp, name) for every `/<name>` command a human typed in the main sessions; a skill invoked
    this way is loaded by the harness, not by an agent tool call."""
    out = []
    for path in sessions:
        for rec in _records(path):
            if rec.get("type") != "user" or rec.get("isMeta") or (before and rec.get("timestamp", "") > before):
                continue
            for b in _blocks(rec):
                if b.get("type") == "text":
                    out += [(rec.get("timestamp", ""), m) for m in _COMMAND_NAME.findall(b["text"])]
    return sorted(out)


def _answer_text(record: dict[str, Any], asked: set[str]) -> str | None:
    """The human's answer to an `AskUserQuestion` call in `asked`: it reaches the agent as that call's
    tool result, not as a user text turn, so `_human_text` does not see it. Rendered as each question
    with its answer; a declined question keeps the harness's result text."""
    for b in _blocks(record):
        if b.get("type") == "tool_result" and b.get("tool_use_id") in asked:
            answers = (record.get("toolUseResult") or {}).get("answers") if isinstance(record.get("toolUseResult"), dict) else None
            if isinstance(answers, dict) and answers:
                return "\n".join(f"Q: {q}\nA: {a}" for q, a in answers.items())
            return _result_text(b).strip() or None
    return None


def _outcome(block: dict[str, Any], result: Any) -> tuple[str, int | None]:
    if isinstance(result, dict):
        if result.get("backgroundTaskId"):
            # The harness moved a long command to the background; it is still running, not failed.
            return "backgrounded", None
        if result.get("timedOutAfterMs"):
            return "timed_out", None
        if result.get("interrupted"):
            return "interrupted", None
    if not block.get("is_error"):
        return "ok", 0
    text = _result_text(block)
    if match := _EXIT_CODE.match(text):
        return "exit_nonzero", int(match.group(1))
    if text.startswith("<tool_use_error>"):
        return "tool_error", None
    return "harness_denied", None


def _utc(stamp: str) -> datetime:
    """A transcript timestamp (`...Z`) or a `sacct` time (local, no zone) as an aware UTC datetime."""
    return datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(timezone.utc)


def _run_jobs(workspace: Path, since: str) -> list[tuple[str, datetime, str]]:
    """(job ID, submit time, state) for the user's Slurm jobs submitted since `since` whose working
    directory is the workspace or below it, which keeps other runs' jobs out."""
    start = _utc(since).astimezone().strftime("%Y-%m-%dT%H:%M:%S")
    try:
        out = subprocess.run(
            ["sacct", "-X", "-P", "-n", "-u", getpass.getuser(), "-S", start, "--format=JobID,Submit,State,WorkDir"],
            capture_output=True, text=True, check=True, timeout=120,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    root, jobs = workspace.resolve(), []
    for line in out.splitlines():
        job, submit, state, workdir = (line.split("|") + ["", "", "", ""])[:4]
        if not (job and state and workdir) or submit in ("", "Unknown"):
            continue
        directory = Path(workdir).resolve()
        if directory == root or root in directory.parents:
            jobs.append((job, _utc(submit), state.split()[0]))
    return jobs


def find_sessions(workspace: Path) -> list[Path]:
    """The main session files Claude Code wrote for a workspace, in the VS Code extension or the
    CLI: `<config>/projects/<workspace path with every non-alphanumeric character as '-'>/*.jsonl`.
    A resumed or restarted session adds another file to the same directory."""
    projects = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude")) / "projects"
    for path in dict.fromkeys((workspace, workspace.resolve())):
        directory = projects / re.sub(r"[^A-Za-z0-9]", "-", str(path))
        if directory.is_dir():
            return sorted(directory.glob("*.jsonl"))
    return []


def extract(sessions: list[Path], workspace: Path | None = None) -> tuple[list[Intervention], list[Execution]]:
    """Interventions from the main sessions (the human talks to the main agent); executions from
    the main sessions and their subagents. Records are merged by `uuid`, so a resumed session that
    repeats earlier history is counted once, and ordered by timestamp. With `workspace`, each Slurm
    job of the run (`_run_jobs`) goes to the latest command that was running when it was submitted,
    a backgrounded or timed-out command counting as running until the session's end; a job submitted
    while no command ran, by a process a finished command left behind, goes to the latest command
    started before it."""
    files = [p for s in sessions for p in (s, *sorted((s.with_suffix("") / "subagents").glob("*.jsonl")))]
    merged: dict[str, dict[str, Any]] = {}
    for path in files:
        for rec in _records(path):
            rec["_main"] = path in sessions and not rec.get("isSidechain")
            rec["_source"] = path.name
            merged.setdefault(rec.get("uuid") or f"{path.name}:{len(merged)}", rec)
    records = sorted(merged.values(), key=lambda r: r.get("timestamp", ""))

    interventions: list[Intervention] = []
    executions: list[Execution] = []
    calls: dict[str, tuple[str, str, str]] = {}
    asked: set[str] = set()
    finished: list[str | None] = []  # each execution's result time; None while it may still be running
    last_agent_text = ""
    launched = False
    pending: Intervention | None = None
    for rec in records:
        if rec.get("type") == "assistant":
            for b in _blocks(rec):
                if b.get("type") == "text" and b.get("text", "").strip() and rec["_main"]:
                    last_agent_text = b["text"]
                    if pending is not None and pending.agent_after is None:
                        pending.agent_after = b["text"][:_CONTEXT_CHARS]
                if b.get("type") == "tool_use" and b.get("name") == "Bash":
                    calls[b["id"]] = (rec["_source"], rec.get("timestamp", ""), str((b.get("input") or {}).get("command", "")))
                if b.get("type") == "tool_use" and b.get("name") == "AskUserQuestion" and rec["_main"]:
                    asked.add(b["id"])
            continue
        for b in _blocks(rec):
            if b.get("type") == "tool_result" and b.get("tool_use_id") in calls:
                source, timestamp, command = calls.pop(b["tool_use_id"])
                outcome, exit_code = _outcome(b, rec.get("toolUseResult"))
                text = _result_text(b)
                executions.append(Execution(
                    source=source, timestamp=timestamp, command=command, outcome=outcome,
                    exit_code=exit_code, output=text,
                ))
                finished.append(None if outcome in ("backgrounded", "timed_out") else rec.get("timestamp", ""))
        answer = _answer_text(rec, asked) if rec["_main"] else None
        text = answer or (_human_text(rec) if rec["_main"] else None)
        if text is None:
            continue
        if not launched and answer is None:
            launched = True  # the first human message is the task prompt, not an intervention
            continue
        pending = Intervention(
            index=len(interventions), timestamp=rec.get("timestamp", ""), text=text,
            interrupted=text.startswith(_INTERRUPTED), agent_before=last_agent_text[-_CONTEXT_CHARS:],
        )
        interventions.append(pending)
    if workspace is not None and executions:
        # `sacct` records whole seconds, so each span is widened to the seconds it touches.
        spans = [(_utc(e.timestamp).replace(microsecond=0), _utc(end).replace(microsecond=0) + timedelta(seconds=1) if end else None)
                 for e, end in zip(executions, finished)]
        for job, submitted, state in _run_jobs(workspace, executions[0].timestamp):
            running = [i for i, (start, end) in enumerate(spans) if start <= submitted and (end is None or submitted <= end)]
            before = [i for i, (start, _) in enumerate(spans) if start <= submitted]
            if owner := (running or before):
                e = executions[max(owner, key=lambda i: spans[i][0])]
                e.job_ids.append(job)
                e.job_states[job] = state
    return interventions, executions


def models(sessions: list[Path]) -> list[str]:
    """The model IDs the harness recorded on the main sessions' responses, so the scored model is
    what ran, not what the launch record declared."""
    seen: dict[str, None] = {}
    for path in sessions:
        for rec in _records(path):
            model = (rec.get("message") or {}).get("model") if rec.get("type") == "assistant" else None
            if model and not model.startswith("<"):
                seen.setdefault(model, None)
    return list(seen)


def accesses(sessions: list[Path], before: str | None = None) -> list[tuple[str, str, str]]:
    """(timestamp, tool, target) for every tool call the agent made, main sessions and subagents: the
    whole call input as JSON, so a path, URL, query, or command is all searchable by the monitor."""
    files = [p for s in sessions for p in (s, *sorted((s.with_suffix("") / "subagents").glob("*.jsonl")))]
    seen: set[str] = set()
    out: list[tuple[str, str, str]] = []
    for path in files:
        for rec in _records(path):
            if rec.get("type") != "assistant" or (before and rec.get("timestamp", "") > before):
                continue
            for b in _blocks(rec):
                if b.get("type") == "tool_use" and b.get("id") not in seen:
                    seen.add(b["id"])
                    out.append((rec.get("timestamp", ""), str(b.get("name")), json.dumps(b.get("input") or {})))
    return sorted(out)


# A response spent waiting on work already started: every tool call it makes only watches (a
# `Monitor`, or a Bash command that sleeps or queries the scheduler and otherwise only filters or
# prints), or it makes none and
# answers a background-task notification. Its cost scales with queue time and cluster load, which
# another run's activity changes, so arms are compared on the rest (SKILL.md, "Launch").
_WATCH_TOOLS = {"Monitor", "ToolSearch"}
_WAIT_COMMANDS = {"sleep", "squeue", "sacct", "wait"}
# Commands that only read state, and shell keywords; a poll may use them around a wait command.
_POLL_COMMANDS = _WAIT_COMMANDS | {"tail", "head", "cat", "ls", "grep", "awk", "cut", "sort", "uniq", "wc", "date",
                                   "echo", "printf", "cd", "test", "[", "[[", "pgrep", "ps", "nvidia-smi",
                                   "until", "while", "do", "done", "if", "then", "else", "fi", "!", "true", "false",
                                   "break", "exit"}
_ASSIGNMENT = re.compile(r"^\w+=")
_NOTIFICATION = "<task-notification>"


def _heads(command: str) -> list[str] | None:
    """The command words of a shell command line, None when it does not tokenize. `timeout` and
    `bash -c` wrap a command, so the wrapped command's words are returned instead of theirs."""
    heads, words = [], []
    try:
        tokens = [t for line in command.splitlines() for t in [*shlex.shlex(line, posix=True, punctuation_chars=True), ";"]]
    except ValueError:
        return None
    redirect = False
    for token in tokens:
        if redirect or (token and set(token) <= set("<>&") and set(token) & set("<>")):
            # A redirection operator and its target are part of the command, not a new one.
            redirect = not redirect and not token[-1].isalnum()
            continue
        if not (token and set(token) <= set(";|&()")):
            words.append(token)
            continue
        words = [w for w in words if not _ASSIGNMENT.match(w)]
        # A loop keyword or `!` precedes the command it governs.
        while words and words[0] in {"until", "while", "do", "if", "then", "else", "!"}:
            heads.append(words.pop(0))
        if words[:1] == ["timeout"]:
            words = words[1:]
            while words and (words[0].startswith("-") or words[0][:1].isdigit()):
                words = words[1:]
        if words[:2] in (["bash", "-c"], ["sh", "-c"]) and len(words) > 2:
            inner = _heads(words[2])
            if inner is None:
                return None
            heads += inner
        else:
            heads += words[:1]
        words = []
    return heads


def _polls(command: str) -> bool:
    heads = _heads(command)
    return heads is not None and bool(_WAIT_COMMANDS & set(heads)) and set(heads) <= _POLL_COMMANDS


def _waits(blocks: list[dict[str, Any]], trigger: list[dict[str, Any]], watching: set[str]) -> bool:
    """`trigger` is the user record's blocks the response answers; `watching` holds the ids of tool
    calls already classified as waiting."""
    calls = [b for b in blocks if b.get("type") == "tool_use"]
    if not calls:
        results = [b.get("tool_use_id") for b in trigger if b.get("type") == "tool_result"]
        if results:
            return all(r in watching for r in results)
        return any(b.get("type") == "text" and b.get("text", "").lstrip().startswith(_NOTIFICATION) for b in trigger)
    return all(c.get("name") in _WATCH_TOOLS
               or (c.get("name") == "Bash" and _polls(str((c.get("input") or {}).get("command", ""))))
               for c in calls)


def usage(sessions: list[Path], before: str | None = None) -> dict[str, int] | None:
    """Token usage the harness recorded on assistant responses, main sessions and subagents alike. A
    response is split over several records that repeat one `message.id`, so each id counts once.
    Totals cover every response; `wait_*` keys repeat them for the responses `_waits` classifies, and `tool_calls` counts the tool calls.
    `peak_context` is the largest prompt (input plus cache tokens) of any response; `wall_seconds` runs from the
    first to the last record of the main sessions. None when no response carries usage. `before` (ISO
    timestamp) leaves out later responses."""
    files = [p for s in sessions for p in (s, *sorted((s.with_suffix("") / "subagents").glob("*.jsonl")))]
    keys = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
    responses: dict[str, tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]] = {}
    stamps = sorted(r["timestamp"] for s in sessions for r in _records(s)
                    if r.get("timestamp") and not (before and r["timestamp"] > before))
    for path in files:
        trigger: list[dict[str, Any]] = []
        for rec in _records(path):
            if rec.get("type") == "user":
                trigger = _blocks(rec)
                continue
            message = rec.get("message") or {}
            if rec.get("type") != "assistant" or not message.get("usage") or (before and rec.get("timestamp", "") > before):
                continue
            # The records of one response share its usage and trigger and split its content blocks.
            _, blocks, first_trigger = responses.get(message.get("id"), (None, [], trigger))
            responses[message.get("id")] = (message["usage"], blocks + _blocks(rec), first_trigger)
    if not responses:
        return None
    totals = {k: 0 for k in keys} | {f"wait_{k}": 0 for k in keys} | {"responses": len(responses), "wait_responses": 0,
                                                                                 "tool_calls": 0, "wait_tool_calls": 0}
    totals["peak_context"] = 0
    if stamps:
        first, last = (datetime.fromisoformat(stamps[i].replace("Z", "+00:00")) for i in (0, -1))
        totals["wall_seconds"] = int((last - first).total_seconds())
    watching: set[str] = set()
    for recorded, blocks, trigger in responses.values():
        totals["peak_context"] = max(totals["peak_context"], sum(recorded.get(k) or 0 for k in
                                     ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")))
        waiting = _waits(blocks, trigger, watching)
        if waiting:
            watching |= {b.get("id") for b in blocks if b.get("type") == "tool_use"}
        calls = sum(b.get("type") == "tool_use" for b in blocks)
        totals["wait_responses"] += waiting
        totals["tool_calls"] += calls
        totals["wait_tool_calls"] += calls * waiting
        for key in keys:
            totals[key] += recorded.get(key) or 0
            if waiting:
                totals[f"wait_{key}"] += recorded.get(key) or 0
    return totals


# Codex sessions (rollout JSONL). Codex saves a session under `$CODEX_HOME/sessions/`, and
# `evaluation.prepare` gives each run its own CODEX_HOME (protocol.md, "The operator's configuration
# stays out of every run"), so a run's session is found there.

def _codex_cwd(path: Path) -> str | None:
    with path.open() as handle:
        first = json.loads(handle.readline() or "{}")
    return (first.get("payload") or {}).get("cwd") if first.get("type") == "session_meta" else None


def find_codex_sessions(codex_home: Path, workspace: Path) -> list[Path]:
    """The Codex sessions under `codex_home` that started in `workspace`."""
    roots = {str(workspace), str(workspace.resolve())}
    return sorted(p for p in (codex_home / "sessions").rglob("rollout-*.jsonl") if _codex_cwd(p) in roots)


def _codex_items(sessions: list[Path], before: str | None = None) -> list[tuple[str, dict[str, Any]]]:
    out = []
    for path in sessions:
        for rec in _records(path):
            payload = rec.get("payload") or {}
            if payload.get("type") == "item_completed" and not (before and rec.get("timestamp", "") > before):
                out.append((rec.get("timestamp", ""), payload.get("item") or {}))
    return sorted(out, key=lambda pair: pair[0])


def codex_extract(sessions: list[Path], before: str | None = None) -> tuple[list[Intervention], list[Execution]]:
    """Interventions (every user message after the task prompt) and executions (every shell command
    with its exit code), as `extract` gives them for Claude Code."""
    interventions: list[Intervention] = []
    executions: list[Execution] = []
    last_agent_text, launched = "", False
    for timestamp, item in _codex_items(sessions, before):
        kind = item.get("type")
        text = "".join(c.get("text", "") for c in item.get("content") or [] if isinstance(c, dict))
        if kind == "AgentMessage" and text.strip():
            last_agent_text = text
        elif kind == "UserMessage":
            if launched:
                interventions.append(Intervention(index=len(interventions), timestamp=timestamp, text=text,
                                                  interrupted=False, agent_before=last_agent_text[-_CONTEXT_CHARS:]))
            launched = True
        elif kind == "CommandExecution":
            command = item.get("command")
            code = item.get("exit_code")
            outcome = ("ok" if code == 0 else "exit_nonzero" if code is not None
                       else "ok" if item.get("status") == "completed" else "tool_error")
            executions.append(Execution(
                source="codex", timestamp=timestamp, outcome=outcome, exit_code=code,
                command=command[-1] if isinstance(command, list) and command else str(command or ""),
                output=item.get("aggregated_output") or "",
            ))
    return interventions, executions


def agent_messages(sessions: list[Path], harness: str, before: str | None = None) -> list[tuple[str, str]]:
    """(timestamp, text) of every message the agent wrote, up to `before`: where the skill tells an
    autonomous agent to state a change before applying it, so a claim about what the run states needs them."""
    if harness == "codex":
        return [(ts, text) for ts, item in _codex_items(sessions, before) if item.get("type") == "AgentMessage"
                and (text := "".join(c.get("text", "") for c in item.get("content") or [] if isinstance(c, dict))).strip()]
    out = []
    for path in sessions:
        for rec in _records(path):
            if rec.get("type") != "assistant" or (before and rec.get("timestamp", "") > before):
                continue
            text = "\n".join(b.get("text", "") for b in _blocks(rec) if b.get("type") == "text")
            if text.strip():
                out.append((rec.get("timestamp", ""), text))
    return sorted(out, key=lambda pair: pair[0])


def codex_accesses(sessions: list[Path], before: str | None = None) -> list[tuple[str, str, str]]:
    """(timestamp, tool, target) for every tool call, the target being the call's whole input."""
    out = []
    for path in sessions:
        for rec in _records(path):
            payload = rec.get("payload") or {}
            if rec.get("type") == "response_item" and payload.get("type") in ("custom_tool_call", "function_call") \
                    and not (before and rec.get("timestamp", "") > before):
                target = payload.get("input") or payload.get("arguments") or ""
                out.append((rec.get("timestamp", ""), payload.get("name", ""), target if isinstance(target, str) else json.dumps(target)))
    return out


def codex_models(sessions: list[Path]) -> list[str]:
    seen: dict[str, None] = {}
    for path in sessions:
        for rec in _records(path):
            if rec.get("type") == "turn_context" and (model := (rec.get("payload") or {}).get("model")):
                seen.setdefault(model, None)
    return list(seen)


def codex_usage(sessions: list[Path], before: str | None = None) -> dict[str, int] | None:
    """Token totals from each session's last cumulative `token_count`, the tool calls, and `wall_seconds`
    from the first to the last record."""
    totals = {"input_tokens": 0, "cache_read_input_tokens": 0, "output_tokens": 0, "tool_calls": 0}
    stamps: list[str] = []
    measured = False
    for path in sessions:
        last = None
        for rec in _records(path):
            stamp = rec.get("timestamp", "")
            if before and stamp > before:
                continue
            stamps.append(stamp)
            payload = rec.get("payload") or {}
            if payload.get("type") == "token_count" and (payload.get("info") or {}).get("total_token_usage"):
                last = payload["info"]["total_token_usage"]
            if rec.get("type") == "response_item" and payload.get("type") in ("custom_tool_call", "function_call"):
                totals["tool_calls"] += 1
        if last:
            measured = True
            # Codex counts cached tokens inside input_tokens; Claude Code keys keep them apart.
            totals["input_tokens"] += (last.get("input_tokens") or 0) - (last.get("cached_input_tokens") or 0)
            totals["cache_read_input_tokens"] += last.get("cached_input_tokens") or 0
            totals["output_tokens"] += last.get("output_tokens") or 0
    if not measured:
        return None
    stamps = sorted(s for s in stamps if s)
    if stamps:
        totals["wall_seconds"] = int((_utc(stamps[-1]) - _utc(stamps[0])).total_seconds())
    return totals


def write(interventions: list[Intervention], executions: list[Execution], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = out_dir / "interventions.jsonl", out_dir / "executions.jsonl"
    for path, rows in zip(paths, (interventions, executions)):
        path.write_text("".join(r.model_dump_json() + "\n" for r in rows))
    return paths


def read_interventions(path: Path) -> list[Intervention]:
    return [Intervention.model_validate_json(line) for line in path.read_text().splitlines() if line.strip()]


def carry_labels(interventions: list[Intervention], previous: Path) -> None:
    """Keep the judge's labels when the same transcript is extracted again: a label stays with the
    message it was given for, matched by index, timestamp, and text."""
    if not previous.exists():
        return
    old = {(i.index, i.timestamp, i.text): i for i in read_interventions(previous)}
    for i in interventions:
        if (match := old.get((i.index, i.timestamp, i.text))) is not None:
            i.type, i.labeled_by = match.type, match.labeled_by


def apply_labels(path: Path, labels: dict[str, str], labeled_by: str) -> list[Intervention]:
    """Every intervention must receive exactly one type from `InterventionType`; anything else is
    rejected before the file is touched."""
    interventions = read_interventions(path)
    indices = {str(i.index) for i in interventions}
    if set(labels) != indices:
        raise SystemExit(f"labels cover {sorted(labels)}, interventions are {sorted(indices)}")
    check = TypeAdapter(InterventionType)
    for i in interventions:
        i.type, i.labeled_by = check.validate_python(labels[str(i.index)]), labeled_by
    path.write_text("".join(i.model_dump_json() + "\n" for i in interventions))
    return interventions


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    ex = sub.add_parser("extract")
    ex.add_argument("source", type=Path, help="the arm's workspace, or one session file")
    ex.add_argument("--out", type=Path, help="write interventions.jsonl and executions.jsonl here")
    lb = sub.add_parser("label")
    lb.add_argument("interventions", type=Path)
    lb.add_argument("labels", type=Path)
    lb.add_argument("--labeled-by", required=True)
    args = parser.parse_args()
    if args.command == "label":
        labeled = apply_labels(args.interventions, json.loads(args.labels.read_text()), args.labeled_by)
        for i in labeled:
            print(f"  {i.index:3} {i.type:14} {i.text[:80]!r}")
        return
    sessions = [args.source] if args.source.suffix == ".jsonl" else find_sessions(args.source)
    interventions, executions = extract(sessions, None if args.source.suffix == ".jsonl" else args.source)
    failed = [e for e in executions if e.failed]
    print(f"interventions {len(interventions)}  executions {len(executions)}  failed {len(failed)}")
    for i in interventions:
        print(f"  {i.timestamp[:16]}  {i.text[:100]!r}")
    for e in failed:
        print(f"  failed {e.outcome:14} {e.job_states or ''} {e.command[:80]!r}")
    if args.out:
        carry_labels(interventions, args.out / "interventions.jsonl")
        for path in write(interventions, executions, args.out):
            print(f"wrote {path}")


if __name__ == "__main__":
    main()

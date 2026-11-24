"""Built-in checker kinds a `PhaseRubric.checker` can name (`{kind: "builtin.<name>", args: {...}}`).

Each checker is read-only against a `RunSnapshot` and returns a `CheckResult`. Nothing here may
hardcode a phase ID, rubric ID, or domain metric name; every domain fact a checker needs (a path, a
pattern, a reference value) comes from the rubric's own `checker.args` or the task manifest.

Checkers read only evidence every arm produces the same way (protocol.md, "Scores"): the files in
the arm's workspace, the command outputs in the harness transcript, and `report.json`, which the
fixed task prompt asks every arm to write with the values the evaluator printed. A record that one
arm's skill asks the agent to keep, such as `effect_ledger.jsonl`, is never evidence: the other arms
do not write it, and the agent can leave anything out of it.
"""

from __future__ import annotations

import functools
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import warnings
from dataclasses import replace, dataclass, field
from pathlib import Path
from typing import Any, Iterator

import joblib

from .schema import CheckResult, EvaluationTask, Execution, PhaseRubric

CHECKER_VERSION = "4"
# Workspace files larger than this are not searched for landmarks (datasets, checkpoints).
_MAX_TEXT_BYTES = 50_000_000


@functools.lru_cache(maxsize=8)
def _workspace_index(workspace: Path) -> tuple[str, ...]:
    """Relative paths of every file under `workspace`, from one directory walk (no per-entry stat). A
    workspace holds environments and preprocessed caches of hundreds of thousands of files, so a glob per
    rubric walked and stat-ed all of them each time. Not followed: symlinked directories."""
    return tuple(sorted(os.path.relpath(os.path.join(root, f), workspace) for root, _, files in os.walk(workspace) for f in files))


@functools.lru_cache(maxsize=256)
def _glob_regex(pattern: str) -> re.Pattern[str]:
    """`Path.glob` semantics for files: `**/` matches any directories (or none), `*` and `?` stay in one path segment."""
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?"); i += 3
        elif pattern.startswith("**", i):
            out.append(".*"); i += 2
        elif pattern[i] == "*":
            out.append("[^/]*"); i += 1
        elif pattern[i] == "?":
            out.append("[^/]"); i += 1
        else:
            out.append(re.escape(pattern[i])); i += 1
    return re.compile("".join(out) + r"\Z")


def workspace_glob(workspace: Path, pattern: str) -> list[Path]:
    """Files under `workspace` matching `pattern`, sorted. Replaces `workspace.glob(pattern)`, which walks the whole tree on every call."""
    regex = _glob_regex(pattern)
    return [workspace / rel for rel in _workspace_index(workspace) if regex.match(rel)]


@dataclass
class RunSnapshot:
    """Read-only view of one arm's run: its workspace, the executions from its transcript, and its
    `report.json`. Nothing here is mutated after construction."""

    run_path: str
    workspace: Path
    executions: list[Execution] = field(default_factory=list)
    messages: list[tuple[str, str]] = field(default_factory=list)  # (timestamp, text) the agent wrote
    report: dict[str, Any] | None = None
    report_error: str | None = None

    @property
    def repo_root(self) -> Path:
        return self.workspace / "repo"

    def texts(self, files: list[str], *, include_executions: bool = True) -> Iterator[tuple[str, str]]:
        """(label, text) for selected workspace files, optionally preceded by command outputs."""
        if include_executions:
            for i, e in enumerate(self.executions):
                yield f"executions.jsonl:{i + 1} ({e.command[:60]!r})", e.output
        seen: set[Path] = set()
        for pattern in files:
            for path in workspace_glob(self.workspace, pattern):
                if path in seen or not path.is_file() or ".claude" in path.relative_to(self.workspace).parts:
                    continue
                seen.add(path)
                if path.stat().st_size <= _MAX_TEXT_BYTES:
                    yield str(path.relative_to(self.workspace)), path.read_text(errors="replace")


def _metric_name(args: dict[str, Any], task: EvaluationTask) -> str:
    """The metric the rubric binds: `args.metric_name`, else the quality contract's name."""
    if args.get("metric_name"):
        return args["metric_name"]
    if task.quality_contract is None:
        raise ValueError("a multi-target rubric must name its metric in checker.args.metric_name")
    return task.quality_contract.result_name_type_and_direction.split(",")[0].strip()


def _reported(snapshot: RunSnapshot, name: str) -> tuple[Any, float | None, str | None]:
    """(value as written, value as a number, failure reason) for one metric in `report.json`.
    Fails closed when the report is missing, is not JSON, or names the metric differently."""
    if snapshot.report is None:
        return None, None, snapshot.report_error or "report.json is missing from the workspace"
    if name not in snapshot.report:
        return None, None, f"report.json records {sorted(snapshot.report)}, not {name!r}"
    raw = snapshot.report[name]
    try:
        return raw, float(str(raw).strip().rstrip("%")), None
    except ValueError:
        return raw, None, f"report.json value for {name!r} is {raw!r}, not a number"


def _resolve_manifest_path(task: EvaluationTask, snapshot: RunSnapshot, path_from: str) -> Path | None:
    """`manifest.inputs.<name>` / `manifest.outputs.<name>` -> `task.artifact_paths[<name>]`: an
    absolute path (an input read from the cache) or a path relative to the workspace's `repo/`."""
    match = re.fullmatch(r"manifest\.(?:inputs|outputs)\.([A-Za-z0-9_]+)", path_from)
    if match is None:
        return None
    relative = task.artifact_paths.get(match.group(1))
    if relative is None:
        return None
    return Path(relative) if Path(relative).is_absolute() else snapshot.repo_root / relative


def _resolve_reference(snapshot: RunSnapshot, reference_from: str) -> Path:
    """A relative `reference_from` names a file in the benchmark's own pinned source tree, which the
    workspace holds under `repo/`."""
    reference_path = Path(reference_from)
    return reference_path if reference_path.is_absolute() else snapshot.repo_root / reference_from


def _result(rubric: PhaseRubric, *, verdict: str, reason: str, evidence_refs: list[str] | None = None) -> CheckResult:
    return CheckResult(
        rubric_id=rubric.rubric_id,
        verdict=verdict,  # type: ignore[arg-type]
        score=1.0 if verdict == "pass" else 0.0,
        evidence_refs=evidence_refs or [],
        reason=reason,
        checker_id=rubric.checker.get("kind", "unknown"),
        checker_version=CHECKER_VERSION,
    )


def check_landmark(rubric: PhaseRubric, args: dict[str, Any], snapshot: RunSnapshot, task: EvaluationTask) -> CheckResult:
    """A landmark (SUPER, section 3.1.2): an output pattern, taken from the benchmark's own tools,
    that shows a step ran -- for example the evaluator's summary line or LoadGen's mode line. It
    passes when the pattern appears in any command output in the transcript or in a workspace file
    matching `args.files`. Runs of spaces and tabs in the output count as one space: a landmark names
    content, and the layout between a log line's tokens (`print("a: ", x)` against `print(f"a: {x}")`)
    is not part of what the task prompt requires."""
    pattern = args.get("pattern")
    if not pattern:
        return _result(rubric, verdict="not_applicable", reason="checker.args is missing 'pattern' -- rubric defect, not a run defect")
    compiled = re.compile(pattern)
    for label, text in snapshot.texts(args.get("files", [])):
        if (match := compiled.search(re.sub(r"[ \t]+", " ", text))) is not None:
            return _result(rubric, verdict="pass", reason=f"{pattern!r} found in {label}: {match.group(0)[:120]!r}", evidence_refs=[label])
    return _result(rubric, verdict="fail", reason=f"{pattern!r} appears in no command output and no workspace file matching {args.get('files', [])}")


def check_artifact_exists(rubric: PhaseRubric, args: dict[str, Any], snapshot: RunSnapshot, task: EvaluationTask) -> CheckResult:
    """`args.path`: a glob relative to the workspace; `args.path_from`: a task manifest path."""
    if literal := args.get("path"):
        found = sorted(p for p in workspace_glob(snapshot.workspace, literal) if ".claude" not in p.relative_to(snapshot.workspace).parts)
        if found:
            return _result(rubric, verdict="pass", reason=f"{found[0]} exists", evidence_refs=[str(p) for p in found[:5]])
        return _result(rubric, verdict="fail", reason=f"nothing in the workspace matches {literal!r}")
    path_from = args.get("path_from")
    if path_from is None:
        return _result(rubric, verdict="not_applicable", reason="checker.args has neither 'path' nor 'path_from'")
    resolved = _resolve_manifest_path(task, snapshot, path_from)
    if resolved is None:
        return _result(
            rubric, verdict="not_applicable",
            reason=f"path_from {path_from!r} has no artifact_paths entry in this task's manifest -- rubric/manifest defect, not a run defect",
        )
    if resolved.exists():
        return _result(rubric, verdict="pass", reason=f"{resolved} exists", evidence_refs=[str(resolved)])
    return _result(rubric, verdict="fail", reason=f"{resolved} does not exist")


def check_artifact_hash_matches(rubric: PhaseRubric, args: dict[str, Any], snapshot: RunSnapshot, task: EvaluationTask) -> CheckResult:
    algorithm = args.get("algorithm", "md5")
    reference_from = args.get("reference_from")
    path_from = args.get("path_from")
    if not reference_from or not path_from:
        return _result(rubric, verdict="not_applicable", reason="checker.args is missing 'reference_from' or 'path_from'")

    reference_path = _resolve_reference(snapshot, reference_from)
    if not reference_path.is_file():
        return _result(rubric, verdict="fail", reason=f"reference checksum file {reference_path} does not exist")
    try:
        reference = json.loads(reference_path.read_text())
    except json.JSONDecodeError as exc:
        return _result(rubric, verdict="fail", reason=f"{reference_path} is not valid JSON: {exc}")

    target_dir = _resolve_manifest_path(task, snapshot, path_from) if path_from.startswith("manifest.") else snapshot.repo_root / path_from
    if target_dir is None:
        return _result(
            rubric, verdict="not_applicable",
            reason=f"path_from {path_from!r} has no artifact_paths entry in this task's manifest -- rubric/manifest defect, not a run defect",
        )
    if not target_dir.is_dir():
        return _result(rubric, verdict="fail", reason=f"{target_dir} does not exist or is not a directory")

    mismatched: list[str] = []
    missing: list[str] = []
    for filename, expected_hash in reference.items():
        candidate = target_dir / filename
        if not candidate.is_file():
            missing.append(filename)
            continue
        digest = hashlib.new(algorithm, candidate.read_bytes()).hexdigest()
        if digest != expected_hash:
            mismatched.append(filename)

    if missing or mismatched:
        return _result(
            rubric, verdict="fail",
            reason=f"{len(missing)} file(s) missing, {len(mismatched)} file(s) hash-mismatched under {target_dir} "
                   f"against {reference_path} (of {len(reference)} expected)",
        )
    return _result(
        rubric, verdict="pass",
        reason=f"all {len(reference)} files under {target_dir} match {reference_path} ({algorithm})",
        evidence_refs=[str(target_dir)],
    )


def check_file_hash_equals(rubric: PhaseRubric, args: dict[str, Any], snapshot: RunSnapshot, task: EvaluationTask) -> CheckResult:
    """Single-file identity: `expected_sha256` given directly in `checker.args`, rather than read
    from a reference checksum file in the benchmark's own source tree (that's
    `builtin.artifact_hash_matches`, for a whole directory of files against a JSON manifest like
    KiTS19's `meta/checksum_inference.json`)."""
    algorithm = args.get("algorithm", "sha256")
    path_from = args.get("path_from")
    expected_hash = args.get("expected_sha256")
    if not path_from or not expected_hash:
        return _result(rubric, verdict="not_applicable", reason="checker.args is missing 'path_from' or 'expected_sha256'")

    target = _resolve_manifest_path(task, snapshot, path_from) if path_from.startswith("manifest.") else snapshot.repo_root / path_from
    if target is None:
        return _result(
            rubric, verdict="not_applicable",
            reason=f"path_from {path_from!r} has no artifact_paths entry in this task's manifest -- rubric/manifest defect, not a run defect",
        )
    if not target.is_file():
        return _result(rubric, verdict="fail", reason=f"{target} does not exist or is not a file")
    digest = hashlib.new(algorithm, target.read_bytes()).hexdigest()
    if digest == expected_hash:
        return _result(rubric, verdict="pass", reason=f"{target} matches expected {algorithm} {expected_hash}", evidence_refs=[str(target)])
    return _result(rubric, verdict="fail", reason=f"{target} {algorithm} is {digest}, expected {expected_hash}")


def check_directory_entry_count(rubric: PhaseRubric, args: dict[str, Any], snapshot: RunSnapshot, task: EvaluationTask) -> CheckResult:
    expected = args.get("expected")
    pattern = args.get("pattern", "*")
    path_from = args.get("path_from")
    if path_from is None or expected is None:
        return _result(rubric, verdict="not_applicable", reason="checker.args is missing 'path_from' or 'expected'")

    target_dir = _resolve_manifest_path(task, snapshot, path_from)
    if target_dir is None:
        return _result(
            rubric, verdict="not_applicable",
            reason=f"path_from {path_from!r} has no artifact_paths entry in this task's manifest -- rubric/manifest defect, not a run defect",
        )
    if not target_dir.is_dir():
        return _result(rubric, verdict="fail", reason=f"{target_dir} does not exist or is not a directory")

    actual = len(list(target_dir.glob(pattern)))
    if actual == expected:
        return _result(rubric, verdict="pass", reason=f"{target_dir} has {actual} entries matching {pattern!r} (expected {expected})", evidence_refs=[str(target_dir)])
    return _result(rubric, verdict="fail", reason=f"{target_dir} has {actual} entries matching {pattern!r}, expected {expected}")


def check_directory_contains_all(rubric: PhaseRubric, args: dict[str, Any], snapshot: RunSnapshot, task: EvaluationTask) -> CheckResult:
    """Does the directory contain every documented entry, permitting extras? Distinct from
    `builtin.directory_entry_count`, which requires an exact count and so rejects a legitimate
    superset. `reference_from` is a JSON file holding a flat list of required names (e.g.
    KiTS19's `meta/inference_cases.json`)."""
    reference_from = args.get("reference_from")
    path_from = args.get("path_from")
    if not reference_from or not path_from:
        return _result(rubric, verdict="not_applicable", reason="checker.args is missing 'reference_from' or 'path_from'")

    reference_path = _resolve_reference(snapshot, reference_from)
    if not reference_path.is_file():
        return _result(rubric, verdict="fail", reason=f"reference file {reference_path} does not exist")
    try:
        required = json.loads(reference_path.read_text())
    except json.JSONDecodeError as exc:
        return _result(rubric, verdict="fail", reason=f"{reference_path} is not valid JSON: {exc}")
    if not isinstance(required, list):
        return _result(rubric, verdict="fail", reason=f"{reference_path} is not a JSON list of required names")

    target_dir = _resolve_manifest_path(task, snapshot, path_from)
    if target_dir is None:
        return _result(
            rubric, verdict="not_applicable",
            reason=f"path_from {path_from!r} has no artifact_paths entry in this task's manifest -- rubric/manifest defect, not a run defect",
        )
    if not target_dir.is_dir():
        return _result(rubric, verdict="fail", reason=f"{target_dir} does not exist or is not a directory")

    present = {p.name for p in target_dir.iterdir()}
    missing = [name for name in required if name not in present]
    if missing:
        return _result(
            rubric, verdict="fail",
            reason=f"{len(missing)} of {len(required)} required entries from {reference_path} missing under {target_dir}: {missing[:10]}",
        )
    return _result(
        rubric, verdict="pass",
        reason=f"all {len(required)} required entries from {reference_path} are present under {target_dir} ({len(present)} entries total)",
        evidence_refs=[str(target_dir)],
    )


def _selected_names(args: dict[str, Any], snapshot: RunSnapshot, task: EvaluationTask) -> list[str]:
    """The metrics the rubric binds, chosen by the user when the task's rubric was authored: the
    keys of `args.references`, else `_metric_name`. The run being scored never chooses them."""
    for key in ("references", "bounds"):
        if isinstance(args.get(key), dict):
            return list(args[key])
    return [_metric_name(args, task)]


def check_numeric_relative_error_within(rubric: PhaseRubric, args: dict[str, Any], snapshot: RunSnapshot, task: EvaluationTask) -> CheckResult:
    """Every metric the rubric binds, as the run reports it in `report.json`, is within its
    tolerance of its reference -- both chosen by the user when the rubric was authored.
    `args.references` maps each metric (name as the evaluator prints it) to its reference; a single
    `reference` binds `_metric_name`. `max_relative_error` is one tolerance for all of them, or a
    mapping with one per metric."""
    references = args.get("references")
    if not isinstance(references, dict):
        references = {_metric_name(args, task): args.get("reference")} if args.get("reference") is not None else None
    tolerance = args.get("max_relative_error")
    tolerances = tolerance if isinstance(tolerance, dict) else {name: tolerance for name in references or {}}
    if not references or any(tolerances.get(name) is None for name in references):
        return _result(rubric, verdict="not_applicable", reason="checker.args needs reference or references and a max_relative_error for every metric -- rubric defect, not a run defect")
    lines: list[str] = []
    failed = False
    for name in references:
        _, value, failure = _reported(snapshot, name)
        if failure:
            return _result(rubric, verdict="fail", reason=failure)
        reference, limit = references[name], tolerances[name]
        relative_error = abs(value - reference) / abs(reference) if reference else float("inf")
        failed |= relative_error > limit
        lines.append(f"{name} {value} vs reference {reference}: relative error {relative_error:.6g} {'>' if relative_error > limit else '<='} {limit}")
    return _result(rubric, verdict="fail" if failed else "pass", reason="; ".join(lines), evidence_refs=["report.json"])


def check_metric_bounds(rubric: PhaseRubric, args: dict[str, Any], snapshot: RunSnapshot, task: EvaluationTask) -> CheckResult:
    """Every metric the rubric binds, as reported in `report.json`, lies within the bounds the user
    chose: `args.bounds` maps each metric (name as the evaluator prints it) to `{min, max}`, either
    one optional, both inclusive. For one-sided rules such as MLPerf's `accuracy-target` (lower
    bounds) and `accuracy-upper-limit` in `tools/submission/submission_checker/constants.py`."""
    bounds = args.get("bounds")
    if not isinstance(bounds, dict) or not bounds or any(not isinstance(b, dict) or (b.get("min") is None and b.get("max") is None) for b in bounds.values()):
        return _result(rubric, verdict="not_applicable", reason="checker.args.bounds must map every metric to a min and/or max -- rubric defect, not a run defect")
    lines: list[str] = []
    failed = False
    for name, bound in bounds.items():
        _, value, failure = _reported(snapshot, name)
        if failure:
            return _result(rubric, verdict="fail", reason=failure)
        low, high = bound.get("min"), bound.get("max")
        inside = (low is None or value >= low) and (high is None or value <= high)
        failed |= not inside
        lines.append(f"{name} {value} {'within' if inside else 'outside'} [{low}, {high}]")
    return _result(rubric, verdict="fail" if failed else "pass", reason="; ".join(lines), evidence_refs=["report.json"])


def check_reported_value_in_output(rubric: PhaseRubric, args: dict[str, Any], snapshot: RunSnapshot, task: EvaluationTask) -> CheckResult:
    """Every value `report.json` records for a bound metric appears, as written, in an evaluator
    output file matching `args.files`, rather than in arbitrary command output."""
    names = _selected_names(args, snapshot, task)
    files = args.get("files", [])
    if not files:
        return _result(rubric, verdict="not_applicable", reason="checker.args needs evaluator output file globs in 'files' -- rubric defect, not a run defect")
    texts = [item for item in snapshot.texts(files, include_executions=False) if item[0] != "report.json"]
    refs: list[str] = []
    for name in names:
        raw, _, failure = _reported(snapshot, name)
        if failure:
            return _result(rubric, verdict="fail", reason=failure)
        needle = str(raw).strip().rstrip("%")
        value_pattern = re.compile(rf"(?<![\d.]){re.escape(needle)}(?![\d.])")
        where = next((label for label, text in texts if value_pattern.search(text)), None)
        if where is None:
            return _result(rubric, verdict="fail", reason=f"report.json {name}={raw!r} appears in no evaluator output file matching {files}")
        refs.append(where)
    return _result(rubric, verdict="pass", reason=f"every reported value of {names} appears in evaluator output", evidence_refs=refs)


# The judge is a frozen study choice (docs/local-preferences.md, section 4), read from EVALUATION_JUDGE, which has
# no default: "claude:<model ID>" or "codex". An alias such as "opus" resolves to whatever model the installed CLI
# maps it to, so the claude backend takes a model ID and a call that the named model did not answer raises. The agents under test are Claude sessions, and a same-vendor judge favors its own family's output
# (CrossAudit, arXiv:2608.28631), so a Claude judge is scored with a warning.
CODEX_JUDGE = "codex"


def judge_backend() -> str:
    backend = os.environ.get("EVALUATION_JUDGE")
    if not backend:
        raise ValueError("EVALUATION_JUDGE is not set; it is the study's judge model (docs/local-preferences.md, section 4)")
    if backend != CODEX_JUDGE and not backend.startswith("claude:"):
        raise ValueError(f"EVALUATION_JUDGE={backend!r}: expected 'claude:<model ID>' or 'codex'")
    if backend == CODEX_JUDGE and shutil.which("codex") is None:
        raise RuntimeError("EVALUATION_JUDGE=codex but no codex CLI is on PATH")
    return backend


def _call_judge(prompt: str, schema: str, backend: str) -> tuple[str, dict]:
    with tempfile.TemporaryDirectory() as cwd:
        if backend == CODEX_JUDGE:
            schema_file, out_file = Path(cwd, "schema.json"), Path(cwd, "answer.json")
            schema_file.write_text(schema)
            done = subprocess.run(
                ["codex", "exec", "--skip-git-repo-check", "--sandbox", "read-only", "--output-schema", str(schema_file),
                 "--output-last-message", str(out_file), "-"], input=prompt, capture_output=True, text=True, cwd=cwd, timeout=600)
            try:
                answer = json.loads(out_file.read_text())
            except (OSError, json.JSONDecodeError):
                answer = None
            answered = "codex"
        else:
            done = subprocess.run(
                ["claude", "-p", "--model", backend.split(":", 1)[1], "--no-session-persistence", "--tools", "",
                 "--output-format", "json", "--json-schema", schema], input=prompt, capture_output=True, text=True, cwd=cwd, timeout=600)
            try:
                envelope = json.loads(done.stdout)
            except json.JSONDecodeError:
                envelope = {}
            model = backend.split(":", 1)[1]
            # The CLI also bills a helper model of its own; the verdict is the named model's or none.
            if model not in envelope.get("modelUsage", {}):
                raise RuntimeError(f"judge {backend} was not answered by {model}: models used {sorted(envelope.get('modelUsage', {}))}, "
                                   f"{str(envelope.get('result'))[:200]!r}")
            answered = model
            answer = envelope.get("structured_output")
    if not isinstance(answer, dict):  # raising keeps a failed call out of the record
        raise RuntimeError(f"judge {answered} gave no structured answer: {done.stdout[-200:]!r} {done.stderr[-200:]!r}")
    return answered, answer


def ask_judge(prompt: str, schema: dict, workspace: Path) -> tuple[str, dict]:
    """The judge's (model, answer), recorded under `<run dir>/evaluation/judge/` keyed by the prompt, so
    scoring the same evidence again returns the same answer instead of a new sample and the score can be
    checked again. Changed evidence or claim is a new prompt and a new call."""
    memory = joblib.Memory(workspace.parent / "evaluation" / "judge", verbose=0)
    backend = judge_backend()
    if backend != CODEX_JUDGE:
        warnings.warn(f"judge {backend} is the same vendor as the agents under test; "
                      "same-vendor judges favor their own family's output", stacklevel=2)
    return memory.cache(_call_judge)(prompt, json.dumps(schema), backend)


_JUDGE_SCHEMA = {
    "type": "object",
    "properties": {"verdict": {"enum": ["pass", "fail"]}, "reason": {"type": "string"}},
    "required": ["verdict", "reason"],
    "additionalProperties": False,  # Codex's strict output schema rejects a schema without it
}


def check_judge(rubric: PhaseRubric, args: dict[str, Any], snapshot: RunSnapshot, task: EvaluationTask) -> CheckResult:
    """A claim no fixed pattern can decide: an LLM judge (protocol.md, "Scores") reads the rubric's claim,
    its source references, and the evidence, and answers pass or fail with a reason. `args.files`
    selects workspace files beside the agent's messages and the command outputs; `args.hint` (a case-insensitive regex) keeps only lines
    that match it from each source, else each source's start is used. The judge runs outside the
    workspace, so its session is not part of any run's transcript."""
    hint = re.compile(args["hint"], re.IGNORECASE) if args.get("hint") else None
    limit = int(args.get("max_chars_per_source", 3000))
    sources = []
    # The agent's own messages come first: the skill has an autonomous agent state a change there before applying it.
    messages = [(f"agent message {i + 1} ({ts[:19]})", text) for i, (ts, text) in enumerate(snapshot.messages)]
    for label, text in [*messages, *snapshot.texts(args.get("files", []))]:
        kept = "\n".join(line for line in text.splitlines() if hint.search(line)) if hint else text
        if kept.strip():
            sources.append(f"--- {label}\n{kept[:limit]}")
    if not sources:
        return _result(rubric, verdict="fail", reason="no command output or workspace file held any evidence for the judge")
    refs = "\n".join(f"- {r['path']}: {r['excerpt']}" for r in rubric.source_refs)
    prompt = (
        "You are the judge for one rubric of a benchmark reproduction run. Decide from the evidence only "
        "whether the claim holds. A different route that reaches the same outcome as the benchmark "
        "documents satisfies the claim; a change that contradicts what the claim names does not.\n\n"
        f"CLAIM: {rubric.claim}\n\nSOURCES THE CLAIM COMES FROM:\n{refs}\n\nEVIDENCE:\n"
        + "\n".join(sources[: int(args.get("max_sources", 12))])
        + "\n\nAnswer with a verdict and a one-sentence reason."
    )
    # No verdict raises: it is a judge failure, not a rubric that does not apply, and scoring around it
    # would drop a critical rubric from its phase and let the phase pass.
    answered, answer = ask_judge(prompt, _JUDGE_SCHEMA, snapshot.workspace)
    return _result(rubric, verdict=answer["verdict"], reason=f"judge {answered}: {answer.get('reason', '')}", evidence_refs=[s.splitlines()[0][4:] for s in sources[:5]])


_CHECKERS = {
    "builtin.judge": check_judge,
    "builtin.landmark": check_landmark,
    "builtin.artifact_exists": check_artifact_exists,
    "builtin.artifact_hash_matches": check_artifact_hash_matches,
    "builtin.file_hash_equals": check_file_hash_equals,
    "builtin.directory_entry_count": check_directory_entry_count,
    "builtin.directory_contains_all": check_directory_contains_all,
    "builtin.numeric_relative_error_within": check_numeric_relative_error_within,
    "builtin.metric_bounds": check_metric_bounds,
    "builtin.reported_value_in_output": check_reported_value_in_output,
}


def run_checker(rubric: PhaseRubric, snapshot: RunSnapshot, task: EvaluationTask) -> CheckResult:
    kind = rubric.checker.get("kind")
    checker = _CHECKERS.get(kind)
    if checker is None:
        return _result(rubric, verdict="not_applicable", reason=f"unknown checker kind {kind!r} -- not implemented in evaluation/checkers.py")
    args = rubric.checker.get("args", {})
    if rubric.target is not None:
        # Command output in the transcript cannot be attributed to one target (a single command may have
        # run several), so a target's rubric reads its own workspace files only.
        snapshot = replace(snapshot, executions=[])
    if args.get("report_path") and snapshot.report is not None:
        # A multi-target report is nested by target id; the checker sees only its own section.
        section: Any = snapshot.report
        for key in args["report_path"]:
            section = section.get(key) if isinstance(section, dict) else None
        if not isinstance(section, dict):
            return _result(rubric, verdict="fail", reason=f"report.json has no object at {'/'.join(args['report_path'])}")
        snapshot = replace(snapshot, report=section)
    return checker(rubric, args, snapshot, task)

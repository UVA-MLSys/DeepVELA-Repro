"""Builds one arm's workspace for a reproduction run, so every run of a task starts the same way
(protocol.md, "Launch"). Run by `agent-evaluation-profile` launch mode, from a chat in this repository:

    python -m evaluation.prepare <profile_id> <task_id> --arm {plain,skill,builder-skill} [--compute {slurm,local,hybrid,cpu}] [--autonomy] [--model ID] [--effort LEVEL]

Without --compute, the Compute wording is the dataset `policy.compute` of the manifest's `source_id`.

Creates `$REPRODUCTION_RUNS_DIR/<task_id>/<arm>-<timestamp>/` with `ws/repo/` (the task's masked source),
`ws/tasks.json` (the per-target records the prompt points to), `ws/prompt.md` (the arm's prompt) and, for a
skill arm, the arm's skills: the Claude Code packages in `ws/.claude/skills/`, the Codex packages in
`ws/.agents/skills/`. It writes `launch.json` beside `ws/`, where the session does not look. The operator opens
`ws/` in a new editor window and sends `ws/prompt.md`; a Codex session is started with `codex_command` from
`launch.json`, which keeps the session in `<run>/codex-home/sessions/`.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shlex
import shutil
import tarfile
from pathlib import Path

import yaml

from .bundle import bundle_digest, check_id, profile_dir as bundle_profile_dir, resolve_bundle_root, task_dir as bundle_task_dir
from .task_prompt import load as load_record

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNS_ROOT_ENV_VAR = "REPRODUCTION_RUNS_DIR"
# The operator's own instructions file, which Claude Code loads into every session it starts. Each
# workspace's settings exclude it, so no arm receives the operator's instructions.
USER_CLAUDE_MD = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude")) / "CLAUDE.md"
# Codex has no per-workspace exclude: it loads AGENTS.md and lists every skill under $CODEX_HOME into each
# session, and saves the session there. Each run gets its own CODEX_HOME holding only the credentials (linked,
# so a token refresh reaches the operator's file) and a configuration naming only the study's model, so nothing
# else in the operator's config.toml (MCP servers, profiles) reaches a run.
USER_CODEX_HOME = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
SKILLS = REPO_ROOT / "skills"
# Skills installed in the arm's workspace, in the order the arm invokes them. Each coding agent gets its own package.
SKILL_FOR_ARM = {"plain": [], "skill": ["reproduce"], "builder-skill": ["builder-reproduce", "reproduce"]}
# Skills Codex installs into every CODEX_HOME. Disabled so a session lists only its arm's workspace skills.
CODEX_BUNDLED_SKILLS = ("imagegen", "openai-docs", "plugin-creator", "review-agent", "skill-creator", "skill-installer")
AGENT_SKILL_DIRS = {"claude": ".claude/skills", "codex": ".agents/skills"}
# The one difference between arms' prompts: a first line `/<skill>` naming the arm's first skill (protocol.md,
# "Setup"). The builder arm's last line names the hand-off to its second skill; each agent's builder package
# says how that hand-off is made.
BUILDER_INSTRUCTION = (
    "First write the benchmark contract for this task as ./BENCHMARK_CARD.md, and audit it with the skill's "
    "rubric and scorer, writing ./rubric.yaml and ./SCORE_REPORT.md. Then, once those three files exist, hand off "
    "to the `reproduce` skill as the builder skill's hand-off section says, and reproduce the task from that card.")
SHARED_ENVIRONMENT_INSTRUCTION = (
    "Other sessions share the GPUs, the Slurm account and the filesystem, and may run at the same time. "
    "Anything you did not start in this session is not yours: note the job ID each sbatch returns, cancel or modify "
    "only those IDs, check them with `squeue -j` or `sacct -j` instead of listing the account's jobs, and size GPU "
    "memory use to what `nvidia-smi` shows free on the GPU you use.")
# Compute nodes see the workspace, not the session's own scratch directory.
WORKSPACE_INSTRUCTION = (
    "Keep every file you create and later read, such as scripts, copies of the repository, work directories and "
    "outputs, inside this directory. Do not keep them in a session scratchpad or /tmp: a Slurm job "
    "cannot see them. Temporary directories are for transient files nothing later reads.")
CPU_SHARED_ENVIRONMENT_INSTRUCTION = (
    "Other sessions share the Slurm account and the filesystem, and may run at the same time. "
    "Anything you did not start in this session is not yours: note the job ID each sbatch returns, cancel or modify "
    "only those IDs, and check them with `squeue -j` or `sacct -j` instead of listing the account's jobs.")
LOCAL_SHARED_ENVIRONMENT_INSTRUCTION = (
    "Other sessions may share this machine's GPU and the filesystem, and may run at the same time. "
    "Anything you did not start in this session is not yours: cancel or modify only processes you started, "
    "and size GPU memory use to what `nvidia-smi` shows free.")
# The delivered entrypoint's compute requirement, by mode.
REPRODUCE_REQUIREMENT = {
    "slurm": "./reproduce.sh --target <target id> must run every step itself inside one Slurm job and submit no job.",
    "cpu": "./reproduce.sh --target <target id> must run every step itself inside one Slurm job and submit no job.",
    "hybrid": "./reproduce.sh --target <target id> must run its GPU work on this machine and submit its CPU-only work as Slurm jobs, starting each step after the jobs whose output it reads have finished.",
    "local": "./reproduce.sh --target <target id> must run on this machine.",
}
# Appended with --autonomy. The default, without it, is to stop and ask (reproduce, Situations).
AUTONOMY_INSTRUCTION = (
    "No human will reply to this session. Do not stop to ask or wait for approval: apply a change the task "
    "needs after stating it, its reason and its evidence in your message before the edit; when the task cannot "
    "be completed, write report.json with what was measured, state the failure with its evidence, and stop.")
LOCAL_PREFERENCES = REPO_ROOT / "docs" / "local-preferences.md"


def compute_wording() -> dict[str, str]:
    """The Compute paragraphs saved in docs/local-preferences.md, section 3, by mode."""
    found = re.findall(r"### Compute wording: (\w+)\n.*?```\n(.*?)\n```", LOCAL_PREFERENCES.read_text(), re.S)
    return {mode: text for mode, text in found}


def check_disjoint(roots: dict[str, Path]) -> None:
    """The repository, bundle root and runs root must not contain one another: a workspace under the bundle root
    or the repository could read the unmasked bundle files or every other task's records (protocol.md)."""
    items = list(roots.items())
    for i, (name_a, a) in enumerate(items):
        for name_b, b in items[i + 1:]:
            if a == b or a.is_relative_to(b) or b.is_relative_to(a):
                raise SystemExit(f"{name_a} {a} and {name_b} {b} overlap: choose disjoint directories "
                                 "(docs/local-preferences.md, sections 1 and 2)")


def codex_config(codex_home: Path, model: str | None, effort: str | None) -> str:
    lines = (f'model = "{model}"\n' if model else "") + (f'model_reasoning_effort = "{effort}"\n' if effort else "")
    return lines + "".join(f'\n[[skills.config]]\npath = "{codex_home / "skills" / ".system" / name / "SKILL.md"}"\nenabled = false\n'
                          for name in CODEX_BUNDLED_SKILLS)


def codex_command(root: Path, ws: Path, autonomy: bool) -> str:
    """Autonomous runs use `codex exec` with the prompt on stdin; interactive runs open the Codex TUI with the prompt
    as its first message, so the operator can answer the agent."""
    q = shlex.quote
    env = f"CODEX_HOME={q(str(root / 'codex-home'))} codex"
    flags = f"--dangerously-bypass-approvals-and-sandbox -C {q(str(ws))}"
    if autonomy:
        return (f"{env} exec {flags} --skip-git-repo-check -o {q(str(root / 'codex-final.txt'))} "
                f"- < {q(str(ws / 'prompt.md'))}")
    return f'{env} {flags} "$(cat {q(str(ws / "prompt.md"))})"'


def install_skills(ws: Path, skills: list[str]) -> None:
    for agent, relative in AGENT_SKILL_DIRS.items():
        for skill in skills:
            shutil.copytree(SKILLS / agent / skill, ws / relative / skill,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "tests"))


def access_scope(source_id: str | None, ws: Path, runs_root: Path) -> dict | None:
    """What the scorer flags as outside the task's access rule: inside `guarded` (this repository, which holds the
    harness and other tasks' records, and the runs root, which holds every other run), the session may touch only
    `allowed` and below: its own workspace and the repository's `.cache`, which holds input caches, tools and cloned
    sources, none of them a result. Answers are guarded by the task's `forbidden_access` patterns, not by location."""
    if source_id is None:
        return None
    return {"guarded": [str(REPO_ROOT), str(runs_root)], "allowed": [str(ws), str(REPO_ROOT / ".cache")]}


def prepare(profile_id: str, task_id: str, arm: str, compute: str | None = None, autonomy: bool = False,
            model: str | None = None, effort: str | None = None) -> Path:
    check_id("task_id", task_id)
    profile_dir = bundle_profile_dir(profile_id)
    task_dir = bundle_task_dir(profile_dir, task_id)
    prompt, source = task_dir / "prompt.md", task_dir / "source.tar.gz"
    if not prompt.is_file() or not source.is_file():
        raise SystemExit(f"{task_dir} has no prompt.md or source.tar.gz: the task has not been set up "
                         "(agent-evaluation-profile author mode)")
    digest = bundle_digest(profile_dir, task_id)
    wording = compute_wording()
    manifest = yaml.safe_load((task_dir / "manifest.yaml").read_text()) or {}
    source_id = manifest.get("source_id")
    if compute is None:
        compute = load_record(source_id).policy.compute if source_id else None
        if compute is None:
            raise SystemExit(f"{task_dir / 'manifest.yaml'} names no source_id whose dataset policy gives a compute "
                             "default: pass --compute slurm|local|hybrid|cpu")
    if compute not in wording:
        raise SystemExit(f"docs/local-preferences.md has no 'Compute wording: {compute}' block")
    unanswered = sorted(set(re.findall(r"\{\{[^}]*\}\}", wording[compute])))
    if unanswered:
        raise SystemExit(f"docs/local-preferences.md, 'Compute wording: {compute}', still holds {', '.join(unanswered)}: "
                         "answer them (section 3) before launching")
    runs_root = os.environ.get(RUNS_ROOT_ENV_VAR)
    if not runs_root:
        raise SystemExit(f"{RUNS_ROOT_ENV_VAR} is not set: take it from docs/local-preferences.md, section 2")
    runs_root = Path(runs_root).expanduser().resolve()
    check_disjoint({"repository": REPO_ROOT, "bundle root": resolve_bundle_root(), "runs root": runs_root})
    root = runs_root / task_id / f"{arm}-{dt.datetime.now():%Y-%m-%d-%H-%M-%S}"
    ws = root / "ws"
    (ws / "repo").mkdir(parents=True)
    with tarfile.open(source) as archive:
        archive.extractall(ws / "repo", filter="data")
    shutil.copyfile(task_dir / "tasks.json", ws / "tasks.json")
    (ws / ".claude").mkdir()
    (ws / ".claude" / "settings.json").write_text(json.dumps({"claudeMdExcludes": [str(USER_CLAUDE_MD)]}, indent=2) + "\n")
    skills = SKILL_FOR_ARM[arm]
    install_skills(ws, skills)
    shared = {"local": LOCAL_SHARED_ENVIRONMENT_INSTRUCTION, "cpu": CPU_SHARED_ENVIRONMENT_INSTRUCTION}.get(compute, SHARED_ENVIRONMENT_INSTRUCTION)
    text = prompt.read_text().rstrip("\n")
    text += "\n\n" + wording[compute] + " " + REPRODUCE_REQUIREMENT[compute]
    text += "\n\n" + shared + " " + WORKSPACE_INSTRUCTION + "\n"
    if autonomy:
        text += "\n" + AUTONOMY_INSTRUCTION + "\n"
    if arm == "builder-skill":
        text = text.rstrip("\n") + "\n\n" + BUILDER_INSTRUCTION + "\n"
    if skills:
        text = f"/{skills[0]}\n" + text
    (ws / "prompt.md").write_text(text)
    codex_home = root / "codex-home"
    codex_home.mkdir()
    if (USER_CODEX_HOME / "auth.json").is_file():  # absent when the operator does not use Codex
        (codex_home / "auth.json").symlink_to(USER_CODEX_HOME / "auth.json")
    (codex_home / "config.toml").write_text(codex_config(codex_home, model, effort))
    launch = {
        "profile_id": profile_id, "task_id": task_id, "bundle_digest": digest, "arm": arm,
        "workspace": str(ws), "prompt": str(ws / "prompt.md"),
        "prompt_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "base_prompt_sha256": hashlib.sha256(prompt.read_bytes()).hexdigest(),
        # evaluation.launch sets this; a null boundary means the run is still mutable.
        "ended": None,
        "skill": skills[-1] if skills else None,
        "skills": skills, "compute": compute,
        "access_scope": access_scope(source_id, ws, runs_root), "autonomy": autonomy, "model": model, "effort": effort,
        "codex_home": str(codex_home), "codex_command": codex_command(root, ws, autonomy),
        "prepared": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    (root / "launch.json").write_text(json.dumps(launch, indent=2) + "\n")
    return root


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("profile_id")
    parser.add_argument("task_id")
    parser.add_argument("--arm", choices=sorted(SKILL_FOR_ARM), required=True)
    parser.add_argument("--compute", choices=["slurm", "local", "hybrid", "cpu"],
                        help="append that Compute wording from docs/local-preferences.md; default: the dataset policy of the manifest's source_id")
    parser.add_argument("--autonomy", action="store_true", help="tell the session no human will reply, so it does not stop to ask")
    parser.add_argument("--model", help="the study's Codex model ID (docs/local-preferences.md, section 4); written to the run's CODEX_HOME and recorded")
    parser.add_argument("--effort", help="the study's Codex reasoning effort; written to the run's CODEX_HOME and recorded")
    args = parser.parse_args()
    root = prepare(args.profile_id, args.task_id, args.arm, args.compute, args.autonomy, args.model, args.effort)
    launch = json.loads((root / "launch.json").read_text())
    print(f"workspace: {root / 'ws'}")
    print(f"prompt:    {launch['prompt']}")
    print(f"launch:    {root / 'launch.json'}")
    print(f"codex:     {launch['codex_command']}")


if __name__ == "__main__":
    main()

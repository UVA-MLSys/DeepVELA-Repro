"""Run a prepared autonomous Codex arm, and freeze a finished run's launch record.

    python -m evaluation.launch <launch.json> [--freeze-only]

Without `--freeze-only`, runs `codex_command` from `launch.json` with the evaluation's variables (bundle root, runs
root, virtual environment) removed from the environment and this repository's directories removed from `PATH`, then
freezes the run. A session that could read `EVALUATION_BUNDLE_DIR` would find the unmasked bundle, and one that found
this repository's `python` would run in the harness's environment. Output goes to `codex-exec.log` beside `ws/`.
`--freeze-only` records `ended` and `canonical_trace` for a run started another way: an interactive Codex run, or a
Claude Code run. Set `CODEX_BIN` when `codex` is not on `PATH`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .transcript import find_sessions


def _codex() -> str:
    codex = shutil.which("codex") or os.environ.get("CODEX_BIN")
    if not codex:
        raise SystemExit("could not find Codex: put codex on PATH or set CODEX_BIN")
    return codex


REPO_ROOT = Path(__file__).resolve().parents[1]
# Variables that locate the evaluation (bundles with rubrics and masks, other runs, the judge); a session never gets them.
EVALUATION_VARIABLES = ("EVALUATION_", "REPRODUCTION_RUNS_DIR", "CODEX_BIN", "VIRTUAL_ENV")


def _session_environment(codex: str) -> dict[str, str]:
    """The launching shell's environment without the evaluation's variables and without PATH entries inside this
    repository (its .venv), so the session's `python3` is the machine's, not the evaluation's."""
    environment = {k: v for k, v in os.environ.items() if not k.startswith(EVALUATION_VARIABLES)}
    path = [p for p in environment.get("PATH", "").split(os.pathsep)
            if p and not Path(p).resolve().is_relative_to(REPO_ROOT)]
    environment["PATH"] = os.pathsep.join([str(Path(codex).parent), *path])
    return environment


def _records(path: Path) -> list[dict[str, Any]]:
    records = []
    for line in path.read_text().splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def _freeze(launch_path: Path, launch: dict[str, Any], codex: str | None, exit_code: int | None) -> None:
    """Record the end of the run's one session: a Codex session under the run's `CODEX_HOME`, else the Claude Code
    session files of the workspace."""
    session_root = Path(launch["codex_home"]) / "sessions"
    sessions = sorted(path for path in session_root.rglob("*.jsonl") if path.is_file())
    harness = "codex"
    if not sessions:
        sessions, harness = find_sessions(Path(launch["workspace"])), "claude-code"
    if len(sessions) != 1:
        found = ", ".join(str(path) for path in sessions) or "none"
        raise SystemExit(f"expected exactly one session for {launch['workspace']}; found: {found}")
    session = sessions[0]
    records = _records(session)
    ended = next((record["timestamp"] for record in reversed(records) if record.get("timestamp")), None)
    meta = next((record for record in records if record.get("type") == "session_meta"), None)
    session_id = (meta or {}).get("payload", {}).get("session_id") if harness == "codex" else session.stem
    if not ended or not session_id:
        raise SystemExit(f"{session} needs a timestamped record and a session id")
    launch.update({
        "ended": ended,
        "canonical_trace": {
            "path": str(session.resolve()),
            "session_id": session_id,
            "sha256": hashlib.sha256(session.read_bytes()).hexdigest(),
        },
        "runtime": subprocess.check_output([codex, "--version"], text=True).strip() if harness == "codex" else "claude-code",
        "launcher_exit_code": exit_code,
    })
    with tempfile.NamedTemporaryFile("w", dir=launch_path.parent, delete=False) as handle:
        json.dump(launch, handle, indent=2)
        handle.write("\n")
        temporary = Path(handle.name)
    os.replace(temporary, launch_path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("launch", type=Path)
    parser.add_argument("--freeze-only", action="store_true")
    args = parser.parse_args()
    launch_path = args.launch.resolve()
    launch = json.loads(launch_path.read_text())
    if launch.get("ended") is not None:
        raise SystemExit(f"{launch_path} is already frozen")
    exit_code = None
    codex = None if args.freeze_only and not Path(launch["codex_home"], "sessions").is_dir() else _codex()
    if not args.freeze_only:
        if not launch["autonomy"]:
            raise SystemExit("this run is interactive: start it in a terminal with the codex_command in launch.json, "
                             "then freeze it with --freeze-only")
        run_dir = Path(launch["workspace"]).parent
        environment = _session_environment(codex)
        with (run_dir / "codex-exec.log").open("w") as log:
            exit_code = subprocess.run(["bash", "-c", launch["codex_command"]], env=environment, stdout=log, stderr=subprocess.STDOUT).returncode
    _freeze(launch_path, launch, codex, exit_code)


if __name__ == "__main__":
    main()

"""evaluation.launch keeps the evaluation's variables and the harness's own directories out of a session."""

import json
from pathlib import Path

import pytest

from evaluation import launch


def test_session_environment_drops_evaluation_variables_and_repository_paths(monkeypatch, tmp_path):
    codex_dir = tmp_path / "codex-bin"
    codex_dir.mkdir()
    monkeypatch.setenv("EVALUATION_BUNDLE_DIR", "/bundles")
    monkeypatch.setenv("REPRODUCTION_RUNS_DIR", "/runs")
    monkeypatch.setenv("VIRTUAL_ENV", str(launch.REPO_ROOT / ".venv"))
    monkeypatch.setenv("PATH", f"{launch.REPO_ROOT / '.venv/bin'}:/usr/bin")
    environment = launch._session_environment(str(codex_dir / "codex"))
    assert not {"EVALUATION_BUNDLE_DIR", "REPRODUCTION_RUNS_DIR", "VIRTUAL_ENV"} & environment.keys()
    assert environment["PATH"].split(":") == [str(codex_dir), "/usr/bin"]


def _launch(tmp_path):
    run = tmp_path / "run"
    (run / "ws").mkdir(parents=True)
    path = run / "launch.json"
    record = {"workspace": str(run / "ws"), "codex_home": str(run / "codex-home"), "autonomy": True, "ended": None}
    path.write_text(json.dumps(record))
    return path, record


def test_freeze_records_the_end_of_a_codex_session(tmp_path):
    path, record = _launch(tmp_path)
    session = tmp_path / "run/codex-home/sessions/2026/s.jsonl"
    session.parent.mkdir(parents=True)
    session.write_text(json.dumps({"type": "session_meta", "timestamp": "2026-11-19T10:00:00Z", "payload": {"session_id": "abc"}})
                       + "\n" + json.dumps({"timestamp": "2026-11-19T10:05:00Z"}) + "\n")
    codex = tmp_path / "codex"
    codex.write_text("#!/bin/sh\necho codex-test 1.0\n")
    codex.chmod(0o755)
    launch._freeze(path, record, str(codex), 0)
    frozen = json.loads(path.read_text())
    assert frozen["ended"] == "2026-11-19T10:05:00Z" and frozen["canonical_trace"]["session_id"] == "abc"
    assert frozen["runtime"] == "codex-test 1.0" and frozen["launcher_exit_code"] == 0


def test_freeze_records_the_end_of_a_claude_code_session(tmp_path, monkeypatch):
    path, record = _launch(tmp_path)
    session = tmp_path / "claude-session.jsonl"
    session.write_text(json.dumps({"timestamp": "2026-11-19T11:00:00.000Z"}) + "\n")
    monkeypatch.setattr(launch, "find_sessions", lambda workspace: [session])
    launch._freeze(path, record, None, None)
    frozen = json.loads(path.read_text())
    assert frozen["ended"] == "2026-11-19T11:00:00.000Z" and frozen["canonical_trace"]["session_id"] == "claude-session"


def test_freeze_refuses_when_no_single_session_exists(tmp_path, monkeypatch):
    path, record = _launch(tmp_path)
    monkeypatch.setattr(launch, "find_sessions", lambda workspace: [])
    with pytest.raises(SystemExit, match="exactly one session"):
        launch._freeze(path, record, None, None)

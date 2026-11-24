"""The scorer flags what the task prompt's access rule forbids inside the framework repository and the runs
root: their reports and other runs. The workspace, the repository's `.cache`, and everything outside both roots, pass."""

import json

from evaluation.scorer import outside_scope

SCOPE = {"guarded": ["/p/repo", "/p/runs"],
         "allowed": ["/p/runs/t/skill-1/ws", "/p/repo/.cache"]}


def flagged(command: str) -> list[str]:
    return outside_scope(json.dumps({"command": command}), SCOPE)


def test_named_paths_and_outside_roots_pass():
    assert flagged("CACHE_ROOT=/p/repo/.cache; ls /p/repo/.cache/imagenet/x.JPEG /usr/lib /tmp/s") == []
    assert flagged("cd /p/runs/t/skill-1/ws/repo && UV_CACHE_DIR=/p/repo/.cache/uv uv sync") == []


def test_reports_and_other_runs_are_flagged_cache_is_not():
    assert flagged("cat /p/repo/docs/reports/README.md") == ["/p/repo/docs/reports/README.md"]
    assert flagged("cat /p/runs/t/plain-1/ws/report.json") == ["/p/runs/t/plain-1/ws/report.json"]
    assert flagged("ls /p/repo/.cache/sources /p/repo/.cache/huggingface") == []
    assert flagged("cat /p/repo/docs/reports/notes.md") == ["/p/repo/docs/reports/notes.md"]

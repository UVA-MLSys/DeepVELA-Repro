"""evaluation.prepare builds each arm's workspace from a sealed bundle."""

import io
import json
import tarfile

import pytest

from evaluation import prepare as prepare_module
from evaluation.bundle import EvaluationBundleError, seal
from evaluation.prepare import prepare
from evaluation.task_prompt import load

COMMIT = load("mlperf-language-bert").repo["commit"]


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    task = tmp_path / "bundles/t"
    task.mkdir(parents=True)
    (task / "manifest.yaml").write_text(f"task_id: t\nsource_id: mlperf-language-bert\ncommit: {COMMIT}\n")
    (task / "prompt.md").write_text(f"Reproduce the synthetic task at commit {COMMIT}.\n")
    (task / "tasks.json").write_text("[]\n")
    (task / "masked.txt").write_text("No reference value stated.\n")
    with tarfile.open(task / "source.tar.gz", "w:gz") as archive:
        payload = b"synthetic pinned source\n"
        entry = tarfile.TarInfo("README.md")
        entry.size = len(payload)
        archive.addfile(entry, io.BytesIO(payload))
    monkeypatch.setenv("EVALUATION_BUNDLE_DIR", str(tmp_path / "bundles"))
    monkeypatch.setenv("REPRODUCTION_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setattr(prepare_module, "USER_CODEX_HOME", tmp_path / "no-codex")
    seal("t")
    return task


def test_skill_arm_gets_each_harness_package(bundle):
    ws = prepare("t", "skill", compute="local") / "ws"
    claude, codex = ws / ".claude/skills/reproduce", ws / ".agents/skills/reproduce"
    assert (claude / "SKILL.md").read_text() == (prepare_module.SKILLS / "claude/reproduce/SKILL.md").read_text()
    assert (codex / "SKILL.md").read_text() == (prepare_module.SKILLS / "codex/reproduce/SKILL.md").read_text()
    assert json.loads((ws / ".claude/settings.json").read_text())["claudeMdExcludes"]
    assert (ws / "prompt.md").read_text().startswith("/reproduce\nReproduce the synthetic task")
    assert (ws / "repo/README.md").is_file()


def test_builder_arm_installs_both_skills_and_names_the_handoff(bundle):
    ws = prepare("t", "builder-skill", compute="local", autonomy=True) / "ws"
    for harness in (".claude/skills", ".agents/skills"):
        assert {p.name for p in (ws / harness).iterdir()} == {"builder-reproduce", "reproduce"}
    text = (ws / "prompt.md").read_text()
    assert text.startswith("/builder-reproduce\n") and "No human will reply" in text
    assert text.rstrip().endswith(prepare_module.BUILDER_INSTRUCTION)


def test_plain_arm_has_no_skill(bundle):
    ws = prepare("t", "plain", compute="local") / "ws"
    assert not (ws / ".claude/skills").exists() and not (ws / ".agents/skills").exists()
    assert (ws / "prompt.md").read_text().startswith("Reproduce the synthetic task")


def test_unanswered_compute_wording_refuses_launch(bundle):
    with pytest.raises(SystemExit, match=r"\{\{account\}\}"):
        prepare("t", "skill", compute="slurm")


def test_bundle_edited_after_sealing_refuses_launch(bundle):
    (bundle / "prompt.md").write_text("A different task.\n")
    with pytest.raises(EvaluationBundleError, match="changed after it was sealed"):
        prepare("t", "skill", compute="local")


def test_overlapping_roots_refuse_launch(bundle, monkeypatch):
    monkeypatch.setenv("REPRODUCTION_RUNS_DIR", str(bundle.parent / "runs"))
    with pytest.raises(SystemExit, match="overlap"):
        prepare("t", "skill", compute="local")


def test_manifest_must_match_the_record(bundle):
    (bundle / "manifest.yaml").write_text("task_id: t\nsource_id: mlperf-language-bert\ncommit: 0000\n")
    with pytest.raises(EvaluationBundleError, match="record pins"):
        seal("t")


def test_unsafe_task_id_is_refused(bundle):
    with pytest.raises(EvaluationBundleError, match="task_id"):
        prepare("../t", "skill", compute="local")


def test_codex_command_is_interactive_unless_autonomous_and_quoted(bundle, monkeypatch, tmp_path):
    monkeypatch.setenv("REPRODUCTION_RUNS_DIR", str(tmp_path / "runs with space"))
    interactive = json.loads((prepare("t", "skill", compute="local", model="m1") / "launch.json").read_text())
    autonomous = json.loads((prepare("t", "plain", compute="local", autonomy=True) / "launch.json").read_text())
    assert " exec " not in interactive["codex_command"] and "-m m1" in interactive["codex_command"]
    assert interactive["model"] == "m1"
    assert " exec " in autonomous["codex_command"] and "'" in autonomous["codex_command"]

"""Per-target scoring and legacy single-target compatibility (evaluation/{bundle,checkers,scorer}.py).
Synthetic bundles only; the historical ResNet50 runs are integration evidence, not part of this file."""

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from evaluation.bundle import EvaluationBundleError, bundle_digest, load_profile, load_task
from evaluation.scorer import IntegrityFailure, score_run

ACCURACY = "accuracy=76.138%, good=38069, total=50000"
OTHER = "accuracy=76.448%, good=38224, total=50000"


def _rubric(rid, phase, args, *, target=None, prerequisites=(), kind="builtin.landmark"):
    return {"rubric_id": rid, "phase_id": phase, "claim": rid, "target": target, "critical": True,
            "prerequisites": list(prerequisites), "evidence_contract": {"artifacts": []},
            "checker": {"kind": kind, "args": args}}


def _contract(reference):
    return {"evaluator_identity": "e", "result_name_type_and_direction": "accuracy, float, higher_is_better",
            "reference_value": reference, "acceptance_rule": "r", "source_path_sha256_excerpt": {}}


def _seal(profile: Path) -> None:
    lines = [f"{hashlib.sha256(f.read_bytes()).hexdigest()}  ./{f.relative_to(profile).as_posix()}"
             for f in sorted(profile.rglob("*")) if f.is_file() and f.name != "MANIFEST.sha256"]
    (profile / "MANIFEST.sha256").write_text("\n".join(lines) + "\n")


def _bundle(root: Path, task: str, manifest: dict, rubrics: list[dict], templates: list[str] | None = None) -> None:
    profile = root / "p"
    (profile / "tasks" / task / "rubrics").mkdir(parents=True)
    (profile / "bundle.yaml").write_text(yaml.safe_dump({"profile_id": "p", "profile_version": 1, "phases": [
        {"id": "ph", "label": "Phase", "templates": templates or []}]}))
    base = {"task_id": task, "profile_id": "p", "profile_version": 1, "suite_role": "development", "source_revision": "r",
            "objective": "o", "input_reuse_contract": {"cache_condition_id": "cold"},
            "authored_by": {"model_id": "m", "authored_at": "d", "source_revision": "r"}, **manifest}
    (profile / "tasks" / task / "manifest.yaml").write_text(yaml.safe_dump(base))
    for r in rubrics:
        (profile / "tasks" / task / "rubrics" / f"{r['rubric_id']}.yaml").write_text(yaml.safe_dump(r))
    _seal(profile)


def _multi_bundle(root: Path) -> None:
    def spec(name, ref):
        return {"quality_rubric_id": f"quality__{name}", "quality_contract": _contract(ref), "shared_rubrics": ["data"]}
    rubrics = [_rubric("data", "ph", {"pattern": "x", "files": ["data.txt"]})]
    for name, ref in (("pt", 76.014), ("onnx", 76.456)):
        rubrics += [
            _rubric(f"evaluated__{name}", "ph", {"pattern": r"accuracy=\d+\.\d{3}%", "files": [f"{name}/accuracy.txt"]}, target=name, prerequisites=["data"]),
            _rubric(f"quality__{name}", "ph", {"report_path": [name], "metric_name": "accuracy", "references": {"accuracy": ref}, "max_relative_error": 0.01},
                    target=name, prerequisites=["data"], kind="builtin.numeric_relative_error_within"),
        ]
    _bundle(root, "t", {"targets": {"pt": spec("pt", 76.014), "onnx": spec("onnx", 76.456)}}, rubrics)


def _score(root: Path, workspace: Path, **launch):
    return score_run({"profile_id": "p", "task_id": "t", "bundle_digest": bundle_digest(root / "p", "t"),
                      "workspace": str(workspace), **launch})[0]


@pytest.fixture
def bundle_root(tmp_path, monkeypatch):
    monkeypatch.setenv("EVALUATION_BUNDLE_DIR", str(tmp_path))
    return tmp_path


def _workspace(root: Path, files: dict[str, str], report: dict) -> Path:
    ws = root / "run" / "ws"
    for name, text in {**files, "report.json": json.dumps(report), "data.txt": "x"}.items():
        (ws / name).parent.mkdir(parents=True, exist_ok=True)
        (ws / name).write_text(text)
    return ws


def test_each_target_is_scored_on_its_own_evidence(bundle_root):
    _multi_bundle(bundle_root)
    ws = _workspace(bundle_root, {"pt/accuracy.txt": ACCURACY, "onnx/accuracy.txt": OTHER},
                    {"pt": {"accuracy": "76.138%"}, "onnx": {"accuracy": "76.448%"}})
    run = _score(bundle_root, ws)
    assert run.quality_result is None and set(run.targets) == {"pt", "onnx"}
    assert run.targets["pt"].success and run.targets["onnx"].success
    assert run.end_to_end_success is True and run.target_success_rate == 1.0


def test_prepared_run_must_be_frozen_before_scoring(bundle_root):
    _multi_bundle(bundle_root)
    ws = _workspace(bundle_root, {"pt/accuracy.txt": ACCURACY, "onnx/accuracy.txt": OTHER},
                    {"pt": {"accuracy": "76.138%"}, "onnx": {"accuracy": "76.448%"}})
    with pytest.raises(IntegrityFailure, match="run is not frozen"):
        _score(bundle_root, ws, ended=None)


def test_a_failing_target_does_not_fail_the_other(bundle_root):
    _multi_bundle(bundle_root)
    ws = _workspace(bundle_root, {"pt/accuracy.txt": ACCURACY},  # onnx evaluator output missing
                    {"pt": {"accuracy": "76.138%"}, "onnx": {"accuracy": "76.448%"}})
    run = _score(bundle_root, ws)
    assert run.targets["pt"].success is True and run.targets["onnx"].success is False
    assert run.end_to_end_success is False and run.target_success_rate == 0.5


def test_swapped_report_values_stay_with_their_targets(bundle_root):
    # Deliberately distant values make both target-specific quality rules fail if the reports are swapped.
    _multi_bundle(bundle_root)
    ws = _workspace(bundle_root, {"pt/accuracy.txt": "accuracy=90.000%", "onnx/accuracy.txt": "accuracy=10.000%"},
                    {"pt": {"accuracy": "90.000%"}, "onnx": {"accuracy": "10.000%"}})
    run = _score(bundle_root, ws)
    assert run.targets["pt"].quality_result.value == 90.0 and run.targets["pt"].quality_result.reference == 76.014
    assert run.targets["onnx"].quality_result.value == 10.0 and run.targets["onnx"].quality_result.reference == 76.456
    assert not run.targets["pt"].quality_result.passed and not run.targets["onnx"].quality_result.passed
    assert run.end_to_end_success is False


def test_target_rubrics_ignore_command_output(bundle_root, monkeypatch):
    # An accuracy line that exists only in a transcript command output must not satisfy a target rubric.
    import evaluation.scorer as scorer
    from evaluation.schema import Execution
    _multi_bundle(bundle_root)
    ws = _workspace(bundle_root, {}, {"pt": {"accuracy": "76.138%"}, "onnx": {"accuracy": "76.448%"}})
    execution = Execution(source="s", timestamp="2026-01-01T00:00:00", command="run both", outcome="ok", output=ACCURACY)
    monkeypatch.setattr(scorer, "extract", lambda sessions, workspace=None: ([], [execution]))
    monkeypatch.setattr(scorer, "find_sessions", lambda w: [object()])
    monkeypatch.setattr(scorer, "agent_messages", lambda *args, **kwargs: [])
    monkeypatch.setattr(scorer, "accesses", lambda *a: [])
    monkeypatch.setattr(scorer, "slash_commands", lambda *a: [])
    monkeypatch.setattr(scorer, "models", lambda s: [])
    monkeypatch.setattr(scorer, "usage", lambda *a: None)
    run = _score(bundle_root, ws)
    assert not run.targets["pt"].success and not run.targets["onnx"].success


def test_shared_rubrics_must_match_prerequisite_closure(bundle_root):
    _multi_bundle(bundle_root)
    manifest = bundle_root / "p/tasks/t/manifest.yaml"
    data = yaml.safe_load(manifest.read_text())
    data["targets"]["pt"]["shared_rubrics"] = []
    manifest.write_text(yaml.safe_dump(data))
    _seal(bundle_root / "p")
    with pytest.raises(EvaluationBundleError, match="closure"):
        load_task(load_profile("p"), "t")


def test_quality_rubric_must_belong_to_its_target(bundle_root):
    _multi_bundle(bundle_root)
    manifest = bundle_root / "p/tasks/t/manifest.yaml"
    data = yaml.safe_load(manifest.read_text())
    data["targets"]["pt"]["quality_rubric_id"] = "quality__onnx"
    manifest.write_text(yaml.safe_dump(data))
    _seal(bundle_root / "p")
    with pytest.raises(EvaluationBundleError, match="belongs to 'onnx'"):
        load_task(load_profile("p"), "t")


def test_transitive_prerequisites_must_exist(bundle_root):
    _multi_bundle(bundle_root)
    rubric_path = bundle_root / "p/tasks/t/rubrics/data.yaml"
    rubric = yaml.safe_load(rubric_path.read_text())
    rubric["prerequisites"] = ["missing"]
    rubric_path.write_text(yaml.safe_dump(rubric))
    _seal(bundle_root / "p")
    with pytest.raises(EvaluationBundleError, match="unknown prerequisites \\['missing'\\]"):
        load_task(load_profile("p"), "t")


def test_prerequisites_cannot_cross_targets(bundle_root):
    _multi_bundle(bundle_root)
    rubric_path = bundle_root / "p/tasks/t/rubrics/evaluated__pt.yaml"
    rubric = yaml.safe_load(rubric_path.read_text())
    rubric["prerequisites"].append("quality__onnx")
    rubric_path.write_text(yaml.safe_dump(rubric))
    _seal(bundle_root / "p")
    with pytest.raises(EvaluationBundleError, match="foreign target rubrics.*quality__onnx"):
        load_task(load_profile("p"), "t")


def test_single_target_task_is_unchanged(bundle_root):
    _bundle(bundle_root, "t", {"quality_contract": _contract(76.014), "quality_rubric_id": "quality"},
            [_rubric("quality", "ph", {"metric_name": "accuracy", "references": {"accuracy": 76.014}, "max_relative_error": 0.01},
                     kind="builtin.numeric_relative_error_within")], templates=["quality"])
    ws = _workspace(bundle_root, {}, {"accuracy": "76.138%"})
    run = _score(bundle_root, ws)
    assert run.targets == {} and run.target_success_rate is None
    assert run.quality_result.passed and run.phases["ph"].success and run.end_to_end_success is True

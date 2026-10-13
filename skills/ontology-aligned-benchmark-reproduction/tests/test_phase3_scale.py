import argparse
import tempfile
import unittest
from pathlib import Path

from _fixture import SCRIPTS, build_campaign  # noqa: F401
from _common import read_json, write_json_atomic, write_jsonl_atomic
from decide_acceptance import compute_decisions, persist
from materialize_experiment_condition import materialize, safe_relative
from seal_benchmark_assessment import seal
from store_artifact import store
from summarize_trial import build_summary
from validate_ontology_graph import validate


class PhaseThreeScaleTest(unittest.TestCase):
    def test_content_addressed_store_deduplicates_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = build_campaign(base / "campaign")
            payload = base / "payload.bin"
            payload.write_bytes(b"same-content")
            common = dict(
                role="log",
                producer_attempt_id="attempt:one",
                target_id=["target:one"],
                dependency=["binding:one"],
                media_type="application/octet-stream",
                logical_name=None,
            )
            first = store(root, payload, argparse.Namespace(artifact_id="artifact:cas-one", **common))
            second = store(root, payload, argparse.Namespace(artifact_id="artifact:cas-two", **common))
            self.assertEqual(first["path"], second["path"])
            objects = [path for path in (root / "artifact-store").rglob("*") if path.is_file()]
            self.assertEqual(len(objects), 1)

    def test_trial_summary_has_comparable_fixed_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            root = build_campaign(Path(directory))
            persist(root, compute_decisions(root))
            summary = build_summary(root, "trial:one", "condition:one", "procedural_skill")
            self.assertEqual(summary["schema_version"], "1.0")
            self.assertEqual(summary["disposition_counts"]["accepted"], 1)
            self.assertEqual(summary["evidence_coverage"]["obligation_ratio"], 1.0)

    def test_windows_and_parent_traversal_paths_are_rejected(self):
        for value in ["../secret", "C:\\secret\\file.txt", "\\\\server\\share\\file.txt"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                safe_relative(value)

    def test_changed_assessment_invalidates_independent_seal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = build_campaign(Path(directory))
            seal(root, "reviewer:test", "initial review")
            assessment_path = root / "contract" / "benchmark-assessment.json"
            assessment = read_json(assessment_path)
            assessment["categories"][0]["criteria"][0]["rationale"] = "changed later"
            write_json_atomic(assessment_path, assessment)
            report = validate(root)
            self.assertIn("stale_assessment_seal", {item["code"] for item in report["errors"]})

    def test_relation_endpoint_type_spoof_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = build_campaign(Path(directory))
            write_jsonl_atomic(
                root / "ontology" / "relations.jsonl",
                [
                    {
                        "relation_id": "relation:bad-type",
                        "relation_type": "implemented_by",
                        "from_id": "obligation:one",
                        "from_type": "artifact",
                        "to_id": "binding:one",
                        "to_type": "binding",
                    }
                ],
            )
            report = validate(root)
            self.assertIn("relation_type_mismatch", {item["code"] for item in report["errors"]})

    def test_condition_bundle_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = build_campaign(base / "campaign")
            source = base / "source"
            source.mkdir()
            (source / "visible.txt").write_text("original", encoding="utf-8")
            condition = materialize(
                root,
                source,
                {
                    "condition_id": "condition:tamper",
                    "trial_id": "trial:tamper",
                    "controller_realization": "procedural_skill",
                    "benchmark_readiness_condition": "full",
                    "visible_paths": ["visible.txt"],
                    "withheld_paths": [],
                    "withheld_ontology_elements": [],
                    "agent_configuration": {},
                    "source_access": [],
                    "tool_access": [],
                    "budgets": {},
                    "intervention_policy": {},
                },
            )
            (condition / "visible" / "visible.txt").write_text("tampered", encoding="utf-8")
            report = validate(root)
            self.assertIn("condition_bundle_mismatch", {item["code"] for item in report["errors"]})


if __name__ == "__main__":
    unittest.main()

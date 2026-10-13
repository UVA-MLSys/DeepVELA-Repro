import tempfile
import unittest
from pathlib import Path

from _fixture import SCRIPTS, build_campaign  # noqa: F401
from _common import invalidated_ids, read_json
from invalidate_dependents import invalidate, resolve
from score_benchmark_readiness import score
from validate_ontology_graph import validate
from verify_artifact_integrity import verify


class PhaseOneControlsTest(unittest.TestCase):
    def test_rubric_rejects_points_without_source_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = build_campaign(Path(directory))
            assessment = read_json(root / "contract" / "benchmark-assessment.json")
            assessment["categories"][0]["criteria"][0]["evidence_source_ids"] = []
            with self.assertRaisesRegex(ValueError, "without source evidence"):
                score(assessment)

    def test_integrity_check_detects_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            root = build_campaign(Path(directory))
            artifact = root / "attempts" / "attempt_one" / "artifacts" / "result.json"
            artifact.write_text('{"tampered": true}\n', encoding="utf-8")
            report = verify(root)
            self.assertFalse(report["all_valid"])
            graph = validate(root)
            self.assertIn("artifact_digest_mismatch", {item["code"] for item in graph["errors"]})

    def test_resolved_invalidation_no_longer_marks_evidence_active(self):
        with tempfile.TemporaryDirectory() as directory:
            root = build_campaign(Path(directory))
            record = invalidate(root, ["binding:one"], "fixture change", True)
            self.assertTrue(invalidated_ids(root))
            resolve(root, record["invalidation_id"], ["binding:replacement"])
            self.assertFalse(invalidated_ids(root))


if __name__ == "__main__":
    unittest.main()

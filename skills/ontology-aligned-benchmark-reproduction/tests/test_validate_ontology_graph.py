import json
import tempfile
import unittest
from pathlib import Path

from _fixture import SKILL_ROOT, SCRIPTS, build_campaign  # noqa: F401
from validate_ontology_graph import validate


class GraphValidationTest(unittest.TestCase):
    def test_valid_fixture_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = build_campaign(Path(directory))
            report = validate(root)
            self.assertTrue(report["valid"], report["errors"])

    def test_all_schema_files_are_valid_json(self):
        schemas = list((SKILL_ROOT / "assets" / "schemas").glob("*.json"))
        self.assertEqual(len(schemas), 6)
        definitions = set()
        for path in schemas:
            with self.subTest(path=path.name):
                module = json.loads(path.read_text(encoding="utf-8"))
                self.assertIn("$defs", module)
                definitions.update(module["$defs"])
        self.assertEqual(
            definitions,
            {
                "campaign_contract",
                "benchmark_assessment",
                "target_manifest",
                "verification_policy",
                "campaign_state",
                "ontology_element",
                "workload_obligation",
                "implementation_binding",
                "action_plan",
                "attempt_manifest",
                "runtime_session",
                "hardware_environment",
                "artifact_record",
                "check_record",
                "comparison",
                "discrepancy",
                "acceptance_decision",
                "tool_call",
                "stage_span",
                "human_intervention",
                "resource_sample",
                "telemetry_summary",
                "experiment_condition",
                "trial_summary",
            },
        )


if __name__ == "__main__":
    unittest.main()

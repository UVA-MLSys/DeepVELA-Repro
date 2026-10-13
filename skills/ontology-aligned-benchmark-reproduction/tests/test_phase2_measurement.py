import tempfile
import unittest
from pathlib import Path

from _fixture import SCRIPTS, build_campaign  # noqa: F401
from ingest_agent_trace import adapt_cumulative_usage
from materialize_experiment_condition import materialize
from seal_benchmark_assessment import seal
from summarize_telemetry import summarize
from validate_ontology_graph import validate


class PhaseTwoMeasurementTest(unittest.TestCase):
    def test_cumulative_usage_is_converted_to_deltas(self):
        events = adapt_cumulative_usage(
            [
                {"usage": {"input_tokens": 100, "output_tokens": 10}},
                {"usage": {"input_tokens": 150, "output_tokens": 30, "cached_input_tokens": 20}},
            ],
            "execution",
            "codex_jsonl",
            "session:test",
        )
        summary = summarize(events)
        self.assertEqual(summary["input_tokens"], 150)
        self.assertEqual(summary["output_tokens"], 30)
        self.assertEqual(summary["cached_input_tokens"], 20)

    def test_resource_measurements_survive_overhead_exclusion(self):
        events = [
            {
                "event_id": "span:one",
                "event_type": "stage_span",
                "stage": "execution",
                "classification": "benchmark_execution",
                "duration_seconds": 10,
                "instrumentation": False,
            },
            {
                "event_id": "resource:one",
                "event_type": "resource_sample",
                "observations": {
                    "gpu_memory_used_mib": {"value": 2048, "unit": "MiB", "aggregation": "max"}
                },
                "instrumentation": True,
            },
        ]
        summary = summarize(events)
        self.assertEqual(summary["included_events"], 1)
        self.assertEqual(summary["excluded_instrumentation_events"], 1)
        self.assertEqual(summary["timing_seconds"]["benchmark_execution"], 10)
        self.assertEqual(summary["resource_summary"]["gpu_memory_used_mib"]["value"], 2048)

    def test_condition_bundle_excludes_withheld_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = build_campaign(base / "campaign")
            source = base / "source"
            source.mkdir()
            (source / "public.txt").write_text("public", encoding="utf-8")
            (source / "secret.txt").write_text("secret", encoding="utf-8")
            path = materialize(
                root,
                source,
                {
                    "condition_id": "condition:test",
                    "trial_id": "trial:test",
                    "controller_realization": "procedural_skill",
                    "benchmark_readiness_condition": "full",
                    "visible_paths": ["public.txt"],
                    "withheld_paths": ["secret.txt"],
                    "withheld_ontology_elements": ["reference_solution"],
                    "visible_ontology_elements": ["dataset"],
                    "visible_source_ids": ["source:public"],
                    "hidden_source_ids": ["source:secret"],
                    "agent_configuration": {},
                    "source_access": [],
                    "tool_access": [],
                    "budgets": {},
                    "intervention_policy": {},
                },
            )
            self.assertTrue((path / "visible" / "public.txt").is_file())
            self.assertFalse((path / "visible" / "secret.txt").exists())

    def test_independent_assessment_seal_is_validated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = build_campaign(Path(directory))
            seal(root, "reviewer:test", "checked against rubric")
            report = validate(root)
            self.assertTrue(report["valid"], report["errors"])


if __name__ == "__main__":
    unittest.main()

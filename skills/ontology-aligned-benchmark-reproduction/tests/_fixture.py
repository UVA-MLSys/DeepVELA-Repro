from __future__ import annotations

import argparse
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from _common import write_json_atomic, write_jsonl_atomic
from bootstrap_campaign import bootstrap


def build_campaign(root: Path) -> Path:
    bootstrap(
        argparse.Namespace(
            campaign_root=str(root),
            campaign_id="campaign:test",
            objective="test campaign",
            claim_type="documented_result_reproduction",
            targets=["target:one"],
            permission=[],
            stopping_condition="all targets terminal",
            allowed_disposition=[],
            comparator="relative_tolerance",
            tolerance=0.01,
            join_key=["target_id"],
            result_grain="target",
        )
    )
    target_manifest = {
        "campaign_id": "campaign:test",
        "targets": [
            {
                "target_id": "target:one",
                "result_grain": "target",
                "reference_available": True,
                "required_obligation_ids": ["obligation:one"],
                "required_artifact_roles": ["result"],
            }
        ],
    }
    write_json_atomic(root / "contract" / "target-manifest.json", target_manifest)
    write_jsonl_atomic(
        root / "ontology" / "obligations.jsonl",
        [
            {
                "obligation_id": "obligation:one",
                "predicate": "metric uses the declared evaluator",
                "severity": "required",
                "source_ids": ["source:one"],
                "target_ids": ["target:one"],
                "required_evidence_roles": ["result"],
                "depends_on": [],
                "status": "verified",
            }
        ],
    )
    write_jsonl_atomic(
        root / "ontology" / "bindings.jsonl",
        [
            {
                "binding_id": "binding:one",
                "obligation_ids": ["obligation:one"],
                "binding_type": "evaluator",
                "identity": "evaluator.py@digest",
                "source_ids": ["source:one"],
            }
        ],
    )
    write_json_atomic(
        root / "planning" / "action-plan.json",
        {
            "action_plan_id": "plan:one",
            "campaign_id": "campaign:test",
            "actions": [
                {
                    "action_id": "action:one",
                    "binding_ids": ["binding:one"],
                    "obligation_ids": ["obligation:one"],
                    "target_ids": ["target:one"],
                    "consumes": [],
                    "expected_artifacts": ["result"],
                    "effects": [],
                    "retry_limit": 1,
                }
            ],
        },
    )
    write_json_atomic(
        root / "attempts" / "attempt_one" / "attempt-manifest.json",
        {
            "attempt_id": "attempt:one",
            "action_plan_id": "plan:one",
            "action_id": "action:one",
            "obligation_ids": ["obligation:one"],
            "target_ids": ["target:one"],
            "input_digests": {},
            "effective_configuration": {},
            "runtime_session_id": "runtime:one",
            "hardware_environment_id": "hardware:one",
            "status": "succeeded",
            "created_at": "2026-01-01T00:00:00Z",
            "started_at": "2026-01-01T00:00:00Z",
            "ended_at": "2026-01-01T00:01:00Z"
        },
    )
    write_jsonl_atomic(
        root / "verification" / "artifacts.jsonl",
        [
            {
                "artifact_id": "artifact:actual",
                "role": "result",
                "producer_attempt_id": "attempt:one",
                "target_ids": ["target:one"],
                "path": "attempts/attempt_one/artifacts/result.json",
                "sha256": "a" * 64,
                "dependencies": ["binding:one"],
                "read_back": True,
                "status": "current",
            },
            {
                "artifact_id": "artifact:reference",
                "role": "reference",
                "producer_attempt_id": "attempt:reference",
                "target_ids": ["target:one"],
                "path": "sources/reference.json",
                "sha256": "b" * 64,
                "dependencies": ["source:one"],
                "read_back": True,
                "status": "current",
            },
        ],
    )
    write_jsonl_atomic(
        root / "verification" / "checks.jsonl",
        [
            {
                "check_id": "check:one",
                "procedure": "declared evaluator",
                "artifact_ids": ["artifact:actual"],
                "obligation_ids": ["obligation:one"],
                "target_ids": ["target:one"],
                "result": "pass",
                "verifier_identity": "verifier:one",
                "verifier_version": "1",
                "current": True,
            }
        ],
    )
    write_jsonl_atomic(
        root / "verification" / "comparisons.jsonl",
        [
            {
                "comparison_id": "comparison:one",
                "target_id": "target:one",
                "actual_artifact_id": "artifact:actual",
                "reference_artifact_id": "artifact:reference",
                "comparator": "relative_tolerance",
                "tolerance": 0.01,
                "grain": "target",
                "values": [],
                "decision": "pass",
                "current": True,
            }
        ],
    )
    state = {
        "campaign_id": "campaign:test",
        "phase": "verification",
        "record_digests": {},
        "counts": {"targets": 1},
        "unresolved_decisions": [],
        "invalidated_ids": [],
        "next_action": "compute acceptance",
        "updated_at": "2026-01-01T00:01:00Z",
    }
    write_json_atomic(root / "state" / "campaign-state.json", state)
    return root

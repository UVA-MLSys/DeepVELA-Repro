#!/usr/bin/env python3
"""Create a benchmark-neutral ontology campaign workspace."""

from __future__ import annotations

import argparse
from pathlib import Path

from _common import utc_now, write_json_atomic


MLCOMMONS_RUBRIC = {
    "software_environment": [
        ("baseline_code_available", 1),
        ("code_complete", 1),
        ("code_documented", 1),
        ("runs_without_modification", 1),
        ("environment_reproducibly_specified", 1),
    ],
    "problem_specification": [
        ("system_constraints_specified", 1),
        ("benchmark_task_clear", 1),
        ("dataset_format_specified", 1),
        ("task_inputs_specified", 1),
        ("task_outputs_specified", 1),
    ],
    "dataset": [
        ("findable", 1),
        ("accessible", 1),
        ("interoperable", 1),
        ("reusable", 1),
        ("canonical_splits_defined", 1),
    ],
    "performance_metrics": [
        ("metric_definitions", 3),
        ("metric_quality", 2),
    ],
    "reference_solution": [
        ("publicly_available", 1),
        ("well_documented", 1),
        ("requirements_listed", 1),
        ("all_metrics_evaluated", 1),
        ("baseline_open_for_study", 1),
    ],
    "documentation": [
        ("task_documented", 1),
        ("background_explained", 1),
        ("motivation_explained", 1),
        ("evaluation_criteria_explained", 1),
        ("academic_paper_exists", 1),
    ],
}

DIRECTORIES = [
    "contract",
    "ontology",
    "sources/retrieved-materials",
    "planning",
    "runtimes",
    "attempts",
    "verification",
    "decisions",
    "state",
    "telemetry",
    "experiment",
    "reports",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign_root")
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--objective", required=True)
    parser.add_argument(
        "--claim-type",
        choices=[
            "documented_result_reproduction",
            "conformance_only",
            "negative_reproducibility_study",
        ],
        required=True,
    )
    parser.add_argument("--target", action="append", required=True, dest="targets")
    parser.add_argument("--permission", action="append", default=[])
    parser.add_argument("--stopping-condition", required=True, help="human-readable description; executable predicates are generated separately")
    parser.add_argument(
        "--allowed-disposition",
        action="append",
        choices=["accepted", "rejected", "inconclusive", "blocked"],
        default=[],
    )
    parser.add_argument("--comparator", choices=["exact", "absolute_tolerance", "relative_tolerance"], required=True)
    parser.add_argument("--verification-rationale", required=True)
    parser.add_argument("--reference-source-id", action="append", default=[])
    parser.add_argument("--tolerance", type=float)
    parser.add_argument("--join-key", action="append", default=["target_id"])
    parser.add_argument("--result-grain", default="target")
    return parser.parse_args()


def bootstrap(args: argparse.Namespace) -> Path:
    root = Path(args.campaign_root).expanduser().resolve()
    contract_path = root / "contract" / "campaign-contract.json"
    if contract_path.exists():
        raise ValueError(f"campaign already exists: {contract_path}")
    if args.comparator != "exact" and args.tolerance is None:
        raise ValueError("non-exact comparators require --tolerance")
    if args.tolerance is not None and args.tolerance < 0:
        raise ValueError("tolerance must be non-negative")

    for relative in DIRECTORIES:
        (root / relative).mkdir(parents=True, exist_ok=True)

    now = utc_now()
    dispositions = args.allowed_disposition or ["accepted", "rejected", "inconclusive", "blocked"]
    write_json_atomic(
        contract_path,
        {
            "campaign_id": args.campaign_id,
            "objective": args.objective,
            "claim_type": args.claim_type,
            "target_ids": args.targets,
            "permissions": args.permission,
            "budgets": {},
            "retry_policy": {},
            "human_decision_boundaries": [],
            "allowed_terminal_dispositions": dispositions,
            "stopping_condition": {
                "description": args.stopping_condition,
                "mode": "all",
                "predicates": [
                    {
                        "predicate_id": "stop:targets-terminal",
                        "predicate_type": "all_targets_terminal",
                        "parameters": {"allowed_dispositions": dispositions},
                        "required_evidence_ids": [],
                    },
                    {
                        "predicate_id": "stop:graph-valid",
                        "predicate_type": "ontology_graph_valid",
                        "parameters": {},
                        "required_evidence_ids": [],
                    },
                    {
                        "predicate_id": "stop:no-critical-discrepancies",
                        "predicate_type": "no_active_critical_discrepancies",
                        "parameters": {},
                        "required_evidence_ids": [],
                    },
                    {
                        "predicate_id": "stop:no-active-invalidations",
                        "predicate_type": "no_active_invalidations",
                        "parameters": {},
                        "required_evidence_ids": [],
                    },
                    {
                        "predicate_id": "stop:obligations-verified",
                        "predicate_type": "all_required_obligations_verified",
                        "parameters": {},
                        "required_evidence_ids": [],
                    },
                ],
                "frozen_at": now,
                "amendments": [],
            },
            "created_at": now,
        },
    )
    write_json_atomic(
        root / "contract" / "target-manifest.json",
        {
            "campaign_id": args.campaign_id,
            "targets": [
                {
                    "target_id": target,
                    "result_grain": args.result_grain,
                    "reference_available": args.claim_type != "conformance_only",
                    "required_obligation_ids": [],
                    "required_artifact_roles": [],
                }
                for target in args.targets
            ],
        },
    )
    write_json_atomic(
        root / "contract" / "benchmark-assessment.json",
        {
            "assessment_id": f"assessment:{args.campaign_id}",
            "campaign_id": args.campaign_id,
            "categories": [
                {
                    "name": category,
                    "score": 0,
                    "criteria": [
                        {
                            "criterion_id": criterion_id,
                            "max_points": max_points,
                            "awarded_points": 0,
                            "met": False,
                            "evidence_source_ids": [],
                            "rationale": "not assessed",
                        }
                        for criterion_id, max_points in criteria
                    ],
                    "gaps": ["not_assessed"],
                }
                for category, criteria in MLCOMMONS_RUBRIC.items()
            ],
            "overall_score": 0,
            "status": "placeholder",
            "rubric_identity": {
                "title": "An MLCommons Scientific Benchmarks Ontology",
                "version": "arXiv:2511.05614v1",
                "source_locator": "https://arxiv.org/abs/2511.05614",
            },
            "assessor": {"identity": "unassigned", "independent_of_execution": False},
        },
    )
    write_json_atomic(
        root / "contract" / "verification-policy.json",
        {
            "policy_id": f"verification:{args.campaign_id}:v1",
            "comparator": args.comparator,
            "join_keys": args.join_key,
            "result_grain": args.result_grain,
            "replicate_design": {},
            "seed_policy": {},
            "aggregation": {},
            "uncertainty_procedure": {},
            "selection_rationale": args.verification_rationale,
            "selected_before_result_inspection": True,
            "reference_source_ids": args.reference_source_id,
            "tolerance": args.tolerance,
            "missing_result_behavior": "fail",
            "allowed_dispositions": dispositions,
            "frozen_at": now,
            "amendments": [],
        },
    )
    write_json_atomic(
        root / "sources" / "source-manifest.json",
        {"campaign_id": args.campaign_id, "sources": []},
    )
    write_json_atomic(
        root / "state" / "campaign-state.json",
        {
            "campaign_id": args.campaign_id,
            "phase": "scope",
            "record_digests": {},
            "counts": {"targets": len(args.targets)},
            "unresolved_decisions": [],
            "invalidated_ids": [],
            "next_action": "complete benchmark readiness assessment and ontology",
            "updated_at": now,
        },
    )
    for relative in [
        "ontology/elements.jsonl",
        "ontology/obligations.jsonl",
        "ontology/bindings.jsonl",
        "ontology/relations.jsonl",
        "sources/conflicts.jsonl",
        "verification/checks.jsonl",
        "verification/artifacts.jsonl",
        "verification/comparisons.jsonl",
        "verification/discrepancies.jsonl",
        "decisions/acceptance-decisions.jsonl",
        "decisions/human-decisions.jsonl",
        "state/invalidations.jsonl",
        "telemetry/events.jsonl",
    ]:
        (root / relative).touch(exist_ok=True)
    return root


def main() -> int:
    args = parse_args()
    try:
        root = bootstrap(args)
    except ValueError as error:
        print(f"error: {error}")
        return 2
    print(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

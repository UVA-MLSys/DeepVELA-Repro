#!/usr/bin/env python3
"""Create a benchmark-neutral ontology campaign workspace."""

from __future__ import annotations

import argparse
from pathlib import Path

from _common import utc_now, write_json_atomic


CATEGORIES = [
    "software_environment",
    "problem_specification",
    "dataset",
    "performance_metrics",
    "reference_solution",
    "documentation",
]

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
    parser.add_argument("--stopping-condition", required=True)
    parser.add_argument(
        "--allowed-disposition",
        action="append",
        choices=["accepted", "rejected", "inconclusive", "blocked"],
        default=[],
    )
    parser.add_argument("--comparator", choices=["exact", "absolute_tolerance", "relative_tolerance"], default="exact")
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
            "stopping_condition": args.stopping_condition,
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
                {"name": category, "score": 0, "subcategories": [], "citations": [], "gaps": ["not_assessed"]}
                for category in CATEGORIES
            ],
            "overall_score": 0,
            "status": "placeholder",
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

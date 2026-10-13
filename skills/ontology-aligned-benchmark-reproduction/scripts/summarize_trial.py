#!/usr/bin/env python3
"""Create one normalized, cross-condition summary from campaign records."""

from __future__ import annotations

import argparse
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

from _common import (
    find_json_records,
    read_json,
    read_json_if_exists,
    read_jsonl,
    require_campaign_root,
    sha256_file,
    utc_now,
    validate_schema_record,
    write_json_atomic,
)
from summarize_telemetry import summarize


def ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def percentage_differences(comparisons: list[dict[str, Any]]) -> list[float]:
    values = []
    for comparison in comparisons:
        for row in comparison.get("values", []):
            actual, reference = row.get("actual"), row.get("reference")
            if isinstance(actual, (int, float)) and isinstance(reference, (int, float)) and reference != 0:
                values.append(abs(float(actual) - float(reference)) / abs(float(reference)) * 100.0)
    return values


def file_digests(root: Path, relatives: list[str]) -> dict[str, str]:
    return {relative: sha256_file(root / relative) for relative in relatives if (root / relative).is_file()}


def build_summary(root: Path, trial_id: str, condition_id: str, controller_realization: str) -> dict:
    contract = read_json(root / "contract" / "campaign-contract.json")
    assessment = read_json(root / "contract" / "benchmark-assessment.json")
    targets = read_json(root / "contract" / "target-manifest.json")["targets"]
    decisions = [record for record in read_jsonl(root / "decisions" / "acceptance-decisions.jsonl") if record.get("current")]
    comparisons = [record for record in read_jsonl(root / "verification" / "comparisons.jsonl") if record.get("current")]
    checks = [record for record in read_jsonl(root / "verification" / "checks.jsonl") if record.get("current")]
    artifacts = [record for record in read_jsonl(root / "verification" / "artifacts.jsonl") if record.get("status") == "current" and record.get("read_back")]
    invalidations = read_jsonl(root / "state" / "invalidations.jsonl")
    attempts = [record for record in find_json_records(root / "attempts") if "attempt_id" in record]
    telemetry_path = root / "telemetry" / "telemetry-summary.json"
    telemetry = read_json(telemetry_path) if telemetry_path.exists() else summarize(read_jsonl(root / "telemetry" / "events.jsonl"))

    disposition_counts = Counter(record["disposition"] for record in decisions)
    comparison_counts = Counter(record["decision"] for record in comparisons)
    differences = percentage_differences(comparisons)
    required_obligations = {value for target in targets for value in target.get("required_obligation_ids", [])}
    verified_obligations = {
        value for check in checks if check.get("result") == "pass" for value in check.get("obligation_ids", [])
    } & required_obligations
    required_roles = {value for target in targets for value in target.get("required_artifact_roles", [])}
    present_roles = {record.get("role") for record in artifacts} & required_roles
    attempts_by_action = Counter(record.get("action_id") for record in attempts)
    redundant_attempts = sum(max(0, count - 1) for count in attempts_by_action.values())

    summary = {
        "schema_version": "1.0",
        "trial_id": trial_id,
        "condition_id": condition_id,
        "campaign_id": contract["campaign_id"],
        "controller_realization": controller_realization,
        "benchmark_readiness_score": assessment.get("overall_score"),
        "target_count": len(targets),
        "disposition_counts": {key: int(disposition_counts.get(key, 0)) for key in ["accepted", "rejected", "inconclusive", "blocked"]},
        "reproduction_quality": {
            "comparisons": len(comparisons),
            "passed": int(comparison_counts.get("pass", 0)),
            "failed": int(comparison_counts.get("fail", 0)),
            "inconclusive": int(comparison_counts.get("inconclusive", 0)),
            "mean_absolute_percentage_difference": statistics.fmean(differences) if differences else None,
            "maximum_absolute_percentage_difference": max(differences) if differences else None,
        },
        "evidence_coverage": {
            "required_obligations": len(required_obligations),
            "verified_obligations": len(verified_obligations),
            "obligation_ratio": ratio(len(verified_obligations), len(required_obligations)),
            "required_artifact_roles": len(required_roles),
            "present_artifact_roles": len(present_roles),
            "artifact_role_ratio": ratio(len(present_roles), len(required_roles)),
        },
        "tool_calls": int(telemetry.get("tool_calls", 0)),
        "input_tokens": telemetry.get("input_tokens"),
        "output_tokens": telemetry.get("output_tokens"),
        "cached_input_tokens": telemetry.get("cached_input_tokens"),
        "reasoning_tokens": telemetry.get("reasoning_tokens"),
        "retries": int(telemetry.get("retries", 0)),
        "errors": int(telemetry.get("failures", 0)),
        "human_interventions": int(telemetry.get("human_interventions", 0)),
        "timing_seconds": telemetry.get("timing_seconds", {}),
        "resource_use": telemetry.get("resource_summary", {}),
        "invalidation_outcomes": {
            "active": sum(record.get("status") == "active" for record in invalidations),
            "resolved": sum(record.get("status") == "resolved" for record in invalidations),
            "unique_invalidated_ids": len({value for record in invalidations for value in record.get("invalidated_ids", [])}),
            "redundant_attempts": redundant_attempts,
        },
        "source_digests": file_digests(
            root,
            [
                "contract/campaign-contract.json",
                "contract/benchmark-assessment.json",
                "contract/target-manifest.json",
                "contract/verification-policy.json",
                "sources/source-manifest.json",
            ],
        ),
        "generated_at": utc_now(),
    }
    errors = validate_schema_record(summary, "trial_summary")
    if errors:
        raise ValueError("trial summary schema failure: " + "; ".join(errors))
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign_root")
    parser.add_argument("--trial-id", required=True)
    parser.add_argument("--condition-id", required=True)
    parser.add_argument("--controller-realization", required=True)
    parser.add_argument("--output")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        root = require_campaign_root(args.campaign_root)
        summary = build_summary(root, args.trial_id, args.condition_id, args.controller_realization)
        output = Path(args.output) if args.output else root / "experiment" / "trial-summary.json"
        write_json_atomic(output, summary)
    except (KeyError, OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}")
        return 2
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

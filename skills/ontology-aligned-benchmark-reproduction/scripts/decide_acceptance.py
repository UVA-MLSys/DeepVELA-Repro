#!/usr/bin/env python3
"""Compute target acceptance from current obligations and evidence."""

from __future__ import annotations

import argparse
import uuid
from pathlib import Path
from typing import Any

from _common import find_json_records, read_json, read_jsonl, require_campaign_root, utc_now, write_jsonl_atomic


def applicable(record: dict[str, Any], target_id: str) -> bool:
    target_ids = record.get("target_ids", [])
    return not target_ids or target_id in target_ids


def compute_decisions(root: Path) -> list[dict[str, Any]]:
    contract = read_json(root / "contract" / "campaign-contract.json")
    targets = read_json(root / "contract" / "target-manifest.json")["targets"]
    checks = read_jsonl(root / "verification" / "checks.jsonl")
    comparisons = read_jsonl(root / "verification" / "comparisons.jsonl")
    discrepancies = read_jsonl(root / "verification" / "discrepancies.jsonl")
    artifacts = read_jsonl(root / "verification" / "artifacts.jsonl")
    attempts = [record for record in find_json_records(root / "attempts") if "attempt_id" in record]
    decisions: list[dict[str, Any]] = []

    for target in targets:
        target_id = target["target_id"]
        required = set(target.get("required_obligation_ids", []))
        target_checks = [record for record in checks if record.get("current") and applicable(record, target_id)]
        passing_obligations = {
            obligation_id
            for record in target_checks
            if record.get("result") == "pass"
            for obligation_id in record.get("obligation_ids", [])
        }
        supporting_checks = sorted(
            record["check_id"]
            for record in target_checks
            if record.get("result") == "pass" and required.intersection(record.get("obligation_ids", []))
        )
        valid = bool(required) and required.issubset(passing_obligations)
        completed = any(
            record.get("status") == "succeeded" and target_id in record.get("target_ids", [])
            for record in attempts
        )

        target_comparisons = [record for record in comparisons if record.get("current") and record.get("target_id") == target_id]
        supporting_comparisons = sorted(record["comparison_id"] for record in target_comparisons)
        claim_type = contract["claim_type"]
        if claim_type == "conformance_only":
            agreed: bool | str = "unavailable"
            agreement_satisfied = True
        elif not target_comparisons:
            agreed = False
            agreement_satisfied = False
        else:
            agreed = all(record.get("decision") == "pass" for record in target_comparisons)
            agreement_satisfied = agreed if claim_type == "documented_result_reproduction" else any(
                record.get("decision") == "fail" for record in target_comparisons
            )

        critical = [
            record["discrepancy_id"]
            for record in discrepancies
            if record.get("severity") == "critical"
            and record.get("status") == "open"
            and applicable(record, target_id)
        ]
        required_roles = set(target.get("required_artifact_roles", []))
        current_artifacts = [
            record
            for record in artifacts
            if record.get("status") == "current" and applicable(record, target_id)
        ]
        available_roles = {record.get("role") for record in current_artifacts if record.get("read_back")}
        artifacts_readable = required_roles.issubset(available_roles)
        rationale = []
        if not completed:
            rationale.append("no succeeded attempt is linked to this target")
        missing_obligations = sorted(required - passing_obligations)
        if missing_obligations:
            rationale.append(f"required obligations lack current passing checks: {missing_obligations}")
        if not agreement_satisfied:
            rationale.append("declared agreement policy is not satisfied")
        if critical:
            rationale.append(f"unresolved critical discrepancies: {critical}")
        missing_roles = sorted(required_roles - available_roles)
        if missing_roles:
            rationale.append(f"required readable artifact roles are missing: {missing_roles}")

        if critical:
            disposition = "blocked"
        elif not completed or not required or not artifacts_readable:
            disposition = "inconclusive"
        elif not valid or not agreement_satisfied:
            disposition = "rejected"
        else:
            disposition = "accepted"
        decisions.append(
            {
                "decision_id": f"acceptance:{target_id}:{uuid.uuid4()}",
                "target_id": target_id,
                "required_obligation_ids": sorted(required),
                "supporting_check_ids": supporting_checks,
                "supporting_comparison_ids": supporting_comparisons,
                "completed": completed,
                "valid": valid,
                "agreed": agreed,
                "canonical": disposition == "accepted",
                "artifacts_readable": artifacts_readable,
                "disposition": disposition,
                "rationale": rationale or ["all declared acceptance conditions are satisfied"],
                "current": True,
                "created_at": utc_now(),
            }
        )
    return decisions


def persist(root: Path, new_decisions: list[dict[str, Any]]) -> None:
    path = root / "decisions" / "acceptance-decisions.jsonl"
    old = read_jsonl(path)
    target_ids = {record["target_id"] for record in new_decisions}
    for record in old:
        if record.get("target_id") in target_ids and record.get("current"):
            record["current"] = False
    write_jsonl_atomic(path, [*old, *new_decisions])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign_root")
    return parser.parse_args()


def main() -> int:
    try:
        root = require_campaign_root(parse_args().campaign_root)
        decisions = compute_decisions(root)
        persist(root, decisions)
    except (KeyError, OSError, ValueError) as error:
        print(f"error: {error}")
        return 2
    counts: dict[str, int] = {}
    for decision in decisions:
        counts[decision["disposition"]] = counts.get(decision["disposition"], 0) + 1
    print(" ".join(f"{key}={value}" for key, value in sorted(counts.items())))
    return 0 if all(record["disposition"] == "accepted" for record in decisions) else 1


if __name__ == "__main__":
    raise SystemExit(main())

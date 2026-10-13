#!/usr/bin/env python3
"""Close a campaign only when current evidence proves its terminal state."""

from __future__ import annotations

import argparse
from pathlib import Path

from _common import invalidated_ids, read_json, read_jsonl, require_campaign_root, utc_now, write_json_atomic
from decide_acceptance import compute_decisions, persist
from validate_ontology_graph import validate


def evaluate_stopping_condition(root: Path, contract: dict, decisions: list[dict], graph_report: dict) -> dict:
    discrepancies = read_jsonl(root / "verification" / "discrepancies.jsonl")
    current_evidence_ids = {
        record.get("check_id") for record in read_jsonl(root / "verification" / "checks.jsonl") if record.get("current")
    } | {
        record.get("comparison_id") for record in read_jsonl(root / "verification" / "comparisons.jsonl") if record.get("current")
    }
    results = []
    for predicate in contract["stopping_condition"]["predicates"]:
        kind = predicate["predicate_type"]
        parameters = predicate.get("parameters", {})
        evidence_present = set(predicate.get("required_evidence_ids", [])).issubset(current_evidence_ids)
        if kind == "all_targets_terminal":
            allowed = set(parameters.get("allowed_dispositions", contract["allowed_terminal_dispositions"]))
            satisfied = bool(decisions) and all(record["disposition"] in allowed for record in decisions)
        elif kind == "ontology_graph_valid":
            satisfied = bool(graph_report["valid"])
        elif kind == "no_active_critical_discrepancies":
            satisfied = not any(
                record.get("status") == "open" and record.get("severity") == "critical" for record in discrepancies
            )
        elif kind == "no_active_invalidations":
            satisfied = not invalidated_ids(root)
        elif kind == "all_required_obligations_verified":
            satisfied = bool(decisions) and all(record["valid"] for record in decisions)
        elif kind == "custom":
            satisfied = bool(parameters.get("human_confirmed", False)) and evidence_present
        else:  # protected by schema validation
            satisfied = False
        results.append(
            {
                "predicate_id": predicate["predicate_id"],
                "predicate_type": kind,
                "satisfied": bool(satisfied and evidence_present),
                "required_evidence_present": evidence_present,
            }
        )
    mode = contract["stopping_condition"]["mode"]
    proven = all(item["satisfied"] for item in results) if mode == "all" else any(item["satisfied"] for item in results)
    return {"mode": mode, "proven": proven, "predicates": results}


def close(root: Path) -> dict:
    contract = read_json(root / "contract" / "campaign-contract.json")
    decisions = compute_decisions(root)
    persist(root, decisions)
    report = validate(root, "verification")
    if not report["valid"]:
        raise ValueError(f"ontology graph is invalid: {len(report['errors'])} error(s)")
    allowed = set(contract["allowed_terminal_dispositions"])
    invalid = [record for record in decisions if record["disposition"] not in allowed]
    if invalid:
        raise ValueError(f"targets have disallowed dispositions: {[record['target_id'] for record in invalid]}")
    stopping_proof = evaluate_stopping_condition(root, contract, decisions, report)
    if not stopping_proof["proven"]:
        failed = [item["predicate_id"] for item in stopping_proof["predicates"] if not item["satisfied"]]
        raise ValueError(f"stopping condition is not proven: {failed}")

    counts: dict[str, int] = {}
    for decision in decisions:
        counts[decision["disposition"]] = counts.get(decision["disposition"], 0) + 1
    result = {
        "campaign_id": contract["campaign_id"],
        "objective": contract["objective"],
        "claim_type": contract["claim_type"],
        "stopping_condition": contract["stopping_condition"],
        "disposition_counts": counts,
        "target_decisions": decisions,
        "ontology_validation": report,
        "stopping_proof": stopping_proof,
        "closed_at": utc_now(),
    }
    write_json_atomic(root / "reports" / "result-report.json", result)
    lines = [
        f"# Campaign {contract['campaign_id']}",
        "",
        contract["objective"],
        "",
        "## Dispositions",
        "",
        *[f"- `{key}`: {value}" for key, value in sorted(counts.items())],
        "",
        f"Closed at: {result['closed_at']}",
    ]
    (root / "reports" / "result-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    state = read_json(root / "state" / "campaign-state.json")
    state.update({"phase": "closed", "next_action": None, "updated_at": result["closed_at"], "counts": {**state.get("counts", {}), **counts}})
    write_json_atomic(root / "state" / "campaign-state.json", state)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign_root")
    return parser.parse_args()


def main() -> int:
    try:
        result = close(require_campaign_root(parse_args().campaign_root))
    except (KeyError, OSError, ValueError) as error:
        print(f"error: {error}")
        return 1
    print(f"closed {result['campaign_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Close a campaign only when current evidence proves its terminal state."""

from __future__ import annotations

import argparse
from pathlib import Path

from _common import read_json, read_jsonl, require_campaign_root, utc_now, write_json_atomic
from decide_acceptance import compute_decisions, persist
from validate_ontology_graph import validate


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
    if any(record["disposition"] in {"blocked", "inconclusive"} for record in decisions):
        raise ValueError("campaign has blocked or inconclusive targets and cannot satisfy strict closure")

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

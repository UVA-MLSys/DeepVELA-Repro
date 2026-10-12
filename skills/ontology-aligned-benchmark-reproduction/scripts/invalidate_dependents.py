#!/usr/bin/env python3
"""Compute dependency closure and mark dependent evidence stale."""

from __future__ import annotations

import argparse
import uuid
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from _common import append_jsonl, read_json, read_jsonl, require_campaign_root, utc_now, write_jsonl_atomic


COLLECTIONS = [
    ("ontology/obligations.jsonl", "obligation_id", "status", "stale"),
    ("verification/artifacts.jsonl", "artifact_id", "status", "stale"),
    ("verification/checks.jsonl", "check_id", "current", False),
    ("verification/comparisons.jsonl", "comparison_id", "current", False),
    ("decisions/acceptance-decisions.jsonl", "decision_id", "current", False),
]


def build_graph(root: Path) -> dict[str, set[str]]:
    graph: dict[str, set[str]] = defaultdict(set)
    for relation in read_jsonl(root / "ontology" / "relations.jsonl"):
        source = relation.get("source_id") or relation.get("from_id")
        target = relation.get("target_id") or relation.get("to_id")
        if source and target:
            graph[str(source)].add(str(target))
    for obligation in read_jsonl(root / "ontology" / "obligations.jsonl"):
        for dependency in obligation.get("depends_on", []):
            graph[str(dependency)].add(obligation["obligation_id"])
    for binding in read_jsonl(root / "ontology" / "bindings.jsonl"):
        for obligation_id in binding.get("obligation_ids", []):
            graph[str(obligation_id)].add(binding["binding_id"])
    plan_path = root / "planning" / "action-plan.json"
    if plan_path.exists():
        for action in read_json(plan_path).get("actions", []):
            for parent in [*action.get("binding_ids", []), *action.get("obligation_ids", []), *action.get("consumes", [])]:
                graph[str(parent)].add(action["action_id"])
    for artifact in read_jsonl(root / "verification" / "artifacts.jsonl"):
        for dependency in artifact.get("dependencies", []):
            graph[str(dependency)].add(artifact["artifact_id"])
    for check in read_jsonl(root / "verification" / "checks.jsonl"):
        for parent in [*check.get("artifact_ids", []), *check.get("obligation_ids", [])]:
            graph[str(parent)].add(check["check_id"])
    for comparison in read_jsonl(root / "verification" / "comparisons.jsonl"):
        for parent in [comparison.get("actual_artifact_id"), comparison.get("reference_artifact_id")]:
            if parent:
                graph[str(parent)].add(comparison["comparison_id"])
    for decision in read_jsonl(root / "decisions" / "acceptance-decisions.jsonl"):
        for parent in [*decision.get("supporting_check_ids", []), *decision.get("supporting_comparison_ids", [])]:
            graph[str(parent)].add(decision["decision_id"])
    return graph


def descendants(graph: dict[str, set[str]], roots: list[str]) -> set[str]:
    seen = set(roots)
    queue = deque(roots)
    result: set[str] = set()
    while queue:
        node = queue.popleft()
        for child in graph.get(node, set()):
            if child in seen:
                continue
            seen.add(child)
            result.add(child)
            queue.append(child)
    return result


def apply_stale_marks(root: Path, stale_ids: set[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for relative, id_key, state_key, stale_value in COLLECTIONS:
        path = root / relative
        records = read_jsonl(path)
        changed = 0
        for record in records:
            if record.get(id_key) in stale_ids and record.get(state_key) != stale_value:
                record[state_key] = stale_value
                changed += 1
        if changed:
            write_jsonl_atomic(path, records)
        counts[relative] = changed
    return counts


def invalidate(root: Path, changed_ids: list[str], reason: str, apply: bool) -> dict[str, Any]:
    closure = descendants(build_graph(root), changed_ids)
    counts = apply_stale_marks(root, closure) if apply else {}
    record = {
        "invalidation_id": f"invalidation:{uuid.uuid4()}",
        "changed_ids": changed_ids,
        "invalidated_ids": sorted(closure),
        "reason": reason,
        "status": "active",
        "applied": apply,
        "changed_record_counts": counts,
        "created_at": utc_now(),
    }
    if apply:
        append_jsonl(root / "state" / "invalidations.jsonl", record)
    return record


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign_root")
    parser.add_argument("--changed-id", action="append", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--apply", action="store_true", help="mark records stale and persist the invalidation")
    parser.add_argument("--output")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        root = require_campaign_root(args.campaign_root)
        record = invalidate(root, args.changed_id, args.reason, args.apply)
        if args.output:
            from _common import write_json_atomic
            write_json_atomic(Path(args.output), record)
    except (KeyError, OSError, ValueError) as error:
        print(f"error: {error}")
        return 2
    print(f"invalidated={len(record['invalidated_ids'])} applied={str(args.apply).lower()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

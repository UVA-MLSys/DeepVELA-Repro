#!/usr/bin/env python3
"""Validate campaign records, graph links, and phase-gate invariants."""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
from typing import Any

from _common import find_json_records, index_unique, invalidated_ids, read_json, read_jsonl, require_campaign_root, utc_now, write_json_atomic


PHASE_RANK = {"scope": 0, "ontology": 1, "binding": 2, "execution": 3, "verification": 4, "recovery": 5, "closed": 6}


def issue(code: str, message: str, ids: list[str] | None = None) -> dict[str, Any]:
    return {"code": code, "message": message, "ids": ids or []}


def cycle_nodes(adjacency: dict[str, set[str]]) -> list[str]:
    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []

    def visit(node: str) -> list[str]:
        if node in visiting:
            start = stack.index(node)
            return stack[start:] + [node]
        if node in visited:
            return []
        visiting.add(node)
        stack.append(node)
        for child in adjacency.get(node, set()):
            found = visit(child)
            if found:
                return found
        stack.pop()
        visiting.remove(node)
        visited.add(node)
        return []

    for node in sorted(adjacency):
        found = visit(node)
        if found:
            return found
    return []


def validate(root: Path, phase: str | None = None) -> dict[str, Any]:
    contract = read_json(root / "contract" / "campaign-contract.json")
    targets_doc = read_json(root / "contract" / "target-manifest.json")
    state = read_json(root / "state" / "campaign-state.json")
    phase = phase or state["phase"]
    rank = PHASE_RANK[phase]
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    try:
        targets = index_unique(targets_doc.get("targets", []), "target_id")
        obligations = index_unique(read_jsonl(root / "ontology" / "obligations.jsonl"), "obligation_id")
        bindings = index_unique(read_jsonl(root / "ontology" / "bindings.jsonl"), "binding_id")
        artifacts = index_unique(read_jsonl(root / "verification" / "artifacts.jsonl"), "artifact_id")
        checks = index_unique(read_jsonl(root / "verification" / "checks.jsonl"), "check_id")
        comparisons = index_unique(read_jsonl(root / "verification" / "comparisons.jsonl"), "comparison_id")
        decisions = index_unique(read_jsonl(root / "decisions" / "acceptance-decisions.jsonl"), "decision_id")
    except ValueError as error:
        errors.append(issue("duplicate_or_missing_identity", str(error)))
        targets, obligations, bindings, artifacts, checks, comparisons, decisions = {}, {}, {}, {}, {}, {}, {}

    if set(contract.get("target_ids", [])) != set(targets):
        errors.append(issue("target_scope_mismatch", "contract and target manifest target IDs differ"))

    if rank >= PHASE_RANK["ontology"]:
        for target_id, target in targets.items():
            required = target.get("required_obligation_ids", [])
            if not required:
                errors.append(issue("target_without_obligations", "target has no required obligations", [target_id]))
            missing = sorted(set(required) - set(obligations))
            if missing:
                errors.append(issue("unknown_target_obligation", "target references unknown obligations", [target_id, *missing]))
        for obligation_id, obligation in obligations.items():
            if not obligation.get("source_ids"):
                errors.append(issue("ungrounded_obligation", "obligation has no source grounding", [obligation_id]))
            missing_targets = sorted(set(obligation.get("target_ids", [])) - set(targets))
            if missing_targets:
                errors.append(issue("unknown_obligation_target", "obligation references unknown targets", [obligation_id, *missing_targets]))

    if rank >= PHASE_RANK["binding"]:
        implemented: set[str] = set()
        for binding_id, binding in bindings.items():
            obligation_ids = set(binding.get("obligation_ids", []))
            if not obligation_ids:
                errors.append(issue("binding_without_obligation", "binding implements no obligations", [binding_id]))
            missing = sorted(obligation_ids - set(obligations))
            if missing:
                errors.append(issue("unknown_binding_obligation", "binding references unknown obligations", [binding_id, *missing]))
            implemented.update(obligation_ids)
        required = {value for target in targets.values() for value in target.get("required_obligation_ids", [])}
        missing_bindings = sorted(required - implemented)
        if missing_bindings:
            errors.append(issue("unimplemented_obligation", "required obligations lack implementation bindings", missing_bindings))

        plan_path = root / "planning" / "action-plan.json"
        if not plan_path.exists():
            errors.append(issue("missing_action_plan", "binding phase requires planning/action-plan.json"))
        else:
            plan = read_json(plan_path)
            for action in plan.get("actions", []):
                action_id = action.get("action_id", "<missing>")
                if not action.get("binding_ids") or not action.get("obligation_ids"):
                    errors.append(issue("orphan_action", "action must link bindings and obligations", [action_id]))
                missing_bindings = sorted(set(action.get("binding_ids", [])) - set(bindings))
                missing_obligations = sorted(set(action.get("obligation_ids", [])) - set(obligations))
                if missing_bindings or missing_obligations:
                    errors.append(issue("unresolved_action_links", "action has unresolved graph links", [action_id, *missing_bindings, *missing_obligations]))

    stale = invalidated_ids(root)
    if rank >= PHASE_RANK["verification"]:
        for check_id, check in checks.items():
            missing_artifacts = sorted(set(check.get("artifact_ids", [])) - set(artifacts))
            missing_obligations = sorted(set(check.get("obligation_ids", [])) - set(obligations))
            if missing_artifacts or missing_obligations:
                errors.append(issue("unresolved_check_links", "check references unknown artifacts or obligations", [check_id, *missing_artifacts, *missing_obligations]))
        for artifact_id, artifact in artifacts.items():
            if artifact.get("status") == "current" and not artifact.get("read_back", False):
                errors.append(issue("unreadable_current_artifact", "current artifact did not pass read-back", [artifact_id]))
        for comparison_id, comparison in comparisons.items():
            unknown = [value for value in [comparison.get("actual_artifact_id"), comparison.get("reference_artifact_id")] if value not in artifacts]
            if unknown:
                errors.append(issue("unresolved_comparison_artifact", "comparison references unknown artifacts", [comparison_id, *unknown]))

    for decision_id, decision in decisions.items():
        missing_checks = sorted(set(decision.get("supporting_check_ids", [])) - set(checks))
        missing_comparisons = sorted(set(decision.get("supporting_comparison_ids", [])) - set(comparisons))
        if missing_checks or missing_comparisons:
            errors.append(issue("unsupported_decision", "decision references unknown evidence", [decision_id, *missing_checks, *missing_comparisons]))
        if decision.get("current") and (set(decision.get("supporting_check_ids", [])) & stale or set(decision.get("supporting_comparison_ids", [])) & stale):
            errors.append(issue("decision_uses_stale_evidence", "decision cites invalidated evidence", [decision_id]))

    adjacency: dict[str, set[str]] = defaultdict(set)
    for relation in read_jsonl(root / "ontology" / "relations.jsonl"):
        relation_type = relation.get("relation_type")
        source = relation.get("source_id") or relation.get("from_id")
        target = relation.get("target_id") or relation.get("to_id")
        if source and target and relation_type in {"depends_on", "consumes", "derived_from", "implemented_by", "produces", "verifies"}:
            adjacency[str(source)].add(str(target))
    cycle = cycle_nodes(adjacency)
    if cycle:
        errors.append(issue("dependency_cycle", "dependency relations contain a cycle", cycle))

    if not find_json_records(root / "runtimes") and rank >= PHASE_RANK["execution"]:
        warnings.append(issue("no_runtime_records", "execution phase has no runtime-session records"))

    return {
        "campaign_id": contract.get("campaign_id"),
        "phase": phase,
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "counts": {
            "targets": len(targets),
            "obligations": len(obligations),
            "bindings": len(bindings),
            "artifacts": len(artifacts),
            "checks": len(checks),
            "comparisons": len(comparisons),
            "decisions": len(decisions),
        },
        "validated_at": utc_now(),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign_root")
    parser.add_argument("--phase", choices=sorted(PHASE_RANK, key=PHASE_RANK.get))
    parser.add_argument("--output")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        root = require_campaign_root(args.campaign_root)
        report = validate(root, args.phase)
        output = Path(args.output) if args.output else root / "reports" / "ontology-validation.json"
        write_json_atomic(output, report)
    except (KeyError, OSError, ValueError) as error:
        print(f"error: {error}")
        return 2
    print(f"valid={str(report['valid']).lower()} errors={len(report['errors'])} warnings={len(report['warnings'])}")
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

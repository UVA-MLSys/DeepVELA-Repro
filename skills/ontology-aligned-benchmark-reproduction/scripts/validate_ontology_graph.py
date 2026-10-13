#!/usr/bin/env python3
"""Validate campaign records, graph links, and phase-gate invariants."""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
from typing import Any

from _common import (
    canonical_digest,
    find_json_records,
    index_unique,
    invalidated_ids,
    read_json,
    read_jsonl,
    require_campaign_root,
    sha256_file,
    utc_now,
    validate_schema_record,
    write_json_atomic,
)


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


def schema_issue(errors: list[dict[str, Any]], location: str, definition: str, value: Any) -> None:
    for message in validate_schema_record(value, definition):
        errors.append(issue("schema_validation", f"{location} [{definition}]: {message}"))


def artifact_path(root: Path, declared: str) -> Path:
    path = Path(declared)
    return path if path.is_absolute() else root / path


def validate(root: Path, phase: str | None = None) -> dict[str, Any]:
    contract = read_json(root / "contract" / "campaign-contract.json")
    targets_doc = read_json(root / "contract" / "target-manifest.json")
    state = read_json(root / "state" / "campaign-state.json")
    phase = phase or state["phase"]
    rank = PHASE_RANK[phase]
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    try:
        assessment = read_json(root / "contract" / "benchmark-assessment.json")
        policy = read_json(root / "contract" / "verification-policy.json")
        source_manifest = read_json(root / "sources" / "source-manifest.json")
        targets = index_unique(targets_doc.get("targets", []), "target_id")
        sources = index_unique(source_manifest.get("sources", []), "source_id")
        elements = index_unique(read_jsonl(root / "ontology" / "elements.jsonl"), "element_id")
        obligations = index_unique(read_jsonl(root / "ontology" / "obligations.jsonl"), "obligation_id")
        bindings = index_unique(read_jsonl(root / "ontology" / "bindings.jsonl"), "binding_id")
        artifacts = index_unique(read_jsonl(root / "verification" / "artifacts.jsonl"), "artifact_id")
        checks = index_unique(read_jsonl(root / "verification" / "checks.jsonl"), "check_id")
        comparisons = index_unique(read_jsonl(root / "verification" / "comparisons.jsonl"), "comparison_id")
        discrepancies = index_unique(read_jsonl(root / "verification" / "discrepancies.jsonl"), "discrepancy_id")
        decisions = index_unique(read_jsonl(root / "decisions" / "acceptance-decisions.jsonl"), "decision_id")
        attempts = index_unique(
            [record for record in find_json_records(root / "attempts") if "attempt_id" in record], "attempt_id"
        )
        runtime_records = find_json_records(root / "runtimes")
        runtimes = index_unique([record for record in runtime_records if "runtime_session_id" in record and "role" in record], "runtime_session_id")
        hardware = index_unique([record for record in runtime_records if "hardware_environment_id" in record], "hardware_environment_id")
    except ValueError as error:
        errors.append(issue("duplicate_or_missing_identity", str(error)))
        assessment, policy, sources, elements = {}, {}, {}, {}
        targets, obligations, bindings, artifacts, checks, comparisons, discrepancies, decisions = {}, {}, {}, {}, {}, {}, {}, {}
        attempts, runtimes, hardware = {}, {}, {}

    schema_issue(errors, "contract/campaign-contract.json", "campaign_contract", contract)
    schema_issue(errors, "contract/benchmark-assessment.json", "benchmark_assessment", assessment)
    schema_issue(errors, "contract/target-manifest.json", "target_manifest", targets_doc)
    schema_issue(errors, "contract/verification-policy.json", "verification_policy", policy)
    schema_issue(errors, "state/campaign-state.json", "campaign_state", state)
    for source_id, record in sources.items():
        schema_issue(errors, f"sources/source-manifest.json:{source_id}", "source_record", record)
    for element_id, record in elements.items():
        schema_issue(errors, f"ontology/elements.jsonl:{element_id}", "ontology_element", record)
    for obligation_id, record in obligations.items():
        schema_issue(errors, f"ontology/obligations.jsonl:{obligation_id}", "workload_obligation", record)
    for binding_id, record in bindings.items():
        schema_issue(errors, f"ontology/bindings.jsonl:{binding_id}", "implementation_binding", record)
    for artifact_id, record in artifacts.items():
        schema_issue(errors, f"verification/artifacts.jsonl:{artifact_id}", "artifact_record", record)
    for check_id, record in checks.items():
        schema_issue(errors, f"verification/checks.jsonl:{check_id}", "check_record", record)
    for comparison_id, record in comparisons.items():
        schema_issue(errors, f"verification/comparisons.jsonl:{comparison_id}", "comparison", record)
    for discrepancy_id, record in discrepancies.items():
        schema_issue(errors, f"verification/discrepancies.jsonl:{discrepancy_id}", "discrepancy", record)
    for decision_id, record in decisions.items():
        schema_issue(errors, f"decisions/acceptance-decisions.jsonl:{decision_id}", "acceptance_decision", record)
    for attempt_id, record in attempts.items():
        schema_issue(errors, f"attempts:{attempt_id}", "attempt_manifest", record)
    for runtime_id, record in runtimes.items():
        schema_issue(errors, f"runtimes:{runtime_id}", "runtime_session", record)
    for hardware_id, record in hardware.items():
        schema_issue(errors, f"runtimes:{hardware_id}", "hardware_environment", record)
    for invalidation in read_jsonl(root / "state" / "invalidations.jsonl"):
        schema_issue(errors, f"state/invalidations.jsonl:{invalidation.get('invalidation_id')}", "invalidation_record", invalidation)
    for human_decision in read_jsonl(root / "decisions" / "human-decisions.jsonl"):
        schema_issue(errors, f"decisions/human-decisions.jsonl:{human_decision.get('human_decision_id')}", "human_decision_record", human_decision)
    telemetry_definitions = {
        "tool_call": "tool_call",
        "stage_span": "stage_span",
        "human_intervention": "human_intervention",
        "resource_sample": "resource_sample",
        "agent_usage": "agent_usage",
    }
    for event in read_jsonl(root / "telemetry" / "events.jsonl"):
        definition = telemetry_definitions.get(event.get("event_type"))
        if definition:
            schema_issue(errors, f"telemetry/events.jsonl:{event.get('event_id')}", definition, event)
        else:
            errors.append(issue("unknown_telemetry_event", "telemetry event has no registered schema", [str(event.get("event_id"))]))
    summary_path = root / "telemetry" / "telemetry-summary.json"
    if summary_path.exists():
        schema_issue(errors, "telemetry/telemetry-summary.json", "telemetry_summary", read_json(summary_path))
    seal_path = root / "experiment" / "benchmark-assessment-seal.json"
    if seal_path.exists():
        seal = read_json(seal_path)
        schema_issue(errors, "experiment/benchmark-assessment-seal.json", "assessment_seal", seal)
        if seal.get("assessment_sha256") != canonical_digest(assessment):
            errors.append(issue("stale_assessment_seal", "assessment changed after independent review", [str(seal.get("seal_id"))]))
    for condition_path in sorted((root / "experiment" / "conditions").glob("*/condition.json")) if (root / "experiment" / "conditions").exists() else []:
        schema_issue(errors, str(condition_path.relative_to(root)), "experiment_condition", read_json(condition_path))
    for manifest_path in sorted((root / "experiment" / "conditions").glob("*/bundle-manifest.json")) if (root / "experiment" / "conditions").exists() else []:
        manifest = read_json(manifest_path)
        schema_issue(errors, str(manifest_path.relative_to(root)), "condition_bundle_manifest", manifest)
        visible_root = (manifest_path.parent / "visible").resolve()
        observed_files = []
        for item in manifest.get("files", []):
            candidate = (visible_root / item["path"]).resolve()
            try:
                candidate.relative_to(visible_root)
            except ValueError:
                errors.append(issue("condition_path_escape", "bundle manifest path escapes visible root", [item["path"]]))
                continue
            if not candidate.is_file() or sha256_file(candidate) != item.get("sha256"):
                errors.append(issue("condition_bundle_mismatch", "visible condition file is missing or changed", [item["path"]]))
            else:
                observed_files.append(item)
        if canonical_digest(observed_files) != manifest.get("bundle_sha256"):
            errors.append(issue("condition_bundle_digest_mismatch", "condition bundle digest does not match inventory"))
        leaked = [value for value in manifest.get("withheld_paths", []) if (visible_root / value).exists()]
        if leaked or not manifest.get("isolation_verified"):
            errors.append(issue("condition_isolation_failure", "withheld condition content is visible", leaked))
    trial_summary_path = root / "experiment" / "trial-summary.json"
    if trial_summary_path.exists():
        schema_issue(errors, "experiment/trial-summary.json", "trial_summary", read_json(trial_summary_path))

    if set(contract.get("target_ids", [])) != set(targets):
        errors.append(issue("target_scope_mismatch", "contract and target manifest target IDs differ"))

    if rank >= PHASE_RANK["ontology"]:
        if assessment.get("status") != "complete":
            errors.append(issue("incomplete_benchmark_assessment", "ontology phase requires a completed readiness assessment"))
        if not policy.get("selected_before_result_inspection"):
            errors.append(issue("late_verification_policy", "verification policy was not frozen before result inspection"))
        unknown_policy_sources = sorted(set(policy.get("reference_source_ids", [])) - set(sources))
        if unknown_policy_sources:
            errors.append(issue("unknown_policy_source", "verification policy references unknown sources", unknown_policy_sources))
        for source_id, source in sources.items():
            if source.get("status") != "resolved" or not source.get("immutable_identity"):
                errors.append(issue("weak_source_identity", "source is not resolved to an immutable identity", [source_id]))
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
            unknown_sources = sorted(set(obligation.get("source_ids", [])) - set(sources))
            if unknown_sources:
                errors.append(issue("unknown_obligation_source", "obligation references unknown sources", [obligation_id, *unknown_sources]))
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
            unknown_sources = sorted(set(binding.get("source_ids", [])) - set(sources))
            if unknown_sources:
                errors.append(issue("unknown_binding_source", "binding references unknown sources", [binding_id, *unknown_sources]))
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
            schema_issue(errors, "planning/action-plan.json", "action_plan", plan)
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
            if artifact.get("status") == "current":
                path = artifact_path(root, artifact["path"])
                if not path.is_file():
                    errors.append(issue("missing_current_artifact", "current artifact path is not readable", [artifact_id]))
                elif sha256_file(path) != artifact.get("sha256"):
                    errors.append(issue("artifact_digest_mismatch", "current artifact digest does not match bytes on disk", [artifact_id]))
            if artifact.get("storage_kind") == "content_addressed" and artifact.get("cas_uri") != f"sha256:{artifact.get('sha256')}":
                errors.append(issue("invalid_cas_identity", "content-addressed artifact URI does not match its digest", [artifact_id]))
        for comparison_id, comparison in comparisons.items():
            unknown = [value for value in [comparison.get("actual_artifact_id"), comparison.get("reference_artifact_id")] if value not in artifacts]
            if unknown:
                errors.append(issue("unresolved_comparison_artifact", "comparison references unknown artifacts", [comparison_id, *unknown]))

    if rank >= PHASE_RANK["execution"]:
        for attempt_id, attempt in attempts.items():
            if attempt.get("runtime_session_id") not in runtimes:
                errors.append(issue("unknown_attempt_runtime", "attempt references unknown runtime session", [attempt_id]))
            if attempt.get("hardware_environment_id") not in hardware:
                errors.append(issue("unknown_attempt_hardware", "attempt references unknown hardware environment", [attempt_id]))
            unknown_targets = sorted(set(attempt.get("target_ids", [])) - set(targets))
            unknown_obligations = sorted(set(attempt.get("obligation_ids", [])) - set(obligations))
            if unknown_targets or unknown_obligations:
                errors.append(issue("unresolved_attempt_links", "attempt references unknown target or obligation", [attempt_id, *unknown_targets, *unknown_obligations]))

    for decision_id, decision in decisions.items():
        missing_checks = sorted(set(decision.get("supporting_check_ids", [])) - set(checks))
        missing_comparisons = sorted(set(decision.get("supporting_comparison_ids", [])) - set(comparisons))
        if missing_checks or missing_comparisons:
            errors.append(issue("unsupported_decision", "decision references unknown evidence", [decision_id, *missing_checks, *missing_comparisons]))
        if decision.get("current") and (set(decision.get("supporting_check_ids", [])) & stale or set(decision.get("supporting_comparison_ids", [])) & stale):
            errors.append(issue("decision_uses_stale_evidence", "decision cites invalidated evidence", [decision_id]))

    actions: dict[str, dict[str, Any]] = {}
    plan_path = root / "planning" / "action-plan.json"
    if plan_path.exists():
        actions = {record["action_id"]: record for record in read_json(plan_path).get("actions", [])}
    node_types: dict[str, str] = {}
    for kind, records in [
        ("source", sources), ("ontology_element", elements), ("target", targets),
        ("obligation", obligations), ("binding", bindings), ("action", actions),
        ("attempt", attempts), ("runtime", runtimes), ("hardware", hardware),
        ("artifact", artifacts), ("check", checks), ("comparison", comparisons), ("decision", decisions),
    ]:
        for record_id in records:
            if record_id in node_types:
                errors.append(issue("duplicate_graph_identity", "identity is reused across graph node types", [record_id]))
            node_types[record_id] = kind

    adjacency: dict[str, set[str]] = defaultdict(set)
    dependency_relations = {"depends_on", "implemented_by", "planned_by", "consumes", "produces", "verifies", "compares", "supports_decision"}
    for relation in read_jsonl(root / "ontology" / "relations.jsonl"):
        schema_issue(errors, f"ontology/relations.jsonl:{relation.get('relation_id')}", "ontology_relation", relation)
        relation_type = relation.get("relation_type")
        source = relation.get("from_id")
        target = relation.get("to_id")
        unknown = [record_id for record_id in [source, target] if record_id not in node_types]
        if unknown:
            errors.append(issue("unknown_relation_endpoint", "typed relation references an unknown graph node", unknown))
        if source in node_types and relation.get("from_type") != node_types[source]:
            errors.append(issue("relation_type_mismatch", "relation from_type does not match endpoint", [str(source)]))
        if target in node_types and relation.get("to_type") != node_types[target]:
            errors.append(issue("relation_type_mismatch", "relation to_type does not match endpoint", [str(target)]))
        if source and target and relation_type in dependency_relations:
            adjacency[str(source)].add(str(target))
    cycle = cycle_nodes(adjacency)
    if cycle:
        errors.append(issue("dependency_cycle", "dependency relations contain a cycle", cycle))

    if not find_json_records(root / "runtimes") and rank >= PHASE_RANK["execution"]:
        warnings.append(issue("no_runtime_records", "execution phase has no runtime-session records"))

    if phase == "closed" and invalidated_ids(root):
        errors.append(issue("active_invalidations", "closed campaign retains active invalidations", sorted(invalidated_ids(root))))

    return {
        "campaign_id": contract.get("campaign_id"),
        "phase": phase,
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "counts": {
            "targets": len(targets),
            "sources": len(sources),
            "elements": len(elements),
            "obligations": len(obligations),
            "bindings": len(bindings),
            "artifacts": len(artifacts),
            "checks": len(checks),
            "comparisons": len(comparisons),
            "discrepancies": len(discrepancies),
            "decisions": len(decisions),
            "attempts": len(attempts),
            "runtimes": len(runtimes),
            "hardware_environments": len(hardware),
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

#!/usr/bin/env python3
"""Register an immutable execution attempt before benchmark execution."""

from __future__ import annotations

import argparse
import uuid
from pathlib import Path

from _common import canonical_digest, find_json_records, read_json, read_jsonl, require_campaign_root, utc_now, write_json_atomic


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign_root")
    parser.add_argument("--action-id", required=True)
    parser.add_argument("--runtime-session-id", required=True)
    parser.add_argument("--hardware-environment-id", required=True)
    parser.add_argument("--target", action="append", default=[])
    parser.add_argument("--input-digests-json")
    parser.add_argument("--effective-configuration-json")
    parser.add_argument("--attempt-id")
    return parser.parse_args()


def register(args: argparse.Namespace) -> Path:
    root = require_campaign_root(args.campaign_root)
    plan = read_json(root / "planning" / "action-plan.json")
    actions = {item["action_id"]: item for item in plan.get("actions", [])}
    action = actions.get(args.action_id)
    if not action:
        raise ValueError(f"unknown action: {args.action_id}")
    if not action.get("binding_ids") or not action.get("obligation_ids"):
        raise ValueError("action must link to bindings and obligations")

    binding_ids = {item.get("binding_id") for item in read_jsonl(root / "ontology" / "bindings.jsonl")}
    obligation_ids = {item.get("obligation_id") for item in read_jsonl(root / "ontology" / "obligations.jsonl")}
    missing_bindings = sorted(set(action["binding_ids"]) - binding_ids)
    missing_obligations = sorted(set(action["obligation_ids"]) - obligation_ids)
    if missing_bindings or missing_obligations:
        raise ValueError(f"unresolved action links: bindings={missing_bindings}, obligations={missing_obligations}")

    runtime_records = find_json_records(root / "runtimes")
    runtime_ids = {record.get("runtime_session_id") for record in runtime_records}
    hardware_ids = {record.get("hardware_environment_id") for record in runtime_records}
    if args.runtime_session_id not in runtime_ids:
        raise ValueError(f"unknown runtime session: {args.runtime_session_id}")
    if args.hardware_environment_id not in hardware_ids:
        raise ValueError(f"unknown hardware environment: {args.hardware_environment_id}")

    attempt_id = args.attempt_id or f"attempt:{uuid.uuid4()}"
    attempt_dir = root / "attempts" / attempt_id.replace(":", "_")
    if attempt_dir.exists():
        raise ValueError(f"attempt already exists: {attempt_id}")
    input_digests = read_json(Path(args.input_digests_json)) if args.input_digests_json else {}
    configuration = read_json(Path(args.effective_configuration_json)) if args.effective_configuration_json else {}
    manifest = {
        "attempt_id": attempt_id,
        "action_plan_id": plan["action_plan_id"],
        "action_plan_digest": canonical_digest(plan),
        "action_id": args.action_id,
        "binding_ids": action["binding_ids"],
        "obligation_ids": action["obligation_ids"],
        "target_ids": args.target,
        "input_digests": input_digests,
        "effective_configuration": configuration,
        "runtime_session_id": args.runtime_session_id,
        "hardware_environment_id": args.hardware_environment_id,
        "status": "registered",
        "created_at": utc_now(),
        "started_at": None,
        "ended_at": None,
    }
    write_json_atomic(attempt_dir / "attempt-manifest.json", manifest)
    (attempt_dir / "artifacts").mkdir(parents=True, exist_ok=True)
    (attempt_dir / "effects.jsonl").touch()
    return attempt_dir


def main() -> int:
    args = parse_args()
    try:
        path = register(args)
    except (OSError, ValueError, KeyError) as error:
        print(f"error: {error}")
        return 2
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

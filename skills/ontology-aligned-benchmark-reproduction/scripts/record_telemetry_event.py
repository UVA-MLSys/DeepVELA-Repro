#!/usr/bin/env python3
"""Append one externally observed telemetry event to a campaign."""

from __future__ import annotations

import argparse
import uuid
from pathlib import Path

from _common import append_jsonl, read_json, require_campaign_root, utc_now, validate_schema_record


SCHEMA_BY_TYPE = {
    "tool_call": "tool_call",
    "stage_span": "stage_span",
    "human_intervention": "human_intervention",
    "resource_sample": "resource_sample",
    "agent_usage": "agent_usage",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign_root")
    parser.add_argument("event_json")
    parser.add_argument("--instrumentation", action="store_true", help="mark profiler-only work for exclusion")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        root = require_campaign_root(args.campaign_root)
        event = read_json(Path(args.event_json))
        event_type = event.get("event_type")
        if event_type not in SCHEMA_BY_TYPE:
            raise ValueError(f"unsupported event_type: {event_type}")
        event.setdefault("event_id", f"telemetry:{uuid.uuid4()}")
        event["instrumentation"] = bool(args.instrumentation or event.get("instrumentation", False))
        event.setdefault("recorded_at", utc_now())
        errors = validate_schema_record(event, SCHEMA_BY_TYPE[event_type])
        if errors:
            raise ValueError("telemetry schema failure: " + "; ".join(errors))
        append_jsonl(root / "telemetry" / "events.jsonl", event)
        if event_type == "human_intervention":
            append_jsonl(
                root / "decisions" / "human-decisions.jsonl",
                {
                    "human_decision_id": event["human_decision_id"],
                    "category": event["category"],
                    "requested_by": event["requested_by"],
                    "reason": event["reason"],
                    "decision": event["decision"],
                    "blocking": event["blocking"],
                    "counts_toward_intervention_metric": event["counts_toward_intervention_metric"],
                    "obligation_ids": event.get("obligation_ids", []),
                    "started_at": event["started_at"],
                    "ended_at": event["ended_at"],
                    "telemetry_event_id": event["event_id"],
                },
            )
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}")
        return 2
    print(event["event_id"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

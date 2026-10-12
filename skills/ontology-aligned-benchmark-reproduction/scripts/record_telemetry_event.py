#!/usr/bin/env python3
"""Append one externally observed telemetry event to a campaign."""

from __future__ import annotations

import argparse
import uuid
from pathlib import Path

from _common import append_jsonl, read_json, require_campaign_root, utc_now


ALLOWED_TYPES = {"tool_call", "stage_span", "human_intervention", "resource_sample", "error", "wait"}


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
        if event_type not in ALLOWED_TYPES:
            raise ValueError(f"unsupported event_type: {event_type}")
        event.setdefault("event_id", f"telemetry:{uuid.uuid4()}")
        event["instrumentation"] = bool(args.instrumentation or event.get("instrumentation", False))
        event.setdefault("recorded_at", utc_now())
        append_jsonl(root / "telemetry" / "events.jsonl", event)
    except (OSError, ValueError) as error:
        print(f"error: {error}")
        return 2
    print(event["event_id"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

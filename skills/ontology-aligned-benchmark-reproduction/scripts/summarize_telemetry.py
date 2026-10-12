#!/usr/bin/env python3
"""Summarize campaign telemetry while excluding instrumentation overhead."""

from __future__ import annotations

import argparse
import uuid
from collections import defaultdict
from typing import Any

from _common import read_jsonl, require_campaign_root, write_json_atomic


def summarize(events: list[dict[str, Any]]) -> dict[str, Any]:
    excluded = [event for event in events if event.get("instrumentation", False)]
    included = [event for event in events if not event.get("instrumentation", False)]
    by_stage: dict[str, dict[str, float | int]] = defaultdict(lambda: {"events": 0, "tool_calls": 0, "failures": 0, "duration_seconds": 0.0})
    timing: dict[str, float] = defaultdict(float)
    tool_calls = failures = retries = interventions = 0
    input_tokens = output_tokens = 0
    saw_input_tokens = saw_output_tokens = False
    resource_maxima: dict[str, float] = {}

    for event in included:
        stage = str(event.get("stage", "unassigned"))
        by_stage[stage]["events"] += 1
        duration = float(event.get("duration_seconds", 0.0) or 0.0)
        by_stage[stage]["duration_seconds"] += duration
        classification = str(event.get("classification", event.get("event_type", "other")))
        timing[classification] += duration
        if event.get("event_type") == "tool_call":
            tool_calls += 1
            by_stage[stage]["tool_calls"] += 1
            if event.get("outcome") == "failure":
                failures += 1
                by_stage[stage]["failures"] += 1
            if event.get("retry_of"):
                retries += 1
        if event.get("event_type") == "human_intervention":
            interventions += 1
        if event.get("input_tokens") is not None:
            saw_input_tokens = True
            input_tokens += int(event["input_tokens"])
        if event.get("output_tokens") is not None:
            saw_output_tokens = True
            output_tokens += int(event["output_tokens"])
        if event.get("event_type") == "resource_sample":
            for key, value in event.get("observations", {}).items():
                if isinstance(value, (int, float)):
                    resource_maxima[key] = max(resource_maxima.get(key, float("-inf")), float(value))

    unavailable = []
    if not saw_input_tokens:
        unavailable.append("input_tokens")
    if not saw_output_tokens:
        unavailable.append("output_tokens")
    return {
        "summary_id": f"telemetry-summary:{uuid.uuid4()}",
        "included_events": len(included),
        "excluded_instrumentation_events": len(excluded),
        "tool_calls": tool_calls,
        "failures": failures,
        "retries": retries,
        "human_interventions": interventions,
        "input_tokens": input_tokens if saw_input_tokens else None,
        "output_tokens": output_tokens if saw_output_tokens else None,
        "timing_seconds": dict(sorted(timing.items())),
        "resource_summary": {"max_observed": dict(sorted(resource_maxima.items()))},
        "by_stage": dict(sorted(by_stage.items())),
        "unavailable_metrics": unavailable,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign_root")
    return parser.parse_args()


def main() -> int:
    try:
        root = require_campaign_root(parse_args().campaign_root)
        summary = summarize(read_jsonl(root / "telemetry" / "events.jsonl"))
        write_json_atomic(root / "telemetry" / "telemetry-summary.json", summary)
    except (OSError, ValueError) as error:
        print(f"error: {error}")
        return 2
    print(f"included={summary['included_events']} excluded_instrumentation={summary['excluded_instrumentation_events']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

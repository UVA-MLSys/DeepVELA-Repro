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
    token_totals = {"input_tokens": 0, "output_tokens": 0, "cached_input_tokens": 0, "reasoning_tokens": 0}
    token_seen = {key: False for key in token_totals}
    usage_events = [event for event in included if event.get("event_type") == "agent_usage"]
    token_events = usage_events or [event for event in included if event.get("event_type") == "tool_call"]
    intervention_categories: dict[str, int] = defaultdict(int)
    blocking_human_seconds = 0.0
    resource_values: dict[str, list[tuple[Any, str, str]]] = defaultdict(list)

    for event in included:
        stage = str(event.get("stage", "unassigned"))
        by_stage[stage]["events"] += 1
        duration = float(event.get("duration_seconds", 0.0) or 0.0)
        if event.get("event_type") == "stage_span":
            by_stage[stage]["duration_seconds"] += duration
        if event.get("event_type") == "stage_span":
            timing[str(event["classification"])] += duration
        if event.get("event_type") == "tool_call":
            tool_calls += 1
            by_stage[stage]["tool_calls"] += 1
            if event.get("outcome") == "failure":
                failures += 1
                by_stage[stage]["failures"] += 1
            if event.get("retry_of"):
                retries += 1
        if event.get("event_type") == "human_intervention" and event.get("counts_toward_intervention_metric", True):
            interventions += 1
            intervention_categories[str(event.get("category", "unknown"))] += 1
            if event.get("blocking"):
                blocking_human_seconds += duration

    for event in token_events:
        for key in token_totals:
            if event.get(key) is not None:
                token_seen[key] = True
                token_totals[key] += int(event[key])

    for event in events:
        if event.get("event_type") != "resource_sample":
            continue
        for key, observation in event.get("observations", {}).items():
            resource_values[key].append((observation.get("value"), observation.get("unit", ""), observation.get("aggregation", "last")))

    resource_summary = {}
    for key, samples in sorted(resource_values.items()):
        numeric = [float(value) for value, _, _ in samples if isinstance(value, (int, float))]
        aggregation = samples[-1][2]
        if not numeric:
            value = samples[-1][0]
        elif aggregation == "max":
            value = max(numeric)
        elif aggregation == "min":
            value = min(numeric)
        elif aggregation == "delta":
            value = numeric[-1] - numeric[0]
        else:
            value = numeric[-1]
        resource_summary[key] = {
            "value": value,
            "unit": samples[-1][1],
            "aggregation": aggregation,
            "sample_count": len(samples),
        }

    unavailable = []
    for key, seen in token_seen.items():
        if not seen:
            unavailable.append(key)
    return {
        "summary_id": f"telemetry-summary:{uuid.uuid4()}",
        "included_events": len(included),
        "excluded_instrumentation_events": len(excluded),
        "tool_calls": tool_calls,
        "failures": failures,
        "retries": retries,
        "human_interventions": interventions,
        **{key: token_totals[key] if token_seen[key] else None for key in token_totals},
        "timing_seconds": dict(sorted(timing.items())),
        "resource_summary": resource_summary,
        "human_interventions_by_category": dict(sorted(intervention_categories.items())),
        "blocking_human_seconds": blocking_human_seconds,
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

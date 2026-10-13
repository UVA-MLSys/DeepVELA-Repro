#!/usr/bin/env python3
"""Ingest normalized events or adapt cumulative model-usage JSONL into telemetry."""

from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path
from typing import Any

from _common import append_jsonl, read_jsonl, require_campaign_root, utc_now, validate_schema_record


TOKEN_KEYS = ("input_tokens", "output_tokens", "cached_input_tokens", "reasoning_tokens")


def usage_candidates(value: Any) -> list[dict[str, int]]:
    candidates: list[dict[str, int]] = []
    if isinstance(value, dict):
        normalized: dict[str, int] = {}
        aliases = {
            "input_tokens": "input_tokens",
            "prompt_tokens": "input_tokens",
            "output_tokens": "output_tokens",
            "completion_tokens": "output_tokens",
            "cached_input_tokens": "cached_input_tokens",
            "cache_read_input_tokens": "cached_input_tokens",
            "reasoning_tokens": "reasoning_tokens",
            "reasoning_output_tokens": "reasoning_tokens",
        }
        for source, target in aliases.items():
            if isinstance(value.get(source), int):
                normalized[target] = max(normalized.get(target, 0), int(value[source]))
        if normalized:
            candidates.append(normalized)
        for child in value.values():
            candidates.extend(usage_candidates(child))
    elif isinstance(value, list):
        for child in value:
            candidates.extend(usage_candidates(child))
    return candidates


def adapt_cumulative_usage(records: list[dict[str, Any]], stage: str, adapter: str, session_id: str | None) -> list[dict[str, Any]]:
    previous = {key: 0 for key in TOKEN_KEYS}
    events = []
    for index, record in enumerate(records):
        candidates = usage_candidates(record)
        if not candidates:
            continue
        cumulative = max(candidates, key=lambda item: sum(item.values()))
        delta = {key: max(0, cumulative.get(key, previous[key]) - previous[key]) for key in TOKEN_KEYS}
        for key in TOKEN_KEYS:
            previous[key] = max(previous[key], cumulative.get(key, previous[key]))
        if not any(delta.values()):
            continue
        events.append(
            {
                "event_id": f"telemetry:{uuid.uuid4()}",
                "event_type": "agent_usage",
                "stage": stage,
                "recorded_at": record.get("timestamp") or record.get("created_at") or utc_now(),
                "agent_session_id": session_id,
                "model": record.get("model"),
                **delta,
                "adapter": adapter,
                "provider_event_id": str(record.get("id", index)),
                "instrumentation": False,
            }
        )
    return events


def ingest(root: Path, trace_path: Path, trace_format: str, stage: str, session_id: str | None) -> list[dict[str, Any]]:
    records = read_jsonl(trace_path)
    if trace_format == "normalized":
        events = records
    else:
        events = adapt_cumulative_usage(records, stage, trace_format, session_id)
    for event in events:
        definition = event.get("event_type")
        if definition not in {"tool_call", "stage_span", "human_intervention", "resource_sample", "agent_usage"}:
            raise ValueError(f"unsupported normalized event type: {definition}")
        errors = validate_schema_record(event, definition)
        if errors:
            raise ValueError("trace event schema failure: " + "; ".join(errors))
        append_jsonl(root / "telemetry" / "events.jsonl", event)
    return events


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign_root")
    parser.add_argument("trace_jsonl")
    parser.add_argument("--format", choices=["normalized", "openai_responses", "codex_jsonl"], required=True)
    parser.add_argument("--stage", default="unassigned")
    parser.add_argument("--agent-session-id")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        events = ingest(
            require_campaign_root(args.campaign_root),
            Path(args.trace_jsonl),
            args.format,
            args.stage,
            args.agent_session_id,
        )
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}")
        return 2
    print(f"ingested={len(events)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

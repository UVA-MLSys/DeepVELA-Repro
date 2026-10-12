#!/usr/bin/env python3
"""Compare reproduced and reference records under a frozen policy."""

from __future__ import annotations

import argparse
import math
import uuid
from pathlib import Path
from typing import Any

from _common import append_jsonl, read_json, require_campaign_root, utc_now


def rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list) and all(isinstance(item, dict) for item in value):
        return value
    if isinstance(value, dict) and isinstance(value.get("records"), list):
        return rows(value["records"])
    if isinstance(value, dict):
        return [value]
    raise ValueError("result file must contain an object, a list of objects, or {'records': [...]}")


def key_for(row: dict[str, Any], keys: list[str]) -> tuple[Any, ...]:
    missing = [key for key in keys if key not in row]
    if missing:
        raise ValueError(f"row lacks join keys {missing}: {row}")
    return tuple(row[key] for key in keys)


def index_rows(values: list[dict[str, Any]], keys: list[str]) -> dict[tuple[Any, ...], dict[str, Any]]:
    result: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in values:
        key = key_for(row, keys)
        if key in result:
            raise ValueError(f"ambiguous duplicate join key: {key}")
        result[key] = row
    return result


def compare_value(actual: Any, reference: Any, comparator: str, tolerance: float | None) -> tuple[bool, float | None]:
    if comparator == "exact":
        return actual == reference, None
    if not isinstance(actual, (int, float)) or not isinstance(reference, (int, float)):
        raise ValueError("tolerance comparators require numeric values")
    if not math.isfinite(float(actual)) or not math.isfinite(float(reference)):
        raise ValueError("non-finite values are not comparable")
    difference = abs(float(actual) - float(reference))
    if comparator == "absolute_tolerance":
        return difference <= float(tolerance), difference
    if comparator == "relative_tolerance":
        boundary = float(tolerance) * abs(float(reference))
        return difference <= boundary, difference
    raise ValueError(f"unsupported comparator in v1: {comparator}")


def compare(args: argparse.Namespace) -> dict[str, Any]:
    root = require_campaign_root(args.campaign_root)
    policy = read_json(root / "contract" / "verification-policy.json")
    comparator = policy["comparator"]
    tolerance = policy.get("tolerance")
    if comparator != "exact" and tolerance is None:
        raise ValueError("frozen policy lacks a tolerance")
    keys = policy["join_keys"]
    actual = index_rows(rows(read_json(Path(args.actual))), keys)
    reference = index_rows(rows(read_json(Path(args.reference))), keys)
    missing_actual = sorted(set(reference) - set(actual), key=str)
    missing_reference = sorted(set(actual) - set(reference), key=str)
    values = []
    failures = 0
    for key in sorted(set(actual) & set(reference), key=str):
        passed, difference = compare_value(actual[key][args.value_field], reference[key][args.value_field], comparator, tolerance)
        failures += int(not passed)
        values.append(
            {
                "join_key": list(key),
                "actual": actual[key][args.value_field],
                "reference": reference[key][args.value_field],
                "absolute_difference": difference,
                "pass": passed,
            }
        )
    missing = bool(missing_actual or missing_reference)
    if missing and policy["missing_result_behavior"] == "inconclusive":
        decision = "inconclusive"
    elif failures or missing:
        decision = "fail"
    else:
        decision = "pass"
    return {
        "comparison_id": args.comparison_id or f"comparison:{uuid.uuid4()}",
        "target_id": args.target_id,
        "actual_artifact_id": args.actual_artifact_id,
        "reference_artifact_id": args.reference_artifact_id,
        "comparator": comparator,
        "tolerance": tolerance,
        "grain": policy["result_grain"],
        "value_field": args.value_field,
        "values": values,
        "missing_actual_keys": [list(value) for value in missing_actual],
        "missing_reference_keys": [list(value) for value in missing_reference],
        "decision": decision,
        "current": True,
        "policy_id": policy["policy_id"],
        "created_at": utc_now(),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign_root")
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--actual", required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--value-field", required=True)
    parser.add_argument("--actual-artifact-id", required=True)
    parser.add_argument("--reference-artifact-id", required=True)
    parser.add_argument("--comparison-id")
    parser.add_argument("--output")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        record = compare(args)
        output = Path(args.output) if args.output else require_campaign_root(args.campaign_root) / "verification" / "comparisons.jsonl"
        append_jsonl(output, record)
    except (KeyError, OSError, TypeError, ValueError) as error:
        print(f"error: {error}")
        return 2
    print(f"{record['comparison_id']} {record['decision']}")
    return 0 if record["decision"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

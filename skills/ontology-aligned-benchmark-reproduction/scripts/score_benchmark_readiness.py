#!/usr/bin/env python3
"""Validate and score the six-category MLCommons benchmark-readiness rubric."""

from __future__ import annotations

import argparse
from pathlib import Path

from _common import read_json, require_campaign_root, utc_now, validate_schema_record, write_json_atomic
from bootstrap_campaign import MLCOMMONS_RUBRIC


def score(assessment: dict) -> dict:
    categories = {item["name"]: item for item in assessment.get("categories", [])}
    if set(categories) != set(MLCOMMONS_RUBRIC):
        raise ValueError("assessment must contain each MLCommons category exactly once")
    for category_name, expected in MLCOMMONS_RUBRIC.items():
        category = categories[category_name]
        criteria = {item["criterion_id"]: item for item in category.get("criteria", [])}
        if set(criteria) != {criterion_id for criterion_id, _ in expected}:
            raise ValueError(f"{category_name} criteria do not match the frozen MLCommons rubric")
        awarded = 0.0
        for criterion_id, max_points in expected:
            item = criteria[criterion_id]
            points = float(item["awarded_points"])
            if float(item["max_points"]) != float(max_points):
                raise ValueError(f"{category_name}/{criterion_id} has an incorrect maximum")
            if points < 0 or points > max_points:
                raise ValueError(f"{category_name}/{criterion_id} points are outside [0, {max_points}]")
            if bool(item["met"]) != (points == max_points):
                raise ValueError(f"{category_name}/{criterion_id} met must mean full credit")
            if points and not item.get("evidence_source_ids"):
                raise ValueError(f"{category_name}/{criterion_id} awards points without source evidence")
            awarded += points
        category["score"] = awarded
        category["gaps"] = [
            item["criterion_id"] for item in category["criteria"] if item["awarded_points"] < item["max_points"]
        ]
    assessment["overall_score"] = sum(float(item["score"]) for item in categories.values()) / 6.0
    assessment["status"] = "complete"
    assessment["scored_at"] = utc_now()
    errors = validate_schema_record(assessment, "benchmark_assessment")
    if errors:
        raise ValueError("assessment schema failure: " + "; ".join(errors))
    return assessment


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign_root")
    parser.add_argument("--assessment")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        root = require_campaign_root(args.campaign_root)
        path = Path(args.assessment) if args.assessment else root / "contract" / "benchmark-assessment.json"
        assessment = score(read_json(path))
        write_json_atomic(root / "contract" / "benchmark-assessment.json", assessment)
    except (KeyError, OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}")
        return 2
    print(f"overall_score={assessment['overall_score']:.6g}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

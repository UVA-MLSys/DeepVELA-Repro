#!/usr/bin/env python3
"""Seal a completed benchmark-readiness assessment by an independent assessor."""

from __future__ import annotations

import argparse
import uuid

from _common import canonical_digest, read_json, require_campaign_root, utc_now, validate_schema_record, write_json_atomic


def seal(root, assessor_identity: str, review_notes: str) -> dict:
    assessment = read_json(root / "contract" / "benchmark-assessment.json")
    if assessment.get("status") != "complete":
        raise ValueError("only a completed assessment can be sealed")
    if not assessor_identity.strip():
        raise ValueError("assessor identity is required")
    assessment["assessor"] = {"identity": assessor_identity, "independent_of_execution": True}
    write_json_atomic(root / "contract" / "benchmark-assessment.json", assessment)
    record = {
        "seal_id": f"assessment-seal:{uuid.uuid4()}",
        "assessment_id": assessment["assessment_id"],
        "assessment_sha256": canonical_digest(assessment),
        "assessor_identity": assessor_identity,
        "independent_of_execution": True,
        "review_notes": review_notes,
        "reviewed_at": utc_now(),
    }
    errors = validate_schema_record(record, "assessment_seal")
    if errors:
        raise ValueError("assessment seal schema failure: " + "; ".join(errors))
    write_json_atomic(root / "experiment" / "benchmark-assessment-seal.json", record)
    return record


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign_root")
    parser.add_argument("--assessor-identity", required=True)
    parser.add_argument("--review-notes", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        record = seal(require_campaign_root(args.campaign_root), args.assessor_identity, args.review_notes)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}")
        return 2
    print(record["seal_id"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

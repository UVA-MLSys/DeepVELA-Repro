#!/usr/bin/env python3
"""Independently read back campaign artifacts and verify their declared digests."""

from __future__ import annotations

import argparse
from pathlib import Path

from _common import read_jsonl, require_campaign_root, sha256_file, utc_now, write_json_atomic, write_jsonl_atomic


def resolve_artifact_path(root: Path, declared: str) -> Path:
    path = Path(declared)
    return path if path.is_absolute() else root / path


def verify(root: Path, apply: bool = False) -> dict:
    path = root / "verification" / "artifacts.jsonl"
    records = read_jsonl(path)
    results = []
    for record in records:
        artifact_path = resolve_artifact_path(root, record["path"])
        readable = artifact_path.is_file()
        observed = sha256_file(artifact_path) if readable else None
        matches = readable and observed == record.get("sha256")
        results.append(
            {
                "artifact_id": record["artifact_id"],
                "path": record["path"],
                "readable": readable,
                "declared_sha256": record.get("sha256"),
                "observed_sha256": observed,
                "digest_matches": matches,
            }
        )
        if apply:
            record["read_back"] = bool(matches)
            record["integrity_verified_at"] = utc_now()
            if not readable:
                record["status"] = "missing"
            elif not matches:
                record["status"] = "unreadable"
    if apply:
        write_jsonl_atomic(path, records)
    report = {
        "campaign_root": str(root),
        "verified_at": utc_now(),
        "all_valid": all(item["digest_matches"] for item in results),
        "artifacts": results,
    }
    write_json_atomic(root / "reports" / "artifact-integrity.json", report)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign_root")
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = verify(require_campaign_root(args.campaign_root), args.apply)
    except (KeyError, OSError, ValueError) as error:
        print(f"error: {error}")
        return 2
    failures = sum(not item["digest_matches"] for item in report["artifacts"])
    print(f"artifacts={len(report['artifacts'])} failures={failures}")
    return 0 if report["all_valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

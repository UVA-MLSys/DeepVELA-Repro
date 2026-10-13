#!/usr/bin/env python3
"""Store an artifact once by SHA-256 and append its evidence record."""

from __future__ import annotations

import argparse
import os
import shutil
import tempfile
import uuid
from pathlib import Path

from _common import append_jsonl, read_jsonl, require_campaign_root, sha256_file, validate_schema_record


def store(root: Path, source: Path, args: argparse.Namespace) -> dict:
    source = source.expanduser().resolve()
    if not source.is_file():
        raise ValueError(f"artifact input is not a readable file: {source}")
    digest = sha256_file(source)
    relative = Path("artifact-store") / "sha256" / digest[:2] / digest
    destination = root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        descriptor, temporary = tempfile.mkstemp(prefix=f".{digest}.", dir=destination.parent)
        os.close(descriptor)
        try:
            shutil.copyfile(source, temporary)
            if sha256_file(Path(temporary)) != digest:
                raise ValueError("artifact digest changed during storage")
            os.replace(temporary, destination)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    if sha256_file(destination) != digest:
        raise ValueError("content-addressed object failed read-back")
    artifact_id = args.artifact_id or f"artifact:{uuid.uuid4()}"
    records = read_jsonl(root / "verification" / "artifacts.jsonl")
    if any(record.get("artifact_id") == artifact_id for record in records):
        raise ValueError(f"artifact_id already exists: {artifact_id}")
    record = {
        "artifact_id": artifact_id,
        "role": args.role,
        "producer_attempt_id": args.producer_attempt_id,
        "target_ids": args.target_id,
        "path": str(relative),
        "sha256": digest,
        "size_bytes": destination.stat().st_size,
        "media_type": args.media_type,
        "storage_kind": "content_addressed",
        "cas_uri": f"sha256:{digest}",
        "logical_name": args.logical_name or source.name,
        "dependencies": args.dependency,
        "read_back": True,
        "status": "current",
    }
    errors = validate_schema_record(record, "artifact_record")
    if errors:
        raise ValueError("artifact record schema failure: " + "; ".join(errors))
    append_jsonl(root / "verification" / "artifacts.jsonl", record)
    return record


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign_root")
    parser.add_argument("input_file")
    parser.add_argument("--artifact-id")
    parser.add_argument("--role", required=True)
    parser.add_argument("--producer-attempt-id", required=True)
    parser.add_argument("--target-id", action="append", default=[])
    parser.add_argument("--dependency", action="append", default=[])
    parser.add_argument("--media-type", default="application/octet-stream")
    parser.add_argument("--logical-name")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        record = store(require_campaign_root(args.campaign_root), Path(args.input_file), args)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}")
        return 2
    print(f"{record['artifact_id']} {record['cas_uri']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

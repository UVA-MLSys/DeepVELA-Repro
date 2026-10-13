#!/usr/bin/env python3
"""Shared helpers for campaign control scripts."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SCHEMA_MODULES = {
    "campaign": "campaign.schema.json",
    "ontology": "ontology.schema.json",
    "execution": "execution.schema.json",
    "verification": "verification.schema.json",
    "telemetry": "telemetry.schema.json",
    "experiment": "experiment.schema.json",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def read_json_if_exists(path: Path, default: Any) -> Any:
    return read_json(path) if path.exists() else default


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number} is not a JSON object")
            records.append(value)
    return records


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_jsonl_atomic(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, sort_keys=True))
                handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def skill_root() -> Path:
    return Path(__file__).resolve().parents[1]


def validate_schema_record(value: Any, definition: str) -> list[str]:
    """Return JSON Schema validation errors for a named bundled definition."""
    try:
        from jsonschema import Draft202012Validator
    except ImportError as error:  # pragma: no cover - environment failure path
        raise RuntimeError("jsonschema is required for campaign validation") from error
    for module_name in SCHEMA_MODULES.values():
        module = read_json(skill_root() / "assets" / "schemas" / module_name)
        if definition not in module.get("$defs", {}):
            continue
        wrapper = {
            "$schema": module.get("$schema", "https://json-schema.org/draft/2020-12/schema"),
            "$ref": f"#/$defs/{definition}",
            "$defs": module["$defs"],
        }
        validator = Draft202012Validator(wrapper)
        return [
            f"{'/'.join(str(part) for part in item.absolute_path) or '<root>'}: {item.message}"
            for item in sorted(validator.iter_errors(value), key=lambda item: list(item.absolute_path))
        ]
    raise KeyError(f"unknown schema definition: {definition}")


def require_campaign_root(path: str | Path) -> Path:
    root = Path(path).expanduser().resolve()
    contract = root / "contract" / "campaign-contract.json"
    if not contract.is_file():
        raise ValueError(f"not a campaign root: missing {contract}")
    return root


def index_unique(records: Iterable[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for record in records:
        identity = record.get(key)
        if not isinstance(identity, str) or not identity:
            raise ValueError(f"record lacks non-empty {key}: {record}")
        if identity in result:
            raise ValueError(f"duplicate {key}: {identity}")
        result[identity] = record
    return result


def find_json_records(directory: Path) -> list[dict[str, Any]]:
    if not directory.exists():
        return []
    records = []
    for path in sorted(directory.rglob("*.json")):
        value = read_json(path)
        if isinstance(value, dict):
            records.append(value)
    return records


def invalidated_ids(root: Path) -> set[str]:
    result: set[str] = set()
    for record in read_jsonl(root / "state" / "invalidations.jsonl"):
        if record.get("status", "active") == "active":
            result.update(str(value) for value in record.get("invalidated_ids", []))
    return result

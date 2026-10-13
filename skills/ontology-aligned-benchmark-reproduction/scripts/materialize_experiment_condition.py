#!/usr/bin/env python3
"""Build a content-inventoried visible bundle for a controlled reproduction trial."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path, PureWindowsPath

from _common import canonical_digest, read_json, require_campaign_root, sha256_file, utc_now, validate_schema_record, write_json_atomic


def safe_relative(value: str) -> Path:
    path = Path(value)
    windows = PureWindowsPath(value)
    if path.is_absolute() or windows.is_absolute() or windows.drive or ".." in path.parts or ".." in windows.parts:
        raise ValueError(f"condition paths must be relative and traversal-free: {value}")
    return path


def copy_visible(source_root: Path, destination: Path, visible_paths: list[str]) -> None:
    for value in visible_paths:
        relative = safe_relative(value)
        source = source_root / relative
        target = destination / relative
        if not source.exists():
            raise ValueError(f"visible path does not exist: {relative}")
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)


def inventory(directory: Path) -> list[dict]:
    return [
        {"path": str(path.relative_to(directory)), "sha256": sha256_file(path), "size_bytes": path.stat().st_size}
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    ]


def materialize(root: Path, source_root: Path, spec: dict) -> Path:
    slug = spec["condition_id"].replace(":", "_").replace("/", "_")
    condition_root = root / "experiment" / "conditions" / slug
    if condition_root.exists():
        raise ValueError(f"condition already materialized: {condition_root}")
    visible = condition_root / "visible"
    visible.mkdir(parents=True)
    copy_visible(source_root, visible, spec.get("visible_paths", []))
    withheld = [str(safe_relative(value)) for value in spec.get("withheld_paths", [])]
    leaked = [value for value in withheld if (visible / value).exists()]
    if leaked:
        shutil.rmtree(condition_root)
        raise ValueError(f"withheld paths leaked into visible bundle: {leaked}")
    files = inventory(visible)
    bundle_digest = canonical_digest(files)
    prompt_path = visible / safe_relative(spec["prompt_path"]) if spec.get("prompt_path") else None
    skill_path = visible / safe_relative(spec["skill_path"]) if spec.get("skill_path") else None
    condition = {
        "condition_id": spec["condition_id"],
        "trial_id": spec["trial_id"],
        "controller_realization": spec["controller_realization"],
        "benchmark_readiness_condition": spec["benchmark_readiness_condition"],
        "withheld_ontology_elements": spec.get("withheld_ontology_elements", []),
        "visible_ontology_elements": spec.get("visible_ontology_elements", []),
        "visible_source_ids": spec.get("visible_source_ids", []),
        "hidden_source_ids": spec.get("hidden_source_ids", []),
        "agent_configuration": spec.get("agent_configuration", {}),
        "source_access": spec.get("source_access", []),
        "tool_access": spec.get("tool_access", []),
        "hardware_environment_ids": spec.get("hardware_environment_ids", []),
        "budgets": spec.get("budgets", {}),
        "intervention_policy": spec.get("intervention_policy", {}),
        "network_policy": spec.get("network_policy", "disabled"),
        "filesystem_policy": spec.get("filesystem_policy", "condition_workspace_only"),
        "prompt_sha256": sha256_file(prompt_path) if prompt_path and prompt_path.is_file() else None,
        "skill_sha256": sha256_file(skill_path) if skill_path and skill_path.is_file() else None,
        "visible_bundle_sha256": bundle_digest,
        "created_at": utc_now(),
    }
    condition["condition_digest"] = canonical_digest(condition)
    errors = validate_schema_record(condition, "experiment_condition")
    if errors:
        shutil.rmtree(condition_root)
        raise ValueError("experiment condition schema failure: " + "; ".join(errors))
    manifest = {
        "condition_id": condition["condition_id"],
        "files": files,
        "withheld_paths": withheld,
        "isolation_verified": not leaked,
        "bundle_sha256": bundle_digest,
        "created_at": condition["created_at"],
    }
    write_json_atomic(condition_root / "condition.json", condition)
    write_json_atomic(condition_root / "bundle-manifest.json", manifest)
    write_json_atomic(
        condition_root / "access-policy.json",
        {
            "network_policy": condition["network_policy"],
            "filesystem_policy": condition["filesystem_policy"],
            "source_access": condition["source_access"],
            "tool_access": condition["tool_access"],
            "note": "The execution controller must enforce this declared policy; bundle validation proves only file visibility.",
        },
    )
    return condition_root


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign_root")
    parser.add_argument("condition_spec")
    parser.add_argument("--source-root", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        path = materialize(
            require_campaign_root(args.campaign_root),
            Path(args.source_root).expanduser().resolve(),
            read_json(Path(args.condition_spec)),
        )
    except (KeyError, OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}")
        return 2
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

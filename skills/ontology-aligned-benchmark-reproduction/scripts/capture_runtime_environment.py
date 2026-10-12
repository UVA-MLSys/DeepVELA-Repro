#!/usr/bin/env python3
"""Capture directly observable runtime hardware and software facts."""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

from _common import require_campaign_root, utc_now, write_json_atomic


def observed(value: Any, source: str) -> dict[str, Any]:
    return {"value": value, "evidence_class": "observed", "source": source}


def unavailable(source: str) -> dict[str, Any]:
    return {"value": None, "evidence_class": "unavailable", "source": source}


def total_memory_bytes() -> dict[str, Any]:
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        return observed(int(pages * page_size), "os.sysconf")
    except (AttributeError, OSError, ValueError):
        return unavailable("os.sysconf")


def command_output(command: list[str]) -> str | None:
    if not shutil.which(command[0]):
        return None
    try:
        completed = subprocess.run(command, check=True, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout.strip()


def capture(args: argparse.Namespace) -> Path:
    root = require_campaign_root(args.campaign_root)
    session_id = args.runtime_session_id or f"runtime:{uuid.uuid4()}"
    hardware_id = f"hardware:{uuid.uuid4()}"
    directory = root / "runtimes" / session_id.replace(":", "_")
    if directory.exists():
        raise ValueError(f"runtime session already exists: {session_id}")
    now = utc_now()
    session = {
        "runtime_session_id": session_id,
        "role": args.role,
        "access_method": args.access_method,
        "lifecycle": "active",
        "declared_capabilities": args.capability,
        "started_at": now,
        "ended_at": None,
        "replaces_runtime_session_id": args.replaces,
    }
    observations: dict[str, Any] = {
        "hostname": observed(platform.node(), "platform.node"),
        "operating_system": observed(platform.platform(), "platform.platform"),
        "kernel": observed(platform.release(), "platform.release"),
        "machine_architecture": observed(platform.machine(), "platform.machine"),
        "processor": observed(platform.processor() or None, "platform.processor"),
        "logical_cpu_count": observed(os.cpu_count(), "os.cpu_count"),
        "memory_bytes": total_memory_bytes(),
        "python_version": observed(sys.version.split()[0], "sys.version"),
    }
    nvidia = command_output(["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"])
    observations["nvidia_gpu"] = observed(nvidia, "nvidia-smi") if nvidia else unavailable("nvidia-smi")
    rocm = command_output(["rocminfo"])
    observations["rocm_info"] = observed(rocm[:20000], "rocminfo") if rocm else unavailable("rocminfo")
    hardware = {
        "hardware_environment_id": hardware_id,
        "runtime_session_id": session_id,
        "captured_at": now,
        "observations": observations,
    }
    write_json_atomic(directory / "runtime-session.json", session)
    write_json_atomic(directory / "hardware-environment.json", hardware)
    return directory


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign_root")
    parser.add_argument("--runtime-session-id")
    parser.add_argument("--role", choices=["control", "benchmark", "evaluator"], required=True)
    parser.add_argument("--access-method", required=True)
    parser.add_argument("--capability", action="append", default=[])
    parser.add_argument("--replaces")
    return parser.parse_args()


def main() -> int:
    try:
        path = capture(parse_args())
    except (OSError, ValueError) as error:
        print(f"error: {error}")
        return 2
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Sample benchmark-runtime resources out of band and append resource telemetry."""

from __future__ import annotations

import argparse
import os
import platform
import resource
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from _common import append_jsonl, require_campaign_root, utc_now


def observation(value: Any, unit: str, aggregation: str) -> dict[str, Any]:
    return {"value": value, "unit": unit, "aggregation": aggregation}


def gpu_observations() -> dict[str, dict[str, Any]]:
    if not shutil.which("nvidia-smi"):
        return {}
    command = [
        "nvidia-smi",
        "--query-gpu=utilization.gpu,memory.used,memory.total,power.draw",
        "--format=csv,noheader,nounits",
    ]
    try:
        output = subprocess.run(command, check=True, capture_output=True, text=True, timeout=10).stdout
        rows = [[float(value.strip()) for value in line.split(",")] for line in output.splitlines() if line.strip()]
    except (OSError, subprocess.SubprocessError, ValueError):
        return {}
    if not rows:
        return {}
    return {
        "gpu_utilization_percent": observation(max(row[0] for row in rows), "percent", "max"),
        "gpu_memory_used_mib": observation(sum(row[1] for row in rows), "MiB", "max"),
        "gpu_memory_total_mib": observation(sum(row[2] for row in rows), "MiB", "last"),
        "gpu_power_watts": observation(sum(row[3] for row in rows), "W", "max"),
    }


def memory_observations() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    proc = Path("/proc/meminfo")
    if proc.is_file():
        values = {}
        for line in proc.read_text(encoding="utf-8").splitlines():
            key, raw = line.split(":", 1)
            values[key] = int(raw.strip().split()[0]) * 1024
        result["system_memory_available_bytes"] = observation(values.get("MemAvailable"), "bytes", "min")
    usage = resource.getrusage(resource.RUSAGE_SELF)
    scale = 1 if platform.system() == "Darwin" else 1024
    result["profiler_process_peak_rss_bytes"] = observation(int(usage.ru_maxrss * scale), "bytes", "max")
    result["profiler_cpu_user_seconds"] = observation(float(usage.ru_utime), "seconds", "delta")
    result["profiler_cpu_system_seconds"] = observation(float(usage.ru_stime), "seconds", "delta")
    return result


def sample(root: Path, args: argparse.Namespace) -> int:
    start = time.monotonic()
    previous = start
    energy_joules = 0.0
    count = 0
    while True:
        now = time.monotonic()
        observations = memory_observations()
        gpu = gpu_observations()
        power = gpu.get("gpu_power_watts", {}).get("value")
        if isinstance(power, (int, float)):
            energy_joules += float(power) * max(0.0, now - previous)
            gpu["gpu_energy_joules"] = observation(energy_joules, "J", "last")
        observations.update(gpu)
        append_jsonl(
            root / "telemetry" / "events.jsonl",
            {
                "event_id": f"telemetry:{uuid.uuid4()}",
                "event_type": "resource_sample",
                "timestamp": utc_now(),
                "runtime_session_id": args.runtime_session_id,
                "hardware_environment_id": args.hardware_environment_id,
                "attempt_id": args.attempt_id,
                "observations": observations,
                "instrumentation": True,
            },
        )
        count += 1
        previous = now
        if args.duration_seconds <= 0 or now - start >= args.duration_seconds:
            break
        time.sleep(min(args.interval_seconds, max(0.0, args.duration_seconds - (now - start))))
    return count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign_root")
    parser.add_argument("--runtime-session-id", required=True)
    parser.add_argument("--hardware-environment-id", required=True)
    parser.add_argument("--attempt-id")
    parser.add_argument("--interval-seconds", type=float, default=5.0)
    parser.add_argument("--duration-seconds", type=float, default=0.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.interval_seconds <= 0 or args.duration_seconds < 0:
        print("error: intervals must be positive and duration non-negative")
        return 2
    try:
        count = sample(require_campaign_root(args.campaign_root), args)
    except (OSError, ValueError) as error:
        print(f"error: {error}")
        return 2
    print(f"samples={count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

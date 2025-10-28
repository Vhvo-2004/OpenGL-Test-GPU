"""Collect GPU and CPU usage statistics using available tools and live sampling."""
from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from src.opengl_app.monitor import UsageMonitor


def run_command(command: list[str]) -> tuple[int, str, str]:
    process = subprocess.run(command, capture_output=True, text=True, check=False)
    return process.returncode, process.stdout.strip(), process.stderr.strip()


def detect_gpus() -> dict[str, Any]:
    """Attempt to detect GPUs using nvidia-smi or lspci."""
    result: dict[str, Any] = {"available": False, "details": []}
    if shutil.which("nvidia-smi"):
        code, stdout, stderr = run_command(["nvidia-smi", "--query-gpu=name,index,memory.total", "--format=csv"])
        if code == 0:
            lines = stdout.splitlines()[1:]
            result["available"] = True
            result["details"] = [line.strip() for line in lines]
        else:
            result["error"] = stderr
    else:
        # Try lspci as a fallback to list display controllers
        if shutil.which("lspci"):
            code, stdout, _ = run_command(["lspci"])
            if code == 0:
                gpus = [line for line in stdout.splitlines() if "VGA" in line or "3D controller" in line]
                if gpus:
                    result["available"] = True
                    result["details"] = gpus
    return result


def detect_cpu() -> dict[str, Any]:
    info: dict[str, Any] = {"processor": platform.processor() or platform.machine()}
    if shutil.which("lscpu"):
        code, stdout, _ = run_command(["lscpu"])
        if code == 0:
            info["lscpu"] = stdout
    return info


def collect_usage(duration: float, interval: float) -> dict[str, Any]:
    """Gather CPU/GPU usage metrics over a sampling window."""

    monitor = UsageMonitor(interval=interval)
    monitor.start()
    try:
        time.sleep(max(0.0, duration))
    finally:
        monitor.stop()

    summary = monitor.summary()
    samples_payload = []
    for sample in monitor.samples:
        samples_payload.append(
            {
                "timestamp": sample.timestamp,
                "cpu_percent": sample.cpu_percent,
                "gpus": [
                    {
                        "index": gpu.index,
                        "name": gpu.name,
                        "utilization": gpu.utilization,
                        "memory_utilization": gpu.memory_utilization,
                    }
                    for gpu in sample.gpus
                ],
            }
        )

    return {
        "summary": summary,
        "samples": samples_payload,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/system_probe.json"))
    parser.add_argument("--duration", type=float, default=5.0, help="Sampling duration in seconds")
    parser.add_argument("--interval", type=float, default=1.0, help="Sampling interval in seconds")
    args = parser.parse_args()

    payload = {
        "cpu": detect_cpu(),
        "gpus": detect_gpus(),
        "usage": collect_usage(args.duration, args.interval),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()

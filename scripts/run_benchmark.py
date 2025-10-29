#!/usr/bin/env python3
"""Run the GLUT triangle demo in benchmark mode while collecting resource metrics."""

from __future__ import annotations

import argparse
import csv
import platform
import subprocess
import sys
import threading
import time
from pathlib import Path
from statistics import mean
from typing import Dict, Iterable, List, Optional, Sequence

try:  # Optional CPU metrics support
    import psutil  # type: ignore
except ImportError:  # pragma: no cover - runtime dependency
    psutil = None  # type: ignore

try:  # Optional GPU metrics support (NVML / NVIDIA GPUs)
    import pynvml  # type: ignore
except ImportError:  # pragma: no cover - runtime dependency
    pynvml = None  # type: ignore


class GPUManager:
    """Helper that wraps optional NVML GPU queries."""

    def __init__(self) -> None:
        self.available = False
        self.handles: List[object] = []
        self.names: List[str] = []
        self.notes: List[str] = []

        if pynvml is None:
            self.notes.append("pynvml not installed; GPU utilisation metrics disabled")
            return

        try:
            pynvml.nvmlInit()  # type: ignore[attr-defined]
        except Exception as exc:  # pragma: no cover - depends on host environment
            self.notes.append(f"NVML initialisation failed: {exc}")
            return

        try:
            count = pynvml.nvmlDeviceGetCount()  # type: ignore[attr-defined]
        except Exception as exc:  # pragma: no cover
            self.notes.append(f"NVML query failed: {exc}")
            return

        for index in range(count):
            handle = pynvml.nvmlDeviceGetHandleByIndex(index)  # type: ignore[attr-defined]
            name = pynvml.nvmlDeviceGetName(handle)  # type: ignore[attr-defined]
            if isinstance(name, bytes):
                name = name.decode("utf-8", "replace")
            self.handles.append(handle)
            self.names.append(str(name))

        self.available = bool(self.handles)

    def shutdown(self) -> None:
        if pynvml is None:
            return
        try:
            pynvml.nvmlShutdown()  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover - best effort cleanup
            pass

    def sample(self) -> List[float]:
        if not self.available:
            return []

        utilisation: List[float] = []
        for handle in self.handles:
            try:
                stats = pynvml.nvmlDeviceGetUtilizationRates(handle)  # type: ignore[attr-defined]
                utilisation.append(float(stats.gpu))
            except Exception:  # pragma: no cover - NVML query issues
                utilisation.append(0.0)
        return utilisation


GPU_MANAGER = GPUManager()
if GPU_MANAGER.available and pynvml is not None:
    import atexit

    atexit.register(GPU_MANAGER.shutdown)


class SystemMonitor:
    """Background sampler that records CPU/GPU utilisation while a process runs."""

    def __init__(self, sample_interval: float = 1.0) -> None:
        self.sample_interval = max(0.1, sample_interval)
        self.cpu_samples: List[float] = []
        self.proc_cpu_samples: List[float] = []
        self.gpu_samples: List[List[float]] = []
        self.notes: List[str] = []
        if psutil is None:
            self.notes.append("psutil not installed; CPU metrics disabled")

        self._pid: Optional[int] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self, pid: int) -> None:
        self._pid = pid
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=self.sample_interval * 2.0)
            self._thread = None

    def _run(self) -> None:
        process: Optional["psutil.Process"] = None
        cpu_count = 1

        if psutil is not None and self._pid is not None:
            try:
                process = psutil.Process(self._pid)
                cpu_count = psutil.cpu_count(logical=True) or 1
                psutil.cpu_percent(interval=None)
                process.cpu_percent(interval=None)
            except Exception as exc:  # pragma: no cover - depends on host environment
                self.notes.append(f"Failed to attach psutil to process: {exc}")
                process = None

        while not self._stop_event.is_set():
            time.sleep(self.sample_interval)

            cpu_percent: Optional[float] = None
            proc_percent: Optional[float] = None
            if psutil is not None:
                try:
                    cpu_percent = float(psutil.cpu_percent(interval=None))
                except Exception as exc:  # pragma: no cover
                    self.notes.append(f"cpu_percent failed: {exc}")
                    cpu_percent = None

            if process is not None:
                try:
                    proc_percent = float(process.cpu_percent(interval=None)) / float(cpu_count)
                    if proc_percent < 0.0:
                        proc_percent = 0.0
                except psutil.NoSuchProcess:  # type: ignore[attr-defined]
                    process = None
                except Exception as exc:  # pragma: no cover
                    self.notes.append(f"process cpu_percent failed: {exc}")
                    process = None

            gpu_percentages = GPU_MANAGER.sample()

            if cpu_percent is not None:
                self.cpu_samples.append(cpu_percent)
            if proc_percent is not None:
                self.proc_cpu_samples.append(proc_percent)
            if gpu_percentages:
                self.gpu_samples.append(gpu_percentages)

            if process is not None and not process.is_running():  # type: ignore[call-arg]
                break

    @staticmethod
    def _mean(values: Sequence[float]) -> Optional[float]:
        return float(mean(values)) if values else None

    @staticmethod
    def _min(values: Sequence[float]) -> Optional[float]:
        return float(min(values)) if values else None

    @staticmethod
    def _max(values: Sequence[float]) -> Optional[float]:
        return float(max(values)) if values else None

    def summary(self) -> Dict[str, Optional[str]]:
        cpu_mean = self._mean(self.cpu_samples)
        cpu_min = self._min(self.cpu_samples)
        cpu_max = self._max(self.cpu_samples)
        proc_mean = self._mean(self.proc_cpu_samples)
        proc_min = self._min(self.proc_cpu_samples)
        proc_max = self._max(self.proc_cpu_samples)

        gpu_flat: List[float] = [value for sample in self.gpu_samples for value in sample]
        gpu_mean = self._mean(gpu_flat)
        gpu_min = self._min(gpu_flat)
        gpu_max = self._max(gpu_flat)

        gpu_details: List[str] = []
        if self.gpu_samples:
            per_gpu = list(zip(*self.gpu_samples))
            for index, values in enumerate(per_gpu):
                name = GPU_MANAGER.names[index] if index < len(GPU_MANAGER.names) else f"GPU {index}"
                mean_val = self._mean(values)
                max_val = self._max(values)
                min_val = self._min(values)
                mean_str = f"{mean_val:.2f}" if mean_val is not None else "?"
                max_str = f"{max_val:.2f}" if max_val is not None else "?"
                min_str = f"{min_val:.2f}" if min_val is not None else "?"
                gpu_details.append(f"{name}:mean={mean_str},max={max_str},min={min_str}")

        notes = list(self.notes)
        notes.extend(GPU_MANAGER.notes)

        def _format(value: Optional[float]) -> Optional[str]:
            if value is None:
                return None
            return f"{value:.4f}"

        return {
            "cpu_percent_mean": _format(cpu_mean),
            "cpu_percent_min": _format(cpu_min),
            "cpu_percent_max": _format(cpu_max),
            "cpu_percent_delta": _format(cpu_max - cpu_min) if cpu_max is not None and cpu_min is not None else None,
            "process_cpu_percent_mean": _format(proc_mean),
            "process_cpu_percent_min": _format(proc_min),
            "process_cpu_percent_max": _format(proc_max),
            "process_cpu_percent_delta": _format(proc_max - proc_min) if proc_max is not None and proc_min is not None else None,
            "gpu_util_mean": _format(gpu_mean),
            "gpu_util_min": _format(gpu_min),
            "gpu_util_max": _format(gpu_max),
            "gpu_util_delta": _format(gpu_max - gpu_min) if gpu_max is not None and gpu_min is not None else None,
            "gpu_util_observed": "yes" if any(value > 0.0 for value in gpu_flat) else "no",
            "gpu_count": str(len(GPU_MANAGER.names)),
            "gpu_names": " | ".join(GPU_MANAGER.names) if GPU_MANAGER.names else "",
            "gpu_details": "; ".join(gpu_details),
            "samples": str(max(len(self.cpu_samples), len(self.gpu_samples))),
            "notes": "; ".join(sorted(set(filter(None, notes)))),
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--executable",
        default=str(Path("build") / "triangle_demo"),
        help="Path to the compiled triangle_demo executable (default: build/triangle_demo)",
    )
    parser.add_argument(
        "--triangles",
        type=str,
        default="1,10,25,50,100",
        help="Comma-separated list of triangle counts to benchmark",
    )
    parser.add_argument(
        "--lighting-modes",
        type=str,
        default="none,point,spot",
        help="Comma-separated list of lighting modes (none, point, spot)",
    )
    parser.add_argument(
        "--textured",
        choices=["yes", "no", "both"],
        default="yes",
        help="Whether to benchmark textured rendering, flat rendering, or both",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=10,
        help="Benchmark duration per run in seconds (default: 10)",
    )
    parser.add_argument(
        "--sample-interval",
        type=float,
        default=1.0,
        help="Sampling interval for CPU/GPU metrics in seconds (default: 1.0)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data") / "metrics.csv",
        help="Destination CSV file for benchmark results",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print stdout/stderr from the benchmark runs",
    )
    return parser.parse_args()


def parse_triangle_counts(raw: str) -> List[int]:
    counts: List[int] = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        value = int(token)
        if value < 1:
            raise ValueError("Triangle counts must be >= 1")
        counts.append(value)
    if not counts:
        raise ValueError("At least one triangle count must be specified")
    return counts


def parse_lighting_modes(raw: str) -> List[str]:
    modes: List[str] = []
    for token in raw.split(","):
        token = token.strip().lower()
        if not token:
            continue
        if token not in {"none", "point", "spot"}:
            raise ValueError(f"Unsupported lighting mode: {token}")
        modes.append(token)
    if not modes:
        raise ValueError("At least one lighting mode must be specified")
    return modes


def parse_textured_option(option: str) -> List[bool]:
    if option == "yes":
        return [True]
    if option == "no":
        return [False]
    return [True, False]


def gather_system_info() -> Dict[str, str]:
    cpu = platform.processor() or platform.uname().processor or "Unknown"
    return {"cpu_model": cpu}


def print_system_info(info: Dict[str, str]) -> None:
    gpu_summary = GPU_MANAGER.names if GPU_MANAGER.names else ["(none detected)"]
    print("SYSTEM_INFO cpu=" + info["cpu_model"])
    print("SYSTEM_INFO gpus=" + "; ".join(gpu_summary))
    if GPU_MANAGER.notes:
        print("SYSTEM_INFO notes=" + "; ".join(GPU_MANAGER.notes))


def run_case(
    executable: str,
    triangle_count: int,
    duration: int,
    lighting: str,
    textured: bool,
    verbose: bool,
    sample_interval: float,
    system_info: Dict[str, str],
) -> Dict[str, str]:
    cmd = [
        executable,
        "--benchmark",
        "--triangles",
        str(triangle_count),
        "--duration",
        str(duration),
        "--lighting",
        lighting,
    ]
    if not textured:
        cmd.append("--no-texture")

    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    monitor = SystemMonitor(sample_interval=sample_interval)
    monitor.start(process.pid)
    stdout, stderr = process.communicate()
    monitor.stop()

    if verbose:
        sys.stdout.write(stdout)
        sys.stdout.flush()
        if stderr:
            sys.stderr.write(stderr)
            sys.stderr.flush()

    if process.returncode != 0:
        raise RuntimeError(f"Benchmark run failed with exit code {process.returncode}:\n{stderr}")

    avg_fps: Optional[float] = None
    parsed_lighting = lighting
    parsed_textured = textured
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("FPS_RESULT"):
            continue
        segments = {}
        for item in line.replace(" ", "").split(","):
            if "=" in item:
                key, value = item.split("=", 1)
                segments[key] = value
        if "avg_fps" in segments:
            avg_fps = float(segments["avg_fps"])
        if "lighting" in segments:
            parsed_lighting = segments["lighting"]
        if "textured" in segments:
            parsed_textured = segments["textured"] not in {"0", "false", "False"}
        break

    if avg_fps is None:
        raise RuntimeError(f"triangle_demo output did not contain an FPS_RESULT line:\n{stdout}")

    metrics = monitor.summary()
    result: Dict[str, str] = {
        "triangles": str(triangle_count),
        "lighting": parsed_lighting,
        "textured": "yes" if parsed_textured else "no",
        "avg_fps": f"{avg_fps:.4f}",
        "duration_s": str(duration),
        "cpu_model": system_info.get("cpu_model", ""),
    }
    result.update({key: value or "" for key, value in metrics.items()})
    return result


FIELDNAMES = [
    "triangles",
    "lighting",
    "textured",
    "duration_s",
    "avg_fps",
    "cpu_percent_mean",
    "cpu_percent_min",
    "cpu_percent_max",
    "cpu_percent_delta",
    "process_cpu_percent_mean",
    "process_cpu_percent_min",
    "process_cpu_percent_max",
    "process_cpu_percent_delta",
    "gpu_util_mean",
    "gpu_util_min",
    "gpu_util_max",
    "gpu_util_delta",
    "gpu_util_observed",
    "gpu_count",
    "gpu_names",
    "gpu_details",
    "samples",
    "cpu_model",
    "notes",
]


def write_results(path: Path, results: Iterable[Dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in results:
            writer.writerow(row)


def main() -> None:  # pragma: no cover - CLI utility
    args = parse_args()
    triangle_counts = parse_triangle_counts(args.triangles)
    lighting_modes = parse_lighting_modes(args.lighting_modes)
    textured_modes = parse_textured_option(args.textured)
    system_info = gather_system_info()

    print_system_info(system_info)

    results: List[Dict[str, str]] = []
    for textured in textured_modes:
        for lighting in lighting_modes:
            for count in triangle_counts:
                result = run_case(
                    args.executable,
                    count,
                    args.duration,
                    lighting,
                    textured,
                    args.verbose,
                    args.sample_interval,
                    system_info,
                )
                results.append(result)

    write_results(args.output, results)
    print(f"Saved results to {args.output}")


if __name__ == "__main__":
    main()

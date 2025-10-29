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
        self.memory_totals_mb: List[Optional[float]] = []

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
            total_mb: Optional[float] = None
            try:
                mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)  # type: ignore[attr-defined]
                total_mb = float(mem_info.total) / (1024.0 ** 2)
            except Exception:
                total_mb = None
            self.memory_totals_mb.append(total_mb)

        self.available = bool(self.handles)

    def shutdown(self) -> None:
        if pynvml is None:
            return
        try:
            pynvml.nvmlShutdown()  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover - best effort cleanup
            pass

    def sample(self) -> List[Dict[str, Optional[float]]]:
        if not self.available:
            return []

        utilisation: List[Dict[str, Optional[float]]] = []
        for index, handle in enumerate(self.handles):
            snapshot: Dict[str, Optional[float]] = {
                "gpu_util": None,
                "mem_util": None,
                "mem_used_mb": None,
                "mem_total_mb": None,
                "temperature_c": None,
                "power_w": None,
                "sm_clock_mhz": None,
                "mem_clock_mhz": None,
            }

            try:
                stats = pynvml.nvmlDeviceGetUtilizationRates(handle)  # type: ignore[attr-defined]
                snapshot["gpu_util"] = float(stats.gpu)
                memory_util = getattr(stats, "memory", None)
                if memory_util is not None:
                    snapshot["mem_util"] = float(memory_util)
            except Exception:  # pragma: no cover - NVML query issues
                pass

            try:
                mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)  # type: ignore[attr-defined]
                snapshot["mem_used_mb"] = float(mem_info.used) / (1024.0 ** 2)
                snapshot["mem_total_mb"] = float(mem_info.total) / (1024.0 ** 2)
            except Exception:  # pragma: no cover
                if index < len(self.memory_totals_mb):
                    snapshot["mem_total_mb"] = self.memory_totals_mb[index]

            try:
                temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)  # type: ignore[attr-defined]
                snapshot["temperature_c"] = float(temp)
            except Exception:  # pragma: no cover
                pass

            try:
                power = pynvml.nvmlDeviceGetPowerUsage(handle)  # type: ignore[attr-defined]
                snapshot["power_w"] = float(power) / 1000.0
            except Exception:  # pragma: no cover
                pass

            try:
                sm_clock = pynvml.nvmlDeviceGetClockInfo(handle, pynvml.NVML_CLOCK_SM)  # type: ignore[attr-defined]
                snapshot["sm_clock_mhz"] = float(sm_clock)
            except Exception:  # pragma: no cover
                try:
                    graphics_clock = pynvml.nvmlDeviceGetClockInfo(handle, pynvml.NVML_CLOCK_GRAPHICS)  # type: ignore[attr-defined]
                    snapshot["sm_clock_mhz"] = float(graphics_clock)
                except Exception:
                    pass

            try:
                mem_clock = pynvml.nvmlDeviceGetClockInfo(handle, pynvml.NVML_CLOCK_MEM)  # type: ignore[attr-defined]
                snapshot["mem_clock_mhz"] = float(mem_clock)
            except Exception:  # pragma: no cover
                pass

            utilisation.append(snapshot)
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
        self.gpu_samples: List[List[Dict[str, Optional[float]]]] = []
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

            gpu_snapshots = GPU_MANAGER.sample()

            if cpu_percent is not None:
                self.cpu_samples.append(cpu_percent)
            if proc_percent is not None:
                self.proc_cpu_samples.append(proc_percent)
            if gpu_snapshots:
                self.gpu_samples.append(gpu_snapshots)

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

        def _collect(metric: str) -> List[float]:
            collected: List[float] = []
            for sample in self.gpu_samples:
                for snapshot in sample:
                    value = snapshot.get(metric)
                    if value is not None:
                        collected.append(float(value))
            return collected

        gpu_util_flat = _collect("gpu_util")
        gpu_mem_util_flat = _collect("mem_util")
        gpu_mem_used_flat = _collect("mem_used_mb")
        gpu_temp_flat = _collect("temperature_c")
        gpu_power_flat = _collect("power_w")
        gpu_sm_clock_flat = _collect("sm_clock_mhz")
        gpu_mem_clock_flat = _collect("mem_clock_mhz")

        gpu_mean = self._mean(gpu_util_flat)
        gpu_min = self._min(gpu_util_flat)
        gpu_max = self._max(gpu_util_flat)

        gpu_mem_util_mean = self._mean(gpu_mem_util_flat)
        gpu_mem_util_min = self._min(gpu_mem_util_flat)
        gpu_mem_util_max = self._max(gpu_mem_util_flat)

        gpu_mem_used_mean = self._mean(gpu_mem_used_flat)
        gpu_mem_used_min = self._min(gpu_mem_used_flat)
        gpu_mem_used_max = self._max(gpu_mem_used_flat)

        gpu_temp_mean = self._mean(gpu_temp_flat)
        gpu_temp_min = self._min(gpu_temp_flat)
        gpu_temp_max = self._max(gpu_temp_flat)

        gpu_power_mean = self._mean(gpu_power_flat)
        gpu_power_min = self._min(gpu_power_flat)
        gpu_power_max = self._max(gpu_power_flat)

        gpu_sm_clock_mean = self._mean(gpu_sm_clock_flat)
        gpu_sm_clock_max = self._max(gpu_sm_clock_flat)
        gpu_mem_clock_mean = self._mean(gpu_mem_clock_flat)
        gpu_mem_clock_max = self._max(gpu_mem_clock_flat)

        gpu_details: List[str] = []
        if self.gpu_samples:
            per_gpu = list(zip(*self.gpu_samples))
            for index, snapshots in enumerate(per_gpu):
                name = GPU_MANAGER.names[index] if index < len(GPU_MANAGER.names) else f"GPU {index}"
                util_vals = [snap.get("gpu_util") for snap in snapshots if snap.get("gpu_util") is not None]
                mem_vals = [snap.get("mem_util") for snap in snapshots if snap.get("mem_util") is not None]
                used_vals = [snap.get("mem_used_mb") for snap in snapshots if snap.get("mem_used_mb") is not None]
                temp_vals = [snap.get("temperature_c") for snap in snapshots if snap.get("temperature_c") is not None]
                power_vals = [snap.get("power_w") for snap in snapshots if snap.get("power_w") is not None]
                sm_clock_vals = [snap.get("sm_clock_mhz") for snap in snapshots if snap.get("sm_clock_mhz") is not None]
                mem_clock_vals = [snap.get("mem_clock_mhz") for snap in snapshots if snap.get("mem_clock_mhz") is not None]

                total_mb = None
                if index < len(GPU_MANAGER.memory_totals_mb):
                    total_mb = GPU_MANAGER.memory_totals_mb[index]
                elif snapshots:
                    total_candidates = [snap.get("mem_total_mb") for snap in snapshots if snap.get("mem_total_mb") is not None]
                    total_mb = float(total_candidates[0]) if total_candidates else None

                parts = [f"util_mean={self._mean(util_vals):.2f}" if util_vals else "util_mean=?"]
                if mem_vals:
                    parts.append(f"mem_mean={self._mean(mem_vals):.2f}")
                if used_vals:
                    parts.append(f"mem_used_mean={self._mean(used_vals):.1f}MB")
                if total_mb is not None:
                    parts.append(f"mem_total={total_mb:.0f}MB")
                if temp_vals:
                    parts.append(f"temp_mean={self._mean(temp_vals):.1f}C")
                if power_vals:
                    parts.append(f"power_mean={self._mean(power_vals):.1f}W")
                if sm_clock_vals:
                    parts.append(f"sm_clock={self._mean(sm_clock_vals):.0f}MHz")
                if mem_clock_vals:
                    parts.append(f"mem_clock={self._mean(mem_clock_vals):.0f}MHz")

                gpu_details.append(f"{name}:" + ",".join(parts))

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
            "gpu_mem_util_mean": _format(gpu_mem_util_mean),
            "gpu_mem_util_min": _format(gpu_mem_util_min),
            "gpu_mem_util_max": _format(gpu_mem_util_max),
            "gpu_mem_util_delta": _format(gpu_mem_util_max - gpu_mem_util_min)
            if gpu_mem_util_max is not None and gpu_mem_util_min is not None
            else None,
            "gpu_mem_used_mb_mean": _format(gpu_mem_used_mean),
            "gpu_mem_used_mb_min": _format(gpu_mem_used_min),
            "gpu_mem_used_mb_max": _format(gpu_mem_used_max),
            "gpu_mem_used_mb_delta": _format(gpu_mem_used_max - gpu_mem_used_min)
            if gpu_mem_used_max is not None and gpu_mem_used_min is not None
            else None,
            "gpu_temp_c_mean": _format(gpu_temp_mean),
            "gpu_temp_c_min": _format(gpu_temp_min),
            "gpu_temp_c_max": _format(gpu_temp_max),
            "gpu_temp_c_delta": _format(gpu_temp_max - gpu_temp_min)
            if gpu_temp_max is not None and gpu_temp_min is not None
            else None,
            "gpu_power_w_mean": _format(gpu_power_mean),
            "gpu_power_w_min": _format(gpu_power_min),
            "gpu_power_w_max": _format(gpu_power_max),
            "gpu_power_w_delta": _format(gpu_power_max - gpu_power_min)
            if gpu_power_max is not None and gpu_power_min is not None
            else None,
            "gpu_sm_clock_mhz_mean": _format(gpu_sm_clock_mean),
            "gpu_sm_clock_mhz_max": _format(gpu_sm_clock_max),
            "gpu_mem_clock_mhz_mean": _format(gpu_mem_clock_mean),
            "gpu_mem_clock_mhz_max": _format(gpu_mem_clock_max),
            "gpu_util_observed": "yes" if any(value > 0.0 for value in gpu_util_flat) else "no",
            "gpu_count": str(len(GPU_MANAGER.names)),
            "gpu_names": " | ".join(GPU_MANAGER.names) if GPU_MANAGER.names else "",
            "gpu_memory_totals_mb": "; ".join(
                f"{GPU_MANAGER.names[i]}={GPU_MANAGER.memory_totals_mb[i]:.0f}MB"
                if i < len(GPU_MANAGER.names) and GPU_MANAGER.memory_totals_mb[i] is not None
                else (
                    f"{GPU_MANAGER.names[i]}=?" if i < len(GPU_MANAGER.names) else ""
                )
                for i in range(len(GPU_MANAGER.names))
            ),
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
        default="1,100,1000,10000,30000,100000,200000,300000",
        help="Comma-separated list of triangle counts to benchmark",
    )
    parser.add_argument(
        "--lighting-modes",
        type=str,
        default="none,point,spot,both",
        help="Comma-separated list of lighting modes (none, point, spot, both)",
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
        if token not in {"none", "point", "spot", "both", "point_spot", "pointandspot"}:
            raise ValueError(f"Unsupported lighting mode: {token}")
        modes.append("both" if token in {"both", "point_spot", "pointandspot"} else token)
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
    if GPU_MANAGER.names:
        memory_summaries = []
        for name, total in zip(GPU_MANAGER.names, GPU_MANAGER.memory_totals_mb):
            if total is None:
                memory_summaries.append(f"{name}:?")
            else:
                memory_summaries.append(f"{name}:{total:.0f}MB")
        if memory_summaries:
            print("SYSTEM_INFO gpu_memory=" + "; ".join(memory_summaries))
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
    "gpu_mem_util_mean",
    "gpu_mem_util_min",
    "gpu_mem_util_max",
    "gpu_mem_util_delta",
    "gpu_mem_used_mb_mean",
    "gpu_mem_used_mb_min",
    "gpu_mem_used_mb_max",
    "gpu_mem_used_mb_delta",
    "gpu_temp_c_mean",
    "gpu_temp_c_min",
    "gpu_temp_c_max",
    "gpu_temp_c_delta",
    "gpu_power_w_mean",
    "gpu_power_w_min",
    "gpu_power_w_max",
    "gpu_power_w_delta",
    "gpu_sm_clock_mhz_mean",
    "gpu_sm_clock_mhz_max",
    "gpu_mem_clock_mhz_mean",
    "gpu_mem_clock_mhz_max",
    "gpu_util_observed",
    "gpu_count",
    "gpu_names",
    "gpu_memory_totals_mb",
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

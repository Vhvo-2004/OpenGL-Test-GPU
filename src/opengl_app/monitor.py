"""System usage monitoring helpers for CPU and GPU sampling."""
from __future__ import annotations

import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

try:  # pragma: no cover - optional dependency
    import psutil  # type: ignore
except Exception:  # pragma: no cover - gracefully handle missing psutil
    psutil = None


@dataclass
class GPUSample:
    """Represent a single GPU usage measurement."""

    index: str
    name: str
    utilization: Optional[float]
    memory_utilization: Optional[float]


@dataclass
class UsageSample:
    """Represent a timestamped CPU/GPU usage snapshot."""

    timestamp: float
    cpu_percent: Optional[float]
    gpus: List[GPUSample]


class UsageMonitor:
    """Background sampler that periodically collects CPU/GPU utilisation."""

    def __init__(self, interval: float = 1.0) -> None:
        self.interval = max(0.2, interval)
        self.samples: List[UsageSample] = []
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        if psutil is not None:
            try:
                psutil.cpu_percent(interval=None)  # prime the reading
            except Exception:
                pass
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=self.interval * 2)
        self._thread = None

    # ------------------------------------------------------------------
    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            start = time.perf_counter()
            self.samples.append(self._collect_sample())
            elapsed = time.perf_counter() - start
            sleep_for = max(0.0, self.interval - elapsed)
            if self._stop_event.wait(timeout=sleep_for):
                break

    def _collect_sample(self) -> UsageSample:
        cpu_percent: Optional[float] = None
        if psutil is not None:
            try:
                cpu_percent = float(psutil.cpu_percent(interval=None))
            except Exception:
                cpu_percent = None
        gpu_samples = self._query_gpu()
        return UsageSample(timestamp=time.time(), cpu_percent=cpu_percent, gpus=gpu_samples)

    @staticmethod
    def _query_gpu() -> List[GPUSample]:
        if not shutil.which("nvidia-smi"):
            return []
        command = [
            "nvidia-smi",
            "--query-gpu=index,name,utilization.gpu,utilization.memory",
            "--format=csv,noheader,nounits",
        ]
        try:
            result = subprocess.run(command, check=False, capture_output=True, text=True)
        except Exception:
            return []
        if result.returncode != 0:
            return []
        samples: List[GPUSample] = []
        for line in result.stdout.splitlines():
            parts = [part.strip() for part in line.split(",")]
            if len(parts) < 4:
                continue
            index, name, util_str, mem_str = parts[:4]
            try:
                util = float(util_str)
            except ValueError:
                util = None
            try:
                mem_util = float(mem_str)
            except ValueError:
                mem_util = None
            samples.append(GPUSample(index=index, name=name, utilization=util, memory_utilization=mem_util))
        return samples

    # ------------------------------------------------------------------
    def summary(self) -> Dict[str, Any]:
        if not self.samples:
            return {}

        cpu_values = [s.cpu_percent for s in self.samples if s.cpu_percent is not None]
        gpu_map: Dict[str, Dict[str, Any]] = {}
        gpu_all_utils: List[float] = []
        gpu_all_mem: List[float] = []
        for sample in self.samples:
            for gpu in sample.gpus:
                stats = gpu_map.setdefault(
                    gpu.index,
                    {
                        "index": gpu.index,
                        "name": gpu.name,
                        "util_values": [],
                        "mem_values": [],
                    },
                )
                if gpu.utilization is not None:
                    stats["util_values"].append(gpu.utilization)
                    gpu_all_utils.append(gpu.utilization)
                if gpu.memory_utilization is not None:
                    stats["mem_values"].append(gpu.memory_utilization)
                    gpu_all_mem.append(gpu.memory_utilization)

        gpu_details: List[Dict[str, Any]] = []
        for stats in gpu_map.values():
            util_values = stats["util_values"]
            mem_values = stats["mem_values"]
            gpu_details.append(
                {
                    "index": stats["index"],
                    "name": stats["name"],
                    "util_avg": sum(util_values) / len(util_values) if util_values else None,
                    "util_max": max(util_values) if util_values else None,
                    "mem_avg": sum(mem_values) / len(mem_values) if mem_values else None,
                    "mem_max": max(mem_values) if mem_values else None,
                }
            )

        summary: Dict[str, Any] = {
            "cpu_avg": sum(cpu_values) / len(cpu_values) if cpu_values else None,
            "cpu_max": max(cpu_values) if cpu_values else None,
            "gpu_avg": sum(gpu_all_utils) / len(gpu_all_utils) if gpu_all_utils else None,
            "gpu_max": max(gpu_all_utils) if gpu_all_utils else None,
            "gpu_mem_avg": sum(gpu_all_mem) / len(gpu_all_mem) if gpu_all_mem else None,
            "gpu_mem_max": max(gpu_all_mem) if gpu_all_mem else None,
            "gpu_details": gpu_details,
            "sample_count": len(self.samples),
        }
        return summary


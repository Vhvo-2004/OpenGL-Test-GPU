"""Generate FPS plots based on recorded benchmark data."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import math
from collections import defaultdict

import matplotlib.pyplot as plt


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/benchmark_results.json"))
    parser.add_argument("--output", type=Path, default=Path("docs/figures/fps_vs_triangles.png"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    with args.input.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    by_light = defaultdict(list)
    for entry in data:
        light = entry.get("light", "omnidirectional")
        by_light[light].append(entry)

    colors = {
        "omnidirectional": "#2b6cb0",
        "spot": "#d97706",
        "directional": "#059669",
    }

    fig, axes = plt.subplots(1, 3, figsize=(16, 5), sharex=False)
    fps_ax, cpu_ax, gpu_ax = axes

    cpu_available = any(entry.get("cpu_percent_avg") is not None for entry in data)
    gpu_available = any(entry.get("gpu_percent_avg") is not None for entry in data)

    for light, entries in by_light.items():
        entries.sort(key=lambda item: item["triangles"])
        triangles = [item["triangles"] for item in entries]
        fps_mean = [item.get("fps_mean", 0.0) for item in entries]
        fps_std = [item.get("fps_std", 0.0) for item in entries]
        color = colors.get(light, None)

        fps_ax.errorbar(triangles, fps_mean, yerr=fps_std, fmt="-o", capsize=4, label=light, color=color)

        if cpu_available:
            cpu_series = [item.get("cpu_percent_avg") for item in entries]
            cpu_ax.plot(
                triangles,
                [value if value is not None else math.nan for value in cpu_series],
                marker="o",
                label=light,
                color=color,
            )

        if gpu_available:
            gpu_series = [item.get("gpu_percent_avg") for item in entries]
            gpu_ax.plot(
                triangles,
                [value if value is not None else math.nan for value in gpu_series],
                marker="o",
                label=light,
                color=color,
            )

    fps_ax.set_title("FPS médio vs. triângulos")
    fps_ax.set_xlabel("Quantidade de triângulos")
    fps_ax.set_ylabel("FPS médio")
    fps_ax.grid(True, linestyle="--", alpha=0.4)
    fps_ax.legend()

    cpu_ax.set_title("Uso médio de CPU (%)")
    cpu_ax.set_xlabel("Quantidade de triângulos")
    cpu_ax.set_ylabel("CPU (%)")
    cpu_ax.grid(True, linestyle="--", alpha=0.4)
    if not cpu_available:
        cpu_ax.text(0.5, 0.5, "Dados de CPU indisponíveis", ha="center", va="center", transform=cpu_ax.transAxes)
        cpu_ax.set_xticks([])

    gpu_ax.set_title("Uso médio de GPU (%)")
    gpu_ax.set_xlabel("Quantidade de triângulos")
    gpu_ax.set_ylabel("GPU (%)")
    gpu_ax.grid(True, linestyle="--", alpha=0.4)
    if not gpu_available:
        gpu_ax.text(0.5, 0.5, "Dados de GPU indisponíveis", ha="center", va="center", transform=gpu_ax.transAxes)
        gpu_ax.set_xticks([])

    if cpu_available:
        cpu_ax.legend()
    if gpu_available:
        gpu_ax.legend()

    fig.tight_layout()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=150, bbox_inches="tight")
    print(f"Gráfico salvo em {args.output}")


if __name__ == "__main__":
    main()

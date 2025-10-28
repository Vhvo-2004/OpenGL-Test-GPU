"""Run FPS and usage benchmarks for multiple triangle counts and lighting modes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.opengl_app import AppConfig, OpenGLApp


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--counts",
        type=int,
        nargs="+",
        default=[1, 10, 25, 50, 100, 250, 500],
        help="Triangle counts to benchmark",
    )
    parser.add_argument("--duration", type=float, default=8.0, help="Duration per test in seconds")
    parser.add_argument("--headless", action="store_true", help="Run with hidden 1x1 window")
    parser.add_argument("--output", type=Path, default=Path("data/benchmark_results.json"))
    parser.add_argument(
        "--lights",
        choices=["omnidirectional", "spot", "directional"],
        nargs="+",
        default=["omnidirectional", "spot"],
        help="Lighting modes to benchmark",
    )
    parser.add_argument("--width", type=int, default=1024)
    parser.add_argument("--height", type=int, default=768)
    parser.add_argument(
        "--monitor-interval",
        type=float,
        default=1.0,
        help="Interval in seconds between CPU/GPU usage samples",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = AppConfig(
        width=args.width,
        height=args.height,
        light_mode=args.lights[0],
        benchmark=True,
        benchmark_duration=args.duration,
        headless=args.headless,
        monitor_usage=True,
        monitor_interval=args.monitor_interval,
    )
    app = OpenGLApp(config)
    results = app.run_benchmark(args.counts, light_modes=args.lights)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    app.save_results(args.output, results)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()

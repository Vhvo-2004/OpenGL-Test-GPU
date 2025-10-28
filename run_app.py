"""Entry point for running the OpenGL rotating triangles demo."""
from __future__ import annotations

import argparse
from pathlib import Path

from src.opengl_app import AppConfig, OpenGLApp


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--triangles", type=int, default=1, help="Number of triangles to render")
    parser.add_argument(
        "--light",
        choices=["omnidirectional", "spot", "directional"],
        default="omnidirectional",
        help="Lighting configuration",
    )
    parser.add_argument(
        "--texture",
        type=Path,
        default=None,
        help="Path to texture image (procedural texture used when omitted)",
    )
    parser.add_argument("--width", type=int, default=1024, help="Window width")
    parser.add_argument("--height", type=int, default=768, help="Window height")
    parser.add_argument("--duration", type=float, default=10.0, help="Benchmark duration in seconds")
    parser.add_argument(
        "--benchmark",
        action="store_true",
        help="Run in benchmark mode and exit after the given duration",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Initialize the OpenGL context with a 1x1 hidden window (useful for remote runs)",
    )
    parser.add_argument(
        "--monitor-usage",
        action="store_true",
        help="Collect CPU/GPU usage samples while the application is running",
    )
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
        triangles=args.triangles,
        light_mode=args.light,
        texture_path=args.texture,
        width=args.width,
        height=args.height,
        benchmark_duration=args.duration,
        benchmark=args.benchmark,
        headless=args.headless,
        monitor_usage=args.monitor_usage or args.benchmark,
        monitor_interval=args.monitor_interval,
    )
    app = OpenGLApp(config)
    app.run()


if __name__ == "__main__":
    main()

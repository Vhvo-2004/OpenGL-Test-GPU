#!/usr/bin/env python3
"""Run the GLUT triangle demo in benchmark mode for multiple triangle counts."""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Tuple


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
        "--duration",
        type=int,
        default=10,
        help="Benchmark duration per run in seconds (default: 10)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data") / "fps_results.csv",
        help="Destination CSV file for benchmark results",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print stdout from the benchmark runs",
    )
    return parser.parse_args()


def run_case(executable: str, triangle_count: int, duration: int, verbose: bool) -> Tuple[int, float]:
    cmd = [executable, "--benchmark", "--triangles", str(triangle_count), "--duration", str(duration)]
    try:
        completed = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as exc:  # pragma: no cover - manual execution utility
        sys.stderr.write(exc.stdout)
        sys.stderr.write(exc.stderr)
        raise

    if verbose:
        sys.stdout.write(completed.stdout)
        sys.stdout.flush()

    avg_fps = None
    for line in completed.stdout.splitlines():
        line = line.strip()
        if line.startswith("FPS_RESULT"):
            segments = dict(item.split("=", 1) for item in line.replace(" ", "").split(","))
            avg_fps = float(segments.get("avg_fps", "nan"))
            break

    if avg_fps is None:
        raise RuntimeError(f"triangle_demo output did not contain an FPS_RESULT line:\n{completed.stdout}")

    return triangle_count, avg_fps


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


def write_results(path: Path, results: Iterable[Tuple[int, float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["triangles", "avg_fps"])
        for triangles, fps in results:
            writer.writerow([triangles, f"{fps:.6f}"])


def main() -> None:  # pragma: no cover - CLI utility
    args = parse_args()
    triangle_counts = parse_triangle_counts(args.triangles)
    results: List[Tuple[int, float]] = []

    for count in triangle_counts:
        result = run_case(args.executable, count, args.duration, args.verbose)
        results.append(result)

    write_results(args.output, results)
    print(f"Saved results to {args.output}")


if __name__ == "__main__":
    main()

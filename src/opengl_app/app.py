"""Interactive OpenGL application and benchmarking helpers."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np
import pygame
from OpenGL import GL

from .monitor import UsageMonitor
from .scene import TriangleScene


@dataclass
class AppConfig:
    """Runtime configuration for the OpenGL application."""

    width: int = 1024
    height: int = 768
    triangles: int = 1
    light_mode: str = "omnidirectional"
    texture_path: Path | None = None
    rotation_speed: float = 45.0
    target_fps: int = 60
    benchmark_duration: float = 10.0
    benchmark: bool = False
    headless: bool = False
    monitor_usage: bool = False
    monitor_interval: float = 1.0


class FPSCounter:
    """Track instantaneous and average FPS over a sliding window."""

    def __init__(self, window_seconds: float = 5.0) -> None:
        self.window_seconds = window_seconds
        self.frame_times: list[float] = []
        self._accumulated: float = 0.0

    def update(self, frame_time: float) -> None:
        if frame_time <= 0:
            return
        self.frame_times.append(frame_time)
        self._accumulated += frame_time
        while self.frame_times and self._accumulated > self.window_seconds:
            self._accumulated -= self.frame_times.pop(0)

    @property
    def fps(self) -> float:
        if not self.frame_times or self._accumulated <= 0:
            return 0.0
        return len(self.frame_times) / self._accumulated

    def reset(self) -> None:
        self.frame_times.clear()
        self._accumulated = 0.0


class OpenGLApp:
    """Main application harness for rendering and benchmarking."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.scene: Optional[TriangleScene] = None
        self.clock = pygame.time.Clock()
        self.fps_counter = FPSCounter()
        self._running = False
        self._frame_fps: list[float] = []
        self.usage_summary: dict[str, Any] | None = None
        self._usage_monitor: UsageMonitor | None = None

    def _init_pygame(self) -> None:
        pygame.init()
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 3)
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_CORE)
        pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLEBUFFERS, 1)
        pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLESAMPLES, 4)
        flags = pygame.OPENGL | pygame.DOUBLEBUF
        if self.config.headless:
            pygame.display.set_mode((1, 1), flags)
        else:
            pygame.display.set_mode((self.config.width, self.config.height), flags)
        pygame.display.set_caption("OpenGL Rotating Triangles")
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glEnable(GL.GL_CULL_FACE)
        GL.glEnable(GL.GL_MULTISAMPLE)

    def _create_scene(self) -> None:
        self.scene = TriangleScene(
            triangle_count=self.config.triangles,
            texture_path=self.config.texture_path,
            light_mode=self.config.light_mode,
            rotation_speed=self.config.rotation_speed,
        )

    def _handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self._running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self._running = False
                elif event.key == pygame.K_1:
                    self.scene.light_mode = "omnidirectional"
                elif event.key == pygame.K_2:
                    self.scene.light_mode = "spot"
                elif event.key == pygame.K_3:
                    self.scene.light_mode = "directional"

    def run(self) -> None:
        self._init_pygame()
        self._create_scene()
        self._running = True
        self._frame_fps.clear()
        self.fps_counter.reset()
        start_time = time.perf_counter()
        if self.config.benchmark or self.config.monitor_usage:
            self._usage_monitor = UsageMonitor(interval=self.config.monitor_interval)
            self._usage_monitor.start()
        try:
            while self._running:
                self._handle_events()
                dt = self.clock.tick(self.config.target_fps) / 1000.0
                if self.scene:
                    self.scene.update(dt)

                GL.glViewport(0, 0, self.config.width, self.config.height)
                GL.glClearColor(0.1, 0.12, 0.18, 1.0)
                GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
                if self.scene:
                    self.scene.render(self.config.width, self.config.height)
                pygame.display.flip()

                now = time.perf_counter()
                self.fps_counter.update(dt)
                if dt > 0:
                    self._frame_fps.append(1.0 / dt)

                if self.config.benchmark and (now - start_time) > self.config.benchmark_duration:
                    self._running = False
        finally:
            if self.scene:
                self.scene.dispose()
            if self._usage_monitor:
                self._usage_monitor.stop()
                self.usage_summary = self._usage_monitor.summary()
                self._usage_monitor = None
            else:
                self.usage_summary = None
            pygame.quit()

    def run_benchmark(
        self,
        triangle_counts: Iterable[int],
        light_modes: Optional[Iterable[str]] = None,
    ) -> list[dict[str, Any]]:
        """Run automated benchmark over triangle counts and optional light modes."""

        results: list[dict[str, Any]] = []
        modes = list(light_modes) if light_modes else [self.config.light_mode]
        for mode in modes:
            for count in triangle_counts:
                config = AppConfig(
                    width=self.config.width,
                    height=self.config.height,
                    triangles=count,
                    light_mode=mode,
                    texture_path=self.config.texture_path,
                    rotation_speed=self.config.rotation_speed,
                    target_fps=self.config.target_fps,
                    benchmark_duration=self.config.benchmark_duration,
                    benchmark=True,
                    headless=self.config.headless,
                    monitor_usage=True,
                    monitor_interval=self.config.monitor_interval,
                )
                app = OpenGLApp(config)
                app.run()
                fps_values = [fps for fps in app._frame_fps if fps > 0]
                if fps_values:
                    mean_fps = float(np.mean(fps_values))
                    std_fps = float(np.std(fps_values))
                    max_fps = float(np.max(fps_values))
                    min_fps = float(np.min(fps_values))
                else:
                    mean_fps = std_fps = max_fps = min_fps = 0.0
                summary = app.usage_summary or {}
                results.append(
                    {
                        "triangles": count,
                        "light": mode,
                        "fps_mean": mean_fps,
                        "fps_std": std_fps,
                        "fps_max": max_fps,
                        "fps_min": min_fps,
                        "cpu_percent_avg": summary.get("cpu_avg"),
                        "cpu_percent_max": summary.get("cpu_max"),
                        "gpu_percent_avg": summary.get("gpu_avg"),
                        "gpu_percent_max": summary.get("gpu_max"),
                        "gpu_mem_percent_avg": summary.get("gpu_mem_avg"),
                        "gpu_mem_percent_max": summary.get("gpu_mem_max"),
                        "gpu_details": summary.get("gpu_details", []),
                        "samples": summary.get("sample_count", 0),
                    }
                )
        return results

    @staticmethod
    def save_results(path: Path, results: Iterable[dict[str, Any]]) -> None:
        data = list(results)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)

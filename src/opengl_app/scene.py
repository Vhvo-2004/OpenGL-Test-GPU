"""Scene management for rendering rotating textured triangles."""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Tuple

import numpy as np
from OpenGL import GL

from .shaders import ShaderCompilationError, compile_shader_program
from .textures import Texture, create_gradient_texture, load_texture, load_texture_from_image


logger = logging.getLogger(__name__)


@dataclass
class TriangleInstance:
    """Describe the translation applied to an individual triangle."""

    position: Tuple[float, float, float]


def generate_triangle_instances(count: int, radius_step: float = 0.4) -> Iterable[TriangleInstance]:
    """Generate instance offsets arranging triangles in expanding circles."""
    if count <= 0:
        return []
    instances: list[TriangleInstance] = []
    remaining = count
    radius = 0.0
    ring = 0
    while remaining > 0:
        ring += 1
        radius += radius_step
        ring_capacity = max(1, int(6 * ring))
        items = min(remaining, ring_capacity)
        for index in range(items):
            angle = 2.0 * math.pi * (index / items)
            x = radius * math.cos(angle)
            y = radius * math.sin(angle)
            instances.append(TriangleInstance(position=(x, y, 0.0)))
        remaining -= items
    return instances


VERTEX_SHADER = """
#version 330 core
layout (location = 0) in vec3 in_position;
layout (location = 1) in vec3 in_normal;
layout (location = 2) in vec2 in_uv;
layout (location = 3) in vec3 in_color;

uniform mat4 u_model;
uniform mat4 u_view;
uniform mat4 u_projection;
uniform vec3 u_light_pos;
uniform vec3 u_light_color;
uniform vec3 u_view_pos;
uniform int u_light_type; // 0=directional,1=point,2=spot
uniform vec3 u_spot_direction;
uniform float u_spot_cutoff;

out vec3 frag_color;
out vec3 frag_normal;
out vec3 frag_pos;
out vec2 frag_uv;

void main() {
    vec4 world_pos = u_model * vec4(in_position, 1.0);
    gl_Position = u_projection * u_view * world_pos;
    frag_pos = world_pos.xyz;
    frag_normal = mat3(transpose(inverse(u_model))) * in_normal;
    frag_uv = in_uv;
    frag_color = in_color;
}
"""

FRAGMENT_SHADER = """
#version 330 core
in vec3 frag_color;
in vec3 frag_normal;
in vec3 frag_pos;
in vec2 frag_uv;

uniform sampler2D u_texture0;
uniform vec3 u_light_color;
uniform vec3 u_light_pos;
uniform int u_light_type; // 0=directional,1=point,2=spot
uniform vec3 u_spot_direction;
uniform float u_spot_cutoff;
uniform vec3 u_view_pos;

out vec4 out_color;

void main() {
    vec3 norm = normalize(frag_normal);
    vec3 light_dir;
    float attenuation = 1.0;
    if (u_light_type == 0) {
        light_dir = normalize(-u_light_pos);
    } else {
        light_dir = normalize(u_light_pos - frag_pos);
        float distance = length(u_light_pos - frag_pos);
        attenuation = 1.0 / (1.0 + 0.09 * distance + 0.032 * distance * distance);
        if (u_light_type == 2) {
            float theta = dot(light_dir, normalize(-u_spot_direction));
            attenuation *= smoothstep(u_spot_cutoff, u_spot_cutoff + 0.05, theta);
        }
    }

    float diff = max(dot(norm, light_dir), 0.0);
    vec3 view_dir = normalize(u_view_pos - frag_pos);
    vec3 reflect_dir = reflect(-light_dir, norm);
    float spec = pow(max(dot(view_dir, reflect_dir), 0.0), 16.0);

    vec3 tex_color = texture(u_texture0, frag_uv).rgb;
    vec3 ambient = 0.2 * tex_color;
    vec3 diffuse = diff * tex_color;
    vec3 specular = spec * vec3(0.5);

    vec3 result = (ambient + diffuse + specular) * frag_color * u_light_color * attenuation;
    out_color = vec4(result, 1.0);
}
"""


@dataclass
class TriangleScene:
    """Manage GPU resources necessary for rendering textured triangles."""

    triangle_count: int
    texture_path: Path | None
    light_mode: str = "omnidirectional"  # "omnidirectional", "spot", "directional"
    rotation_speed: float = 45.0
    size: float = 0.5
    shader_program: int | None = field(init=False, default=None)
    vao: int | None = field(init=False, default=None)
    vbo: int | None = field(init=False, default=None)
    ebo: int | None = field(init=False, default=None)
    texture: Texture | None = field(init=False, default=None)
    angle: float = field(init=False, default=0.0)
    bounding_radius: float = field(init=False, default=0.0)

    def __post_init__(self) -> None:
        self.instances = list(generate_triangle_instances(self.triangle_count)) or [
            TriangleInstance(position=(0.0, 0.0, 0.0))
        ]
        try:
            self.shader_program = compile_shader_program(VERTEX_SHADER, FRAGMENT_SHADER)
        except ShaderCompilationError as exc:
            raise RuntimeError(f"Failed to compile shaders: {exc}")
        self.bounding_radius = self._compute_bounding_radius()
        self._build_geometry()
        self.texture = self._load_texture()

    def _compute_bounding_radius(self) -> float:
        if not self.instances:
            return math.sqrt(2.0) * self.size
        base_extent = max(
            math.hypot(vertex[0], vertex[1])
            for vertex in (
                (-self.size, -self.size),
                (self.size, -self.size),
                (0.0, self.size),
            )
        )
        furthest_offset = max(
            math.hypot(instance.position[0], instance.position[1])
            for instance in self.instances
        )
        return furthest_offset + base_extent

    def _load_texture(self) -> Texture:
        """Load a texture from disk or fall back to a procedural gradient."""

        if self.texture_path:
            try:
                return load_texture(self.texture_path)
            except FileNotFoundError:
                logger.warning(
                    "Texture file %s not found; falling back to procedural gradient.",
                    self.texture_path,
                )
            except OSError as exc:
                logger.warning(
                    "Failed to load texture %s (%s); using procedural gradient instead.",
                    self.texture_path,
                    exc,
                )
        gradient = create_gradient_texture()
        return load_texture_from_image(gradient)

    def _build_geometry(self) -> None:
        vertices = []
        indices = []
        base_positions = [
            np.array([-self.size, -self.size, 0.0], dtype=np.float32),
            np.array([self.size, -self.size, 0.0], dtype=np.float32),
            np.array([0.0, self.size, 0.0], dtype=np.float32),
        ]
        normals = [np.array([0.0, 0.0, 1.0], dtype=np.float32)] * 3
        uvs = [
            np.array([0.0, 0.0], dtype=np.float32),
            np.array([1.0, 0.0], dtype=np.float32),
            np.array([0.5, 1.0], dtype=np.float32),
        ]
        warm_highlight = np.array([1.0, 0.62, 0.1], dtype=np.float32)
        colors = [warm_highlight for _ in range(3)]
        vertex_index = 0
        for instance in self.instances:
            offset = np.array(instance.position, dtype=np.float32)
            for pos, normal, uv, color in zip(base_positions, normals, uvs, colors):
                vertices.extend((pos + offset).tolist())
                vertices.extend(normal.tolist())
                vertices.extend(uv.tolist())
                vertices.extend(color.tolist())
            indices.extend(
                [
                    vertex_index,
                    vertex_index + 1,
                    vertex_index + 2,
                ]
            )
            vertex_index += 3
        vertex_data = np.array(vertices, dtype=np.float32)
        index_data = np.array(indices, dtype=np.uint32)

        self.vao = GL.glGenVertexArrays(1)
        self.vbo = GL.glGenBuffers(1)
        self.ebo = GL.glGenBuffers(1)

        GL.glBindVertexArray(self.vao)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, vertex_data.nbytes, vertex_data, GL.GL_STATIC_DRAW)

        GL.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, self.ebo)
        GL.glBufferData(GL.GL_ELEMENT_ARRAY_BUFFER, index_data.nbytes, index_data, GL.GL_STATIC_DRAW)

        stride = 11 * 4
        GL.glEnableVertexAttribArray(0)
        GL.glVertexAttribPointer(0, 3, GL.GL_FLOAT, GL.GL_FALSE, stride, ctypes.c_void_p(0))
        GL.glEnableVertexAttribArray(1)
        GL.glVertexAttribPointer(1, 3, GL.GL_FLOAT, GL.GL_FALSE, stride, ctypes.c_void_p(12))
        GL.glEnableVertexAttribArray(2)
        GL.glVertexAttribPointer(2, 2, GL.GL_FLOAT, GL.GL_FALSE, stride, ctypes.c_void_p(24))
        GL.glEnableVertexAttribArray(3)
        GL.glVertexAttribPointer(3, 3, GL.GL_FLOAT, GL.GL_FALSE, stride, ctypes.c_void_p(32))

        GL.glBindVertexArray(0)
        self.index_count = len(indices)

    def update(self, dt: float) -> None:
        self.angle = (self.angle + self.rotation_speed * dt) % 360.0

    def _light_uniforms(self) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
        light_color = np.array([1.0, 1.0, 1.0], dtype=np.float32)
        if self.light_mode == "directional":
            light_pos = np.array([-0.3, -0.8, -1.0], dtype=np.float32)
            light_type = 0
            spot_direction = np.array([0.0, 0.0, -1.0], dtype=np.float32)
            spot_cutoff = -1.0
        elif self.light_mode == "spot":
            light_pos = np.array([0.0, 0.0, 2.5], dtype=np.float32)
            light_type = 2
            spot_direction = np.array([0.0, 0.0, -1.0], dtype=np.float32)
            spot_cutoff = math.cos(math.radians(25.0))
        else:
            light_pos = np.array([2.5, 2.5, 2.5], dtype=np.float32)
            light_type = 1
            spot_direction = np.array([0.0, -1.0, 0.0], dtype=np.float32)
            spot_cutoff = math.cos(math.radians(12.5))
        return light_pos, light_color, spot_direction, spot_cutoff, light_type

    def render(self, width: int, height: int) -> None:
        if not self.shader_program or not self.texture or not self.vao:
            return
        GL.glUseProgram(self.shader_program)
        aspect = width / max(1, height)
        fovy = math.radians(45.0)
        bounding = max(self.bounding_radius, 1e-3)
        vertical_distance = bounding / math.tan(fovy / 2.0)
        horizontal_fov = 2.0 * math.atan(math.tan(fovy / 2.0) * max(aspect, 1e-3))
        horizontal_distance = bounding / math.tan(max(horizontal_fov / 2.0, 1e-3))
        camera_distance = max(vertical_distance, horizontal_distance) + self.size * 2.0
        near_plane = max(0.1, camera_distance - (bounding + self.size * 2.0))
        far_plane = max(camera_distance + bounding + self.size * 4.0, near_plane + 10.0)

        projection = _perspective(fovy, aspect, near_plane, far_plane)
        eye_position = np.array([0.0, 0.0, camera_distance], dtype=np.float32)
        view = _look_at(
            eye=eye_position,
            target=np.array([0.0, 0.0, 0.0], dtype=np.float32),
            up=np.array([0.0, 1.0, 0.0], dtype=np.float32),
        )
        model = _rotation_matrix(self.angle, axis=np.array([0.0, 0.0, 1.0], dtype=np.float32))

        self.texture.bind(0)

        _set_uniform_mat4(self.shader_program, "u_projection", projection)
        _set_uniform_mat4(self.shader_program, "u_view", view)
        _set_uniform_mat4(self.shader_program, "u_model", model)
        _set_uniform_vec3(self.shader_program, "u_view_pos", eye_position)
        light_pos, light_color, spot_direction, spot_cutoff, light_type = self._light_uniforms()
        _set_uniform_vec3(self.shader_program, "u_light_pos", light_pos)
        _set_uniform_vec3(self.shader_program, "u_light_color", light_color)
        _set_uniform_vec3(self.shader_program, "u_spot_direction", spot_direction)
        _set_uniform_float(self.shader_program, "u_spot_cutoff", spot_cutoff)
        _set_uniform_int(self.shader_program, "u_light_type", light_type)
        _set_uniform_int(self.shader_program, "u_texture0", 0)

        GL.glBindVertexArray(self.vao)
        GL.glDrawElements(GL.GL_TRIANGLES, self.index_count, GL.GL_UNSIGNED_INT, None)
        GL.glBindVertexArray(0)

    def dispose(self) -> None:
        if self.texture:
            GL.glDeleteTextures(int(self.texture.handle))
            self.texture = None
        if self.vbo:
            GL.glDeleteBuffers(1, [self.vbo])
            self.vbo = None
        if self.ebo:
            GL.glDeleteBuffers(1, [self.ebo])
            self.ebo = None
        if self.vao:
            GL.glDeleteVertexArrays(1, [self.vao])
            self.vao = None
        if self.shader_program:
            GL.glDeleteProgram(self.shader_program)
            self.shader_program = None


def _perspective(fovy: float, aspect: float, near: float, far: float) -> np.ndarray:
    f = 1.0 / math.tan(fovy / 2.0)
    result = np.zeros((4, 4), dtype=np.float32)
    result[0, 0] = f / aspect
    result[1, 1] = f
    result[2, 2] = (far + near) / (near - far)
    result[2, 3] = (2 * far * near) / (near - far)
    result[3, 2] = -1.0
    return result


def _look_at(eye: np.ndarray, target: np.ndarray, up: np.ndarray) -> np.ndarray:
    zaxis = eye - target
    zaxis /= np.linalg.norm(zaxis)
    xaxis = np.cross(up, zaxis)
    xaxis /= np.linalg.norm(xaxis)
    yaxis = np.cross(zaxis, xaxis)

    result = np.identity(4, dtype=np.float32)
    result[0, :3] = xaxis
    result[1, :3] = yaxis
    result[2, :3] = zaxis
    result[0, 3] = -np.dot(xaxis, eye)
    result[1, 3] = -np.dot(yaxis, eye)
    result[2, 3] = -np.dot(zaxis, eye)
    return result


def _rotation_matrix(angle_degrees: float, axis: np.ndarray) -> np.ndarray:
    angle = math.radians(angle_degrees)
    axis = axis / np.linalg.norm(axis)
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    x, y, z = axis
    result = np.array(
        [
            [cos_a + x * x * (1 - cos_a), x * y * (1 - cos_a) - z * sin_a, x * z * (1 - cos_a) + y * sin_a, 0.0],
            [y * x * (1 - cos_a) + z * sin_a, cos_a + y * y * (1 - cos_a), y * z * (1 - cos_a) - x * sin_a, 0.0],
            [z * x * (1 - cos_a) - y * sin_a, z * y * (1 - cos_a) + x * sin_a, cos_a + z * z * (1 - cos_a), 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ],
        dtype=np.float32,
    )
    return result


def _set_uniform_mat4(program: int, name: str, matrix: np.ndarray) -> None:
    location = GL.glGetUniformLocation(program, name)
    # NumPy stores matrices in row-major order, while OpenGL expects column-major
    # data when ``transpose`` is ``GL_FALSE``.  Transposing here keeps the shader
    # math intuitive (row-major on the Python side) yet uploads the correct
    # column-major layout to the GPU, ensuring the model/view/projection
    # transforms behave as intended.
    GL.glUniformMatrix4fv(
        location,
        1,
        GL.GL_FALSE,
        np.ascontiguousarray(matrix.T, dtype=np.float32),
    )


def _set_uniform_vec3(program: int, name: str, vector: np.ndarray) -> None:
    location = GL.glGetUniformLocation(program, name)
    GL.glUniform3fv(location, 1, vector)


def _set_uniform_float(program: int, name: str, value: float) -> None:
    location = GL.glGetUniformLocation(program, name)
    GL.glUniform1f(location, value)


def _set_uniform_int(program: int, name: str, value: int) -> None:
    location = GL.glGetUniformLocation(program, name)
    GL.glUniform1i(location, value)


import ctypes  # noqa: E402  pylint: disable=wrong-import-position

"""Shader helper utilities."""
from __future__ import annotations

from OpenGL import GL


class ShaderCompilationError(RuntimeError):
    """Raised when shader compilation fails."""


def _compile_shader(source: str, shader_type: int) -> int:
    shader = GL.glCreateShader(shader_type)
    GL.glShaderSource(shader, source)
    GL.glCompileShader(shader)
    compiled = GL.glGetShaderiv(shader, GL.GL_COMPILE_STATUS)
    if not compiled:
        log = GL.glGetShaderInfoLog(shader).decode("utf-8")
        GL.glDeleteShader(shader)
        raise ShaderCompilationError(log)
    return shader


def compile_shader_program(vertex_source: str, fragment_source: str) -> int:
    """Compile a shader program and return its handle."""
    vertex_shader = _compile_shader(vertex_source, GL.GL_VERTEX_SHADER)
    fragment_shader = _compile_shader(fragment_source, GL.GL_FRAGMENT_SHADER)

    program = GL.glCreateProgram()
    GL.glAttachShader(program, vertex_shader)
    GL.glAttachShader(program, fragment_shader)
    GL.glLinkProgram(program)

    linked = GL.glGetProgramiv(program, GL.GL_LINK_STATUS)
    if not linked:
        log = GL.glGetProgramInfoLog(program).decode("utf-8")
        GL.glDeleteProgram(program)
        GL.glDeleteShader(vertex_shader)
        GL.glDeleteShader(fragment_shader)
        raise ShaderCompilationError(log)

    GL.glDetachShader(program, vertex_shader)
    GL.glDetachShader(program, fragment_shader)
    GL.glDeleteShader(vertex_shader)
    GL.glDeleteShader(fragment_shader)
    return program

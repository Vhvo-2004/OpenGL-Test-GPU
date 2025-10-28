"""Texture helpers for loading images into OpenGL."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from OpenGL import GL
from PIL import Image


@dataclass
class Texture:
    """Container referencing an OpenGL texture object."""

    handle: int
    width: int
    height: int

    def bind(self, unit: int = 0) -> None:
        GL.glActiveTexture(GL.GL_TEXTURE0 + unit)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.handle)


def _upload_image(
    image: Image.Image, *, repeat: bool = True, generate_mipmaps: bool = True
) -> Texture:
    """Upload an RGBA image into an OpenGL texture."""

    rgba_image = image.convert("RGBA")
    width, height = rgba_image.size
    data = np.array(rgba_image, dtype=np.uint8)

    handle = GL.glGenTextures(1)
    GL.glBindTexture(GL.GL_TEXTURE_2D, handle)
    GL.glTexImage2D(
        GL.GL_TEXTURE_2D,
        0,
        GL.GL_RGBA,
        width,
        height,
        0,
        GL.GL_RGBA,
        GL.GL_UNSIGNED_BYTE,
        data,
    )

    wrap_mode = GL.GL_REPEAT if repeat else GL.GL_CLAMP_TO_EDGE
    GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S, wrap_mode)
    GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T, wrap_mode)
    GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
    GL.glTexParameteri(
        GL.GL_TEXTURE_2D,
        GL.GL_TEXTURE_MIN_FILTER,
        GL.GL_LINEAR_MIPMAP_LINEAR if generate_mipmaps else GL.GL_LINEAR,
    )

    if generate_mipmaps:
        GL.glGenerateMipmap(GL.GL_TEXTURE_2D)

    GL.glBindTexture(GL.GL_TEXTURE_2D, 0)
    return Texture(handle=handle, width=width, height=height)


def load_texture(path: Path, *, repeat: bool = True, generate_mipmaps: bool = True) -> Texture:
    """Load an image file into an OpenGL texture."""

    image = Image.open(path)
    return load_texture_from_image(image, repeat=repeat, generate_mipmaps=generate_mipmaps)


def load_texture_from_image(
    image: Image.Image, *, repeat: bool = True, generate_mipmaps: bool = True
) -> Texture:
    """Create a texture from a pre-constructed PIL image."""

    return _upload_image(image, repeat=repeat, generate_mipmaps=generate_mipmaps)


def create_checkerboard_texture(size: int = 128, squares: int = 8) -> Image.Image:
    """Create a checkerboard PIL image for quick testing."""
    image = Image.new("RGBA", (size, size))
    pixels = image.load()
    block = size // squares
    for y in range(size):
        for x in range(size):
            if (x // block + y // block) % 2 == 0:
                pixels[x, y] = (255, 230, 170, 255)
            else:
                pixels[x, y] = (90, 140, 255, 255)
    return image


def create_gradient_texture(size: int = 256) -> Image.Image:
    """Create a smooth gradient image used as the default texture."""

    x = np.linspace(0.0, 1.0, size, dtype=np.float32)
    y = np.linspace(0.0, 1.0, size, dtype=np.float32)
    xv, yv = np.meshgrid(x, y)
    red = (255 * xv).astype(np.uint8)
    green = (255 * (1.0 - xv * 0.5)).astype(np.uint8)
    blue = (255 * yv).astype(np.uint8)
    alpha = np.full_like(red, 255, dtype=np.uint8)
    data = np.stack([red, green, blue, alpha], axis=-1)
    return Image.fromarray(data, mode="RGBA")

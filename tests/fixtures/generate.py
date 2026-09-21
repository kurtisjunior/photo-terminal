"""Regenerate the committed image fixtures.

    nix develop -c uv run --extra dev python tests/fixtures/generate.py

The outputs are deterministic, so re-running this on a clean tree produces no
diff.
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).parent


def _gradient(width: int, height: int, seed: int) -> Image.Image:
    """A smooth two-axis gradient. Cheap, deterministic, and visibly oriented."""
    image = Image.new("RGB", (width, height))
    pixels = image.load()
    assert pixels is not None
    for y in range(height):
        for x in range(width):
            pixels[x, y] = (
                x * 255 // max(width - 1, 1),
                y * 255 // max(height - 1, 1),
                ((x + y + seed) * 255 // max(width + height, 1)) % 256,
            )
    return image


def _framed_gradient(width: int, height: int, seed: int) -> Image.Image:
    """A gradient with a white inset border, so orientation is obvious by eye."""
    image = _gradient(width, height, seed)
    inset = round(min(width, height) * 0.0667)
    draw = ImageDraw.Draw(image)
    draw.rectangle(
        [inset, inset, width - inset - 1, height - inset - 1],
        outline=(255, 255, 255),
        width=6,
    )
    return image


def _photographic(width: int, height: int) -> Image.Image:
    """A large image whose entropy is in the range of a real photograph.

    Pure noise does not compress like a photo, and a flat gradient compresses
    far better than one, so neither exercises the optimizer's quality loop
    realistically. Blurred noise over a slow colour ramp lands in between.
    """
    noise = Image.effect_noise((width, height), 40).convert("L")
    noise = noise.filter(ImageFilter.GaussianBlur(2.2))
    noise_pixels = noise.load()
    assert noise_pixels is not None

    image = Image.new("RGB", (width, height))
    pixels = image.load()
    assert pixels is not None
    for y in range(height):
        vertical = y / height
        for x in range(width):
            grain = (noise_pixels[x, y] - 128) * 1.6
            pixels[x, y] = (
                max(0, min(255, int(80 + 150 * vertical + grain))),
                max(0, min(255, int(120 + 70 * math.sin(x / 300.0) + grain))),
                max(0, min(255, int(170 - 100 * vertical + grain * 0.6))),
            )
    return image


def main() -> None:
    _framed_gradient(300, 400, seed=0).save(HERE / "portrait_3x4.jpg", quality=92)
    _framed_gradient(400, 300, seed=64).save(HERE / "landscape_4x3.jpg", quality=92)
    _gradient(40, 30, seed=128).save(HERE / "tiny_40x30.png")
    _photographic(2400, 1800).save(HERE / "photo_2400x1800.jpg", "JPEG", quality=88)

    for name in sorted(p.name for p in HERE.glob("*.jpg")) + ["tiny_40x30.png"]:
        path = HERE / name
        with Image.open(path) as image:
            print(f"{name}: {image.size[0]}x{image.size[1]} {path.stat().st_size // 1024}KB")


if __name__ == "__main__":
    main()

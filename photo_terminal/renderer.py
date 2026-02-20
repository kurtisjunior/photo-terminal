"""In-process Pillow-based image renderer for ANSI half-block terminal display.

Converts images to colored Unicode half-block characters (▄) using 24-bit ANSI
escape codes. Each terminal cell represents two vertical pixels: the top pixel
as the background color and the bottom pixel as the foreground color.

This replaces shelling out to the `viu` subprocess for block-mode rendering,
reducing preview latency from ~100-300ms down to ~10-30ms by staying in-process.

Algorithm (standard half-block technique used by pixterm, ansipix, climage, etc.):
    1. Open image with PIL and convert to RGB
    2. Resize to (width, height * 2) pixels — two pixels per terminal row
    3. For each row pair, emit background color (top pixel) + foreground color
       (bottom pixel) + the lower half-block character ▄
    4. Apply run-length encoding: consecutive cells with identical fg+bg colors
       share a single color escape sequence
    5. Reset colors at end of each line
"""

import logging
from pathlib import Path
from typing import List, Tuple

from PIL import Image

logger = logging.getLogger(__name__)

# Unicode Lower Half Block — each terminal cell renders this character with
# the top pixel as background color and the bottom pixel as foreground color.
HALF_BLOCK = "\u2584"

# ANSI escape code components
ESC_RESET = "\033[0m"


def _composite_on_black(image: Image.Image) -> Image.Image:
    """Composite an RGBA image onto a black background.

    Args:
        image: PIL Image in RGBA mode

    Returns:
        PIL Image in RGB mode with alpha composited on black
    """
    background = Image.new("RGB", image.size, (0, 0, 0))
    background.paste(image, mask=image.split()[3])
    return background


def render_image_to_ansi_from_pil(image: Image.Image, width: int, height: int) -> List[str]:
    """Render a PIL Image to ANSI half-block art.

    Converts the image to colored Unicode half-block characters using 24-bit
    ANSI escape codes. Each terminal cell represents two vertical pixels.
    Applies run-length encoding to reduce output size when consecutive pixels
    share the same colors.

    Args:
        image: PIL Image object (any mode — will be converted to RGB)
        width: Width in terminal columns
        height: Height in terminal rows

    Returns:
        List of strings, one per terminal row, containing ANSI escape codes.
        On failure, returns a list containing an error message string.
    """
    try:
        # Handle transparency: composite RGBA onto black background
        if image.mode == "RGBA":
            image = _composite_on_black(image)
        elif image.mode != "RGB":
            image = image.convert("RGB")

        # Resize to target dimensions. Each terminal row represents 2 vertical
        # pixels, so we need height * 2 pixel rows.
        pixel_width = max(1, width)
        pixel_height = max(1, height * 2)
        image = image.resize((pixel_width, pixel_height), Image.LANCZOS)

        # Use load() for fast pixel access via indexing
        pixels = image.load()

        lines: List[str] = []

        for row in range(height):
            top_y = row * 2
            bot_y = top_y + 1

            parts: List[str] = []
            prev_bg: Tuple[int, int, int] = (-1, -1, -1)
            prev_fg: Tuple[int, int, int] = (-1, -1, -1)

            for x in range(pixel_width):
                bg = pixels[x, top_y]  # top pixel -> background
                fg = pixels[x, bot_y]  # bottom pixel -> foreground

                if bg == prev_bg and fg == prev_fg:
                    # Run-length: same colors, just emit the block character
                    parts.append(HALF_BLOCK)
                else:
                    # Emit new color escape sequences
                    br, bg_g, bb = bg
                    fr, fg_g, fb = fg
                    parts.append(
                        f"\033[48;2;{br};{bg_g};{bb}m"
                        f"\033[38;2;{fr};{fg_g};{fb}m"
                        f"{HALF_BLOCK}"
                    )
                    prev_bg = bg
                    prev_fg = fg

            parts.append(ESC_RESET)
            lines.append("".join(parts))

        return lines

    except Exception as e:
        logger.error("Failed to render image: %s", e, exc_info=True)
        return [f"[Render error: {e}]"]


def render_image_to_ansi(image_path: Path, width: int, height: int) -> List[str]:
    """Render an image file to ANSI half-block art.

    Opens the image at the given path and converts it to colored Unicode
    half-block characters using 24-bit ANSI escape codes. Each terminal cell
    represents two vertical pixels.

    Args:
        image_path: Path to image file
        width: Width in terminal columns
        height: Height in terminal rows

    Returns:
        List of strings, one per terminal row, containing ANSI escape codes.
        On failure, returns a list containing an error message string.
    """
    try:
        with Image.open(image_path) as img:
            # Force load so we own the pixel data after the context manager exits
            img.load()
            return render_image_to_ansi_from_pil(img, width, height)
    except FileNotFoundError:
        logger.error("Image file not found: %s", image_path)
        return [f"[File not found: {image_path}]"]
    except Exception as e:
        logger.error("Failed to open image %s: %s", image_path, e, exc_info=True)
        return [f"[Error opening image: {e}]"]

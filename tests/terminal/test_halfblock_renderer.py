"""The half-block renderer's first direct coverage.

It has been the production preview path on every non-Kitty terminal since it was
written, and no test has ever imported it. Its output only ran during the suite
by accident, against zero-byte fixture files, where it hit its own except branch
and returned an error string nothing asserted on.
"""

from __future__ import annotations

import re

import pytest
from PIL import Image

from photo_terminal.terminal.preview.halfblock import (
    HALF_BLOCK,
    render_image_to_ansi,
    render_image_to_ansi_from_pil,
)

SGR = re.compile(r"\033\[[0-9;]*m")


def visible(line: str) -> str:
    return SGR.sub("", line)


class TestShape:
    @pytest.mark.parametrize(
        ("width", "height"),
        [(10, 5), (1, 1), (117, 56), (40, 1), (1, 40)],
    )
    def test_one_line_per_row_and_one_block_per_column(self, portrait_3x4, width, height):
        lines = render_image_to_ansi(portrait_3x4, width, height)

        assert len(lines) == height
        for line in lines:
            assert visible(line) == HALF_BLOCK * width

    def test_every_line_resets_its_colours(self, portrait_3x4):
        """Without the reset the last cell's colours bleed into whatever the
        painter writes next on that row."""
        for line in render_image_to_ansi(portrait_3x4, 12, 6):
            assert line.endswith("\033[0m")

    def test_a_row_is_two_pixels_tall(self):
        """The top pixel is the background, the bottom pixel the foreground, so
        a 1x2 image renders as one cell carrying both colours."""
        image = Image.new("RGB", (1, 2))
        image.putpixel((0, 0), (255, 0, 0))
        image.putpixel((0, 1), (0, 0, 255))

        (line,) = render_image_to_ansi_from_pil(image, 1, 1)

        assert "\033[48;2;255;0;0m" in line
        assert "\033[38;2;0;0;255m" in line


class TestColour:
    def test_a_flat_image_coalesces_into_a_single_colour_escape(self):
        """Run-length encoding: identical neighbours share one escape."""
        lines = render_image_to_ansi_from_pil(Image.new("RGB", (40, 40), (10, 20, 30)), 20, 5)

        for line in lines:
            assert len(SGR.findall(line)) == 3  # one bg, one fg, one reset

    def test_a_striped_image_emits_an_escape_per_change(self):
        image = Image.new("RGB", (4, 2))
        for x in range(4):
            colour = (255, 255, 255) if x % 2 else (0, 0, 0)
            image.putpixel((x, 0), colour)
            image.putpixel((x, 1), colour)

        (line,) = render_image_to_ansi_from_pil(image, 4, 1)

        assert len(SGR.findall(line)) == 4 * 2 + 1

    def test_transparency_is_composited_onto_black(self):
        image = Image.new("RGBA", (2, 2), (255, 255, 255, 0))
        (line,) = render_image_to_ansi_from_pil(image, 2, 1)

        assert "\033[48;2;0;0;0m" in line

    def test_a_palette_image_is_converted_rather_than_rejected(self):
        lines = render_image_to_ansi_from_pil(Image.new("P", (8, 8)), 4, 2)
        assert len(lines) == 2


class TestFailure:
    def test_a_missing_file_returns_a_message_rather_than_raising(self, tmp_path):
        lines = render_image_to_ansi(tmp_path / "absent.jpg", 10, 5)

        assert len(lines) == 1
        assert "not found" in lines[0].lower()

    def test_a_file_that_is_not_an_image_returns_a_message(self, tmp_path):
        path = tmp_path / "broken.jpg"
        path.write_bytes(b"not an image")

        lines = render_image_to_ansi(path, 10, 5)

        assert len(lines) == 1
        assert lines[0].startswith("[")

    def test_a_zero_byte_file_returns_a_message(self, tmp_path):
        """The shape the old ``.touch()`` fixtures produced, now asserted on
        rather than silently swallowed in a worker thread."""
        path = tmp_path / "empty.jpg"
        path.touch()

        lines = render_image_to_ansi(path, 10, 5)

        assert len(lines) == 1
        assert lines[0].startswith("[")

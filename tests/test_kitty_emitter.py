"""The Kitty graphics protocol emitter: framing, chunking and control keys.

Every assertion here is on the bytes actually produced. The path this replaces
was an opaque blob from a subprocess, which is precisely why nothing about it
could be asserted and why it stayed broken under a green suite.
"""

from __future__ import annotations

import base64
import io

import pytest
from PIL import Image

from photo_terminal.terminal.geometry import Size
from photo_terminal.terminal.preview import kitty

from .conftest import FakeTerminal


def commands(payload: bytes) -> list[dict[str, str]]:
    terminal = FakeTerminal()
    terminal.write(payload)
    return terminal.kitty_commands()


def chunk_payloads(payload: bytes) -> list[bytes]:
    """The base64 body of each control block, in order."""
    bodies = []
    for block in payload.split(b"\033_G")[1:]:
        body = block.split(b"\033\\", 1)[0]
        bodies.append(body.split(b";", 1)[1])
    return bodies


class TestTransmitAndPlace:
    def test_the_placement_is_bounded_and_quiet(self):
        payload = kitty.transmit_and_place(b"x" * 10, Size(58, 44), image_id=7)
        first = commands(payload)[0]

        assert first["a"] == "T"
        assert first["f"] == "100"  # PNG
        assert first["t"] == "d"  # inline base64, not a file path
        assert first["c"] == "58"
        assert first["r"] == "44"
        assert first["C"] == "1"  # the placement must not move the cursor
        assert first["q"] == "2"  # no replies into our raw-mode stdin
        assert first["i"] == "7"  # individually deletable

    def test_every_control_block_is_escape_framed(self):
        payload = kitty.transmit_and_place(b"x" * 20_000, Size(10, 5), image_id=1)

        assert payload.startswith(b"\033_G")
        assert payload.endswith(b"\033\\")
        assert payload.count(b"\033_G") == payload.count(b"\033\\")

    def test_control_keys_ride_on_the_first_chunk_only(self):
        payload = kitty.transmit_and_place(b"x" * 20_000, Size(10, 5), image_id=1)
        blocks = commands(payload)

        assert len(blocks) > 1
        for block in blocks[1:]:
            assert set(block) == {"m"}

    def test_every_chunk_but_the_last_sets_more(self):
        payload = kitty.transmit_and_place(b"x" * 20_000, Size(10, 5), image_id=1)
        blocks = commands(payload)

        assert [block["m"] for block in blocks[:-1]] == ["1"] * (len(blocks) - 1)
        assert blocks[-1]["m"] == "0"

    def test_a_payload_that_fits_in_one_chunk_is_a_single_block(self):
        payload = kitty.transmit_and_place(b"x" * 8, Size(4, 2), image_id=3)
        blocks = commands(payload)

        assert len(blocks) == 1
        assert blocks[0]["m"] == "0"
        assert blocks[0]["a"] == "T"

    def test_no_chunk_exceeds_the_protocol_limit(self):
        payload = kitty.transmit_and_place(b"x" * 100_000, Size(10, 5), image_id=1)

        for body in chunk_payloads(payload):
            assert len(body) <= kitty.CHUNK_BYTES

    def test_the_chunks_reassemble_to_the_source_png(self):
        png = bytes(range(256)) * 200
        payload = kitty.transmit_and_place(png, Size(10, 5), image_id=1)

        assert base64.standard_b64decode(b"".join(chunk_payloads(payload))) == png

    def test_the_payload_carries_no_carriage_return(self):
        """The 2026-09-21 bug in one line: a ``\\r`` in the payload resets the
        cursor to column 1 and walks the preview across the file list."""
        payload = kitty.transmit_and_place(b"x" * 20_000, Size(10, 5), image_id=1)
        assert b"\r" not in payload


class TestPlacementLifecycle:
    def test_re_placing_needs_no_pixels(self):
        payload = kitty.place(Size(58, 44), image_id=7)

        assert commands(payload) == [{"a": "p", "i": "7", "c": "58", "r": "44", "C": "1", "q": "2"}]

    def test_hiding_keeps_the_pixels(self):
        """Lowercase ``d=i``: the placement goes, the transmitted image stays,
        so navigating back is one short command instead of a re-transmission."""
        assert commands(kitty.hide(7)) == [{"a": "d", "d": "i", "i": "7", "q": "2"}]

    def test_evicting_frees_the_pixels(self):
        """Uppercase ``d=I``, fired only when our own cache drops the entry."""
        assert commands(kitty.evict(7)) == [{"a": "d", "d": "I", "i": "7", "q": "2"}]

    def test_deletion_is_quiet_too(self):
        for payload in (kitty.hide(7), kitty.evict(7)):
            assert commands(payload)[0]["q"] == "2"


class TestImageIds:
    def test_ids_are_unique_within_a_sequence(self):
        ids = kitty.image_ids()
        assert len({next(ids) for _ in range(100)}) == 100

    def test_ids_fit_the_protocol_field(self):
        ids = kitty.image_ids()
        for _ in range(100):
            assert 0 < next(ids) < 2**32


class TestEncodePng:
    @pytest.mark.parametrize("px", [Size(64, 32), Size(120, 160), Size(8, 16)])
    def test_the_png_is_exactly_the_requested_pixel_size(self, portrait_3x4, px):
        """The resize is what leaves the terminal nothing to scale."""
        with Image.open(portrait_3x4) as image:
            png = kitty.encode_png(image, px)

        with Image.open(io.BytesIO(png)) as decoded:
            assert decoded.format == "PNG"
            assert decoded.size == (px.w, px.h)

    def test_a_palette_image_with_transparency_keeps_its_alpha(self):
        source = Image.new("P", (8, 8))
        source.info["transparency"] = 0
        png = kitty.encode_png(source, Size(8, 8))

        with Image.open(io.BytesIO(png)) as decoded:
            assert decoded.mode in ("RGBA", "LA", "PA", "P")

    def test_a_greyscale_image_is_converted_rather_than_rejected(self):
        png = kitty.encode_png(Image.new("L", (10, 10), 128), Size(10, 10))

        with Image.open(io.BytesIO(png)) as decoded:
            assert decoded.size == (10, 10)

    def test_a_zero_pixel_request_still_produces_a_valid_png(self):
        png = kitty.encode_png(Image.new("RGB", (4, 4)), Size(0, 0))

        with Image.open(io.BytesIO(png)) as decoded:
            assert decoded.size == (1, 1)

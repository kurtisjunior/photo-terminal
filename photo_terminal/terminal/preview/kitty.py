"""Kitty graphics protocol emitter.

Pure string building: every function returns bytes and writes nothing, which is
the same contract :mod:`~photo_terminal.terminal.preview.halfblock` has and the
reason both are testable.

A PNG is transmitted as chunked base64 (``m=1`` on every chunk but the last) and
placed into a cell rectangle with ``c``/``r``. The image has already been resized
to exactly ``cells x cell_px`` pixels, so the terminal has nothing left to scale
- which matters because Ghostty stretches rather than letterboxes when both
``c`` and ``r`` are given.

Four control keys carry the design:

``a=T``
    Transmit and place in one command. ``f=100`` says the payload is PNG,
    ``t=d`` says it is inline base64 rather than a file path.
``C=1``
    Do not move the cursor. A placement therefore cannot disturb the rest of the
    frame, and the frame's remaining writes land where the painter put them.
``q=2``
    Suppress both the OK and the error response. Without this the terminal
    answers on the same stdin the input loop is polling in raw mode, and stray
    characters appear in the UI.
``i=<id>``
    An explicit image id, which makes the placement individually deletable.
    ``\\033[2J`` clears images but no other text erasure touches them, so ``a=d``
    is the only sanctioned way to remove one.

``i`` is a 32-bit space shared with every other program on the terminal. The
spec's collision-free route (``I=``, image *number*) requires reading the
terminal's reply, which is exactly what ``q=2`` is there to prevent, so we take
a base id from the PID and accept the negligible collision risk of a full-screen
application.
"""

from __future__ import annotations

import base64
import itertools
import os
from io import BytesIO

from PIL import Image

from photo_terminal.terminal.geometry import Size

CHUNK_BYTES = 4096
"""The protocol's maximum escape-sequence payload. A multiple of 4, so base64
can be split on it without re-padding."""

_GRAPHICS_START = b"\033_G"
_GRAPHICS_END = b"\033\\"

# The id space is 32-bit and shared with other programs on the same terminal.
# 16 bits of PID plus a 12-bit counter keeps ids unique within a process and
# unlikely to collide across concurrent ones.
_ID_BASE = (os.getpid() & 0xFFFF) << 12


def image_ids() -> itertools.count[int]:
    """A fresh sequence of process-scoped image ids."""
    return itertools.count(_ID_BASE + 1)


def encode_png(image: Image.Image, px: Size) -> bytes:
    """Resize ``image`` to exactly ``px`` and encode it as a PNG.

    The resize is the whole trick: the placement rectangle is a whole number of
    cells and ``px`` is exactly that rectangle in pixels, so whether the terminal
    stretches or letterboxes, the transform it applies is the identity.
    """
    source = image
    if source.mode == "P" and "transparency" in source.info:
        source = source.convert("RGBA")
    elif source.mode not in ("RGB", "RGBA"):
        source = source.convert("RGB")

    resized = source.resize((max(1, px.w), max(1, px.h)), Image.Resampling.LANCZOS)
    buffer = BytesIO()
    resized.save(buffer, format="PNG", compress_level=1)
    return buffer.getvalue()


def _command(keys: str, payload: bytes = b"") -> bytes:
    return _GRAPHICS_START + keys.encode("ascii") + b";" + payload + _GRAPHICS_END


def transmit_and_place(png: bytes, cells: Size, image_id: int) -> bytes:
    """Transmit ``png`` and place it in a ``cells`` rectangle at the cursor.

    Control keys ride on the first chunk only; every later chunk carries just
    ``m``, per the protocol.
    """
    payload = base64.standard_b64encode(png)
    chunks = [payload[at : at + CHUNK_BYTES] for at in range(0, len(payload), CHUNK_BYTES)] or [b""]

    out = bytearray()
    last = len(chunks) - 1
    for index, chunk in enumerate(chunks):
        more = 0 if index == last else 1
        if index == 0:
            keys = f"a=T,f=100,t=d,i={image_id},c={cells.w},r={cells.h},C=1,q=2,m={more}"
        else:
            keys = f"m={more}"
        out += _command(keys, chunk)
    return bytes(out)


def place(cells: Size, image_id: int) -> bytes:
    """Re-place an image whose pixels are still resident in the terminal.

    Navigating away hides a placement but leaves the pixels, so coming back is
    this one short command rather than a re-transmission.
    """
    return _command(f"a=p,i={image_id},c={cells.w},r={cells.h},C=1,q=2")


def hide(image_id: int) -> bytes:
    """Delete the placement, keep the pixels. Lowercase ``d=i``."""
    return _command(f"a=d,d=i,i={image_id},q=2")


def evict(image_id: int) -> bytes:
    """Delete the placement *and* free the pixels. Uppercase ``d=I``.

    Fired only when our own cache evicts the entry, so the terminal's memory
    tracks ours instead of growing for the lifetime of the screen.
    """
    return _command(f"a=d,d=I,i={image_id},q=2")

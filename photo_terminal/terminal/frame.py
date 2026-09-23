"""A buffered painter: build a frame in one buffer, write it once.

Every screen already batched its output into a ``parts`` list and flushed
exactly once, which is what keeps the UI flicker-free. This promotes that idiom
from an inline pattern to a type, and fixes the one place it broke down: the
graphics path did ``sys.stdout.write(text)`` followed by a separate
``sys.stdout.buffer.write(blob)`` - two writes, two flushes, and an interleaving
hazard between them. :class:`Frame` keeps text and binary segments ordered in a
single byte buffer, so a placement cannot land out of order with the text around
it.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from typing import Protocol

from photo_terminal.terminal.geometry import Point

CLEAR_AND_HOME = "\033[2J\033[H"
HOME = "\033[H"
HIDE_CURSOR = "\033[?25l"
SHOW_CURSOR = "\033[?25h"


class ByteSink(Protocol):
    """The minimum a :class:`Frame` needs to flush itself."""

    def write(self, data: bytes, /) -> int: ...

    def flush(self) -> None: ...


def move_to(at: Point) -> str:
    """The absolute cursor-position escape for a 1-based cell coordinate."""
    return f"\033[{at.row};{at.col}H"


class Frame:
    """An ordered buffer of text and binary segments, flushed in one write."""

    def __init__(self) -> None:
        self._buffer = bytearray()

    def write(self, data: str | bytes) -> None:
        """Append raw content, already positioned by whatever produced it."""
        if isinstance(data, str):
            self._buffer.extend(data.encode("utf-8", errors="replace"))
        else:
            self._buffer.extend(data)

    def place(self, at: Point, content: str | bytes) -> None:
        """Position the cursor at ``at``, then append ``content``."""
        self.write(move_to(at))
        self.write(content)

    def place_lines(self, at: Point, lines: Sequence[str]) -> None:
        """Append ``lines`` downward from ``at``, one absolute anchor per row.

        The per-row anchor is the whole point: a single anchor plus embedded
        newlines is what let the old preview walk across the file list, because
        a ``\\r`` or a wrapped row silently returns the cursor to column 1.
        """
        for offset, line in enumerate(lines):
            self.place(Point(at.col, at.row + offset), line)

    @property
    def payload(self) -> bytes:
        return bytes(self._buffer)

    def __len__(self) -> int:
        return len(self._buffer)

    def flush(self, sink: ByteSink | None = None) -> None:
        """Write the whole frame to ``sink`` (default stdout) and flush it once."""
        if not self._buffer:
            return
        target = sink if sink is not None else _stdout_bytes()
        target.write(bytes(self._buffer))
        target.flush()
        self._buffer.clear()


def _stdout_bytes() -> ByteSink:
    """The binary side of ``sys.stdout``, or a text shim when there isn't one.

    ``sys.stdout`` is replaced by test harnesses and by pytest's capture, not all
    of which expose ``.buffer``, so fall back to decoding rather than failing.
    """
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is not None:
        return buffer  # type: ignore[no-any-return]
    return _TextSink(sys.stdout)


class _TextSink:
    """Adapts a text stream to the :class:`ByteSink` protocol."""

    def __init__(self, stream: object) -> None:
        self._stream = stream

    def write(self, data: bytes, /) -> int:
        self._stream.write(data.decode("utf-8", errors="replace"))  # type: ignore[attr-defined]
        return len(data)

    def flush(self) -> None:
        self._stream.flush()  # type: ignore[attr-defined]

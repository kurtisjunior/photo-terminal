"""One preview, painted or erased, whatever the terminal turned out to be.

:class:`PreviewFrame` is the seam that removes the ``bytes | list[str]``
ambiguity the old cache carried, and with it the prefix-sniffing coercion that
existed only to reconcile the two shapes. A screen calls :meth:`paint` and
:meth:`erase` and never learns which implementation it is holding.

Every implementation reports the footprint it actually occupies, in cells, and
never paints outside it. That is the invariant the old graphics path had no way
to state, let alone hold.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from photo_terminal.terminal.frame import move_to
from photo_terminal.terminal.geometry import Point, Size
from photo_terminal.terminal.preview import kitty

SGR_RESET = "\033[0m"


class PreviewFrame(Protocol):
    """A preview that knows how to draw and undraw itself.

    Deliberately not ``runtime_checkable``: a protocol with a data member
    cannot be used with ``isinstance``, and callers that need to know which
    implementation they hold should name it.
    """

    cells: Size
    """The footprint actually occupied, in terminal cells."""

    def paint(self, at: Point) -> bytes:
        """Bytes that draw this preview with its top-left corner at ``at``."""
        ...

    def erase(self, at: Point) -> bytes:
        """Bytes that remove what :meth:`paint` drew at ``at``."""
        ...


def _rows(at: Point, count: int, content: list[str]) -> bytes:
    out: list[str] = []
    for offset in range(count):
        out.append(move_to(Point(at.col, at.row + offset)))
        out.append(content[offset])
    return "".join(out).encode("utf-8", errors="replace")


@dataclass
class HalfBlockFrame:
    """Rows of 24-bit ANSI half-blocks, one absolute anchor per row.

    The per-row anchor is what keeps the preview inside its column. The rows are
    padded to exactly ``cells.w`` visible characters rather than terminated with
    ``\\033[K``, so nothing right of the box is erased either.
    """

    lines: list[str]
    cells: Size

    def paint(self, at: Point) -> bytes:
        rows = [f"{line}{SGR_RESET}" for line in self.lines[: self.cells.h]]
        rows += [" " * self.cells.w] * (self.cells.h - len(rows))
        return _rows(at, self.cells.h, rows)

    def erase(self, at: Point) -> bytes:
        blank = " " * self.cells.w
        return _rows(at, self.cells.h, [blank] * self.cells.h)


@dataclass
class KittyFrame:
    """One Kitty graphics placement of a PNG already sized to its rectangle.

    The frame remembers whether the terminal still holds its pixels.
    :meth:`paint` transmits on the first showing and re-places on every later
    one; :meth:`erase` deletes the placement but keeps the pixels, so navigating
    back is a single short command. :meth:`evict` is the uppercase deletion that
    frees them, and only the cache calls it.
    """

    png: bytes
    cells: Size
    image_id: int
    resident: bool = field(default=False)

    def paint(self, at: Point) -> bytes:
        anchor = move_to(at).encode("ascii")
        if self.resident:
            return anchor + kitty.place(self.cells, self.image_id)
        self.resident = True
        return anchor + kitty.transmit_and_place(self.png, self.cells, self.image_id)

    def erase(self, at: Point) -> bytes:
        del at  # a placement is deleted by id, not by position
        return kitty.hide(self.image_id)

    def evict(self) -> bytes:
        """Free the terminal's copy of the pixels."""
        self.resident = False
        return kitty.evict(self.image_id)


@dataclass
class MessageFrame:
    """A single line of text standing in for an image.

    Used for the loading placeholder, for render failures, and for a preview box
    too small to draw into. It is a ``PreviewFrame`` like any other, which is
    what lets the screen erase a placeholder exactly the way it erases a photo.
    """

    text: str
    width: int
    cells: Size = field(init=False)

    def __post_init__(self) -> None:
        self.width = max(0, self.width)
        self.text = self.text[: self.width]
        self.cells = Size(self.width, 1)

    def paint(self, at: Point) -> bytes:
        return _rows(at, 1, [self.text.ljust(self.width)])

    def erase(self, at: Point) -> bytes:
        return _rows(at, 1, [" " * self.width])

"""Cell and pixel geometry for the terminal UI.

Two units circulate here and they are never interchangeable:

* **cells** - terminal columns and rows, which is what cursor addressing and the
  Kitty protocol's ``c``/``r`` keys speak.
* **pixels** - what an image is made of, and what ``TIOCGWINSZ`` reports
  alongside the cell dimensions.

:class:`CellMetrics` is the bridge. It matters because the Kitty graphics
protocol's sizing is *not* letterboxed on every terminal: Ghostty's
``graphics_storage.zig`` is explicit that with both ``c`` and ``r`` set it
computes ``cell_width * columns`` by ``cell_height * rows`` and stretches to
fill, with no aspect-ratio adjustment anywhere. Relying on the terminal to
letterbox would therefore reproduce the exact distortion we are fixing, one
layer down.

:func:`fit` makes us independent of it. It returns a rectangle that is a whole
number of cells in both axes *and* the exact pixel size of that rectangle. The
image is resized to precisely that pixel size, so the terminal's stretch is the
identity transform - which is true whichever reading of the spec the terminal
implements.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import NamedTuple

# A cell is assumed to be twice as tall as it is wide when the terminal does not
# report its pixel dimensions. The absolute numbers only matter for the Kitty
# path, which is only taken by terminals that do report them; the 1:2 ratio is
# what keeps aspect ratios correct on the half-block path, where one cell really
# is two stacked pixels.
ASSUMED_CELL_PX = (8, 16)


class Size(NamedTuple):
    """A width/height pair. Units are stated by the field that holds it."""

    w: int
    h: int


class Point(NamedTuple):
    """A 1-based cell coordinate, matching ANSI cursor addressing."""

    col: int
    row: int


@dataclass(frozen=True)
class Rect:
    """A 1-based, inclusive-origin rectangle of terminal cells."""

    left: int
    top: int
    width: int
    height: int

    @property
    def origin(self) -> Point:
        return Point(self.left, self.top)

    @property
    def size(self) -> Size:
        return Size(self.width, self.height)

    @property
    def is_empty(self) -> bool:
        return self.width <= 0 or self.height <= 0

    @property
    def cells(self) -> frozenset[Point]:
        return frozenset(
            Point(col, row)
            for row in range(self.top, self.top + self.height)
            for col in range(self.left, self.left + self.width)
        )

    def __or__(self, other: Rect | frozenset[Point]) -> frozenset[Point]:
        return self.cells | (other.cells if isinstance(other, Rect) else other)

    __ror__ = __or__


@dataclass(frozen=True)
class CellMetrics:
    """The pixel size of one terminal cell.

    ``measured`` records whether the terminal actually told us, so a caller can
    tell a real measurement from the 1:2 fallback without comparing magic
    numbers.
    """

    px: Size
    measured: bool

    @property
    def aspect(self) -> float:
        """Cell height divided by cell width. 2.0 for a typical terminal font."""
        return self.px.h / self.px.w

    @classmethod
    def assumed(cls) -> CellMetrics:
        """The fallback: a cell twice as tall as it is wide."""
        return cls(px=Size(*ASSUMED_CELL_PX), measured=False)

    @classmethod
    def probe(cls, fd: int) -> CellMetrics:
        """Measure one cell via ``ioctl(fd, TIOCGWINSZ)``.

        The ioctl reports ``rows, cols, xpixel, ypixel``. Ghostty, Kitty and
        WezTerm populate the pixel fields - Ghostty derives its own cell size by
        exactly this division - so dividing gives us the same number the
        terminal is using. When the fields are zero, or the fd is not a
        terminal, we fall back to the 1:2 assumption.
        """
        try:
            import fcntl
            import termios

            packed = fcntl.ioctl(fd, termios.TIOCGWINSZ, struct.pack("HHHH", 0, 0, 0, 0))
            rows, cols, xpixel, ypixel = struct.unpack("HHHH", packed)
        except (OSError, ValueError, ImportError, AttributeError):
            return cls.assumed()

        if rows <= 0 or cols <= 0 or xpixel <= 0 or ypixel <= 0:
            return cls.assumed()

        cell = Size(xpixel // cols, ypixel // rows)
        if cell.w <= 0 or cell.h <= 0:
            return cls.assumed()
        return cls(px=cell, measured=True)


@dataclass(frozen=True)
class Placement:
    """Where an image goes: a whole number of cells, and its exact pixel size.

    ``px`` is always ``cells.w * cell.w`` by ``cells.h * cell.h``. Resizing the
    source to ``px`` is what makes the terminal's own scaling a no-op.
    """

    cells: Size
    px: Size

    @property
    def is_empty(self) -> bool:
        return self.cells.w <= 0 or self.cells.h <= 0


EMPTY_PLACEMENT = Placement(cells=Size(0, 0), px=Size(0, 0))


def fit(source_px: Size, box_cells: Size, cell: CellMetrics) -> Placement:
    """Largest aspect-correct, cell-aligned rectangle that fits ``box_cells``.

    Args:
        source_px: The source image's own pixel dimensions.
        box_cells: The available box, in terminal cells.
        cell: The pixel size of one cell.

    Returns:
        A :class:`Placement` whose ``cells`` never exceeds ``box_cells`` in
        either axis, and whose ``px`` is exactly that many whole cells. The
        scale is capped at 1.0, so a source smaller than the box is shown at
        (or just under) its native resolution rather than blown up.

    Flooring the cell count is what keeps the result inside the box, and it is
    also what bounds the aspect error: the drawn rectangle is within one cell of
    the mathematically ideal one in each axis.
    """
    if source_px.w <= 0 or source_px.h <= 0 or box_cells.w <= 0 or box_cells.h <= 0:
        return EMPTY_PLACEMENT

    scale = min(
        box_cells.w * cell.px.w / source_px.w,
        box_cells.h * cell.px.h / source_px.h,
        1.0,
    )

    cells = Size(
        max(1, min(box_cells.w, int(source_px.w * scale / cell.px.w))),
        max(1, min(box_cells.h, int(source_px.h * scale / cell.px.h))),
    )
    return Placement(cells=cells, px=Size(cells.w * cell.px.w, cells.h * cell.px.h))

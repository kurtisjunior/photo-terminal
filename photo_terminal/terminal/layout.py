"""The two-pane screen layout, computed in exactly one place.

Before this module the same numbers were recomputed at six call sites from two
spellings of the same constant, with a size clamp at two of the six and none at
the other four - which is why the graphics preview had no bound at all and ran
off the bottom and the right of the window.

Everything a screen needs to know about where things go now comes from one
frozen :class:`Layout`, built once per render from the terminal size.

The list pane is *responsive*. It was a flat 55 columns, which is a good width
on the 178-column window in the bug report and a terrible one on an 80-column
window: 55 for the list plus the gutter and the right margin left 19 columns of
preview, one short of the threshold, so a standard-width terminal got no
preview at all. The pane now takes a fraction of the window, floored at a width
that still fits a readable filename and capped at the 55 it has always had.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

from photo_terminal.terminal.geometry import CellMetrics, Rect

FALLBACK_TERMINAL_SIZE = os.terminal_size((120, 40))
"""What to assume when stdout is not a terminal at all."""

PREFERRED_LIST_WIDTH = 55
"""What the file list gets when the window is wide enough to spare it."""

MIN_LIST_WIDTH = 36
"""Narrower than this the list cannot show a filename, so it stops shrinking.

Below the width at which both panes are usable the preview is dropped entirely
and the list takes the whole window, which is a better answer than two useless
columns.
"""

LIST_SHARE = (2, 5)
"""The list's share of a window too narrow for its preferred width, as a ratio."""

GUTTER = 4
"""Blank columns between the list pane and the preview."""

RIGHT_MARGIN = 2
"""The preview stops two columns short of the right edge."""

FOOTER_HEIGHT = 2
"""Two rows reserved at the bottom, so nothing is drawn against the window edge."""

MIN_PREVIEW_WIDTH = 20
MIN_PREVIEW_HEIGHT = 10


@dataclass(frozen=True)
class Layout:
    """Where each region of the screen is, in 1-based terminal cells."""

    list_pane: Rect
    preview_box: Rect
    footer: Rect
    cell: CellMetrics

    @classmethod
    def for_terminal(cls, size: os.terminal_size, cell: CellMetrics) -> Layout:
        """Split a terminal of ``size`` into list pane, preview box and footer.

        When the window cannot give the preview a usable box, the preview box
        comes back empty and the list pane takes the full width. A screen tests
        that with :attr:`preview_suppressed` and shows a message instead.
        """
        columns = max(0, size.columns)
        lines = max(0, size.lines)
        body_height = max(0, lines - FOOTER_HEIGHT)

        list_width = min(columns, _list_width_for(columns))
        preview_left = list_width + GUTTER + 1
        # The last column the preview may occupy, so its width follows from the
        # left edge rather than from a second independently-maintained constant.
        preview_width = max(0, (columns - RIGHT_MARGIN) - preview_left + 1)

        if preview_width < MIN_PREVIEW_WIDTH or body_height < MIN_PREVIEW_HEIGHT:
            list_width = columns
            preview_left = columns + 1
            preview_width = 0

        return cls(
            list_pane=Rect(left=1, top=1, width=list_width, height=body_height),
            preview_box=Rect(
                left=preview_left,
                top=1,
                width=preview_width,
                height=body_height if preview_width else 0,
            ),
            footer=Rect(
                left=1,
                top=body_height + 1,
                width=columns,
                height=min(FOOTER_HEIGHT, lines),
            ),
            cell=cell,
        )

    @property
    def preview_suppressed(self) -> bool:
        """Whether this window is too small to draw a preview into.

        Under 20 columns or 10 rows a photograph is a handful of unreadable
        cells, so the screen shows a short message instead and gives the space
        to the file list.
        """
        return self.preview_box.is_empty


def _list_width_for(columns: int) -> int:
    """The file list's width in a window ``columns`` wide.

    Its preferred width on a wide window, a fixed share of a narrower one, and
    never below the width at which a filename stops being readable.
    """
    numerator, denominator = LIST_SHARE
    share = columns * numerator // denominator
    return max(MIN_LIST_WIDTH, min(PREFERRED_LIST_WIDTH, share))


# --------------------------------------------------------------------------- #
# Measuring the terminal
# --------------------------------------------------------------------------- #


def _stdout_fd() -> int | None:
    """The descriptor we are painting to, or ``None`` when there isn't one.

    Both the cell measurement and the size sample have to ask the *same*
    descriptor, or they can disagree about which terminal they describe.
    """
    try:
        fd = sys.stdout.fileno()
    except (OSError, AttributeError, ValueError):
        return None
    return fd if isinstance(fd, int) else None


def sample_terminal_size() -> os.terminal_size:
    """The terminal's cell dimensions, with a fallback for a detached stdout."""
    fd = _stdout_fd()
    try:
        return os.get_terminal_size() if fd is None else os.get_terminal_size(fd)
    except OSError:
        return FALLBACK_TERMINAL_SIZE


def probe_cell_metrics() -> CellMetrics:
    """Measure one cell in pixels, falling back to the 1:2 assumption."""
    fd = _stdout_fd()
    return CellMetrics.assumed() if fd is None else CellMetrics.probe(fd)

"""The two-pane screen layout, computed in exactly one place.

Before this module the same numbers were recomputed at six call sites from two
spellings of the same constant, with a size clamp at two of the six and none at
the other four - which is why the graphics preview had no bound at all and ran
off the bottom and the right of the window.

Everything a screen needs to know about where things go now comes from one
frozen :class:`Layout`, built once per render from the terminal size.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from photo_terminal.terminal.geometry import CellMetrics, Rect

LIST_PANE_WIDTH = 55
"""Columns 1..55: the file list and its hint rows."""

PREVIEW_LEFT = 60
"""The preview starts at column 60, leaving a four-column gutter after the list."""

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
        """Split a terminal of ``size`` into list pane, preview box and footer."""
        columns = max(0, size.columns)
        lines = max(0, size.lines)
        body_height = max(0, lines - FOOTER_HEIGHT)

        # The last column the preview may occupy, so the width follows from the
        # left edge rather than from a second independently-maintained constant.
        preview_right = columns - RIGHT_MARGIN

        return cls(
            list_pane=Rect(
                left=1,
                top=1,
                width=min(LIST_PANE_WIDTH, columns),
                height=body_height,
            ),
            preview_box=Rect(
                left=PREVIEW_LEFT,
                top=1,
                width=max(0, preview_right - PREVIEW_LEFT + 1),
                height=body_height,
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
        """Whether the preview box is too small to be worth drawing into.

        Under 20 columns or 10 rows a photograph is a handful of unreadable
        cells, so the screen shows a short message instead.
        """
        return (
            self.preview_box.width < MIN_PREVIEW_WIDTH
            or self.preview_box.height < MIN_PREVIEW_HEIGHT
        )

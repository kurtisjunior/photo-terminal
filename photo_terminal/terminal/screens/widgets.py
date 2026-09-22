"""Reusable screen widgets, and the text helpers they are drawn with.

Bounded list navigation was written three times, character for character, and
none of the three copies had a scroll window - a folder with more images than
the window is tall simply painted past the bottom of the terminal. The
37-image screenshot in the bug report paints all 37 rows on every frame.

``ListView`` owns both halves: where the cursor is, and which slice of the list
is on screen. The window follows the cursor with a margin, so the selection is
never pinned against the top or bottom edge while there is more list to see.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

#: SGR colour codes, which occupy no cells. Pre-compiled: this is a hot path.
_ANSI_ESCAPE_RE = re.compile(r"\033\[[0-9;]*m")

SGR_RESET = "\033[0m"

DEFAULT_MARGIN = 2
"""Rows kept between the cursor and the edge of the window while scrolling.

Two rows of context in the direction of travel is enough to see what is coming
without the list jumping a screenful at a time.
"""


@dataclass
class ListView[T]:
    """A cursor over a list, plus the window of it that is on screen.

    The window is *sticky*: it only moves when the cursor would otherwise come
    within :attr:`margin` rows of an edge, so arrowing up and down inside the
    visible rows does not scroll the list under the user.
    """

    items: Sequence[T]
    cursor: int = 0
    margin: int = DEFAULT_MARGIN
    offset: int = field(default=0)
    """First visible index. Maintained by :meth:`window`; read it afterwards."""

    def __post_init__(self) -> None:
        self.cursor = self._clamped(self.cursor)

    # -- the list --------------------------------------------------------- #

    def __len__(self) -> int:
        return len(self.items)

    @property
    def is_empty(self) -> bool:
        return not self.items

    @property
    def current(self) -> T:
        """The item under the cursor.

        Raises:
            IndexError: if the list is empty.
        """
        if self.is_empty:
            raise IndexError("ListView is empty")
        return self.items[self.cursor]

    def sync(self, items: Sequence[T], cursor: int | None = None) -> None:
        """Adopt a new list, keeping the cursor in range.

        Used by screens whose list is owned elsewhere - the reorder screen's
        order lives in the domain, and the S3 browser's list is whatever the
        last listing returned.
        """
        self.items = items
        if cursor is not None:
            self.cursor = cursor
        self.cursor = self._clamped(self.cursor)

    # -- the cursor ------------------------------------------------------- #

    def move(self, delta: int) -> bool:
        """Move the cursor by ``delta``, bounded, without wrapping.

        Returns:
            Whether the cursor actually moved. No-wrap matches every screen's
            behaviour today: arrowing up at the top stays at the top.
        """
        target = self._clamped(self.cursor + delta)
        if target == self.cursor:
            return False
        self.cursor = target
        return True

    def move_up(self) -> bool:
        return self.move(-1)

    def move_down(self) -> bool:
        return self.move(1)

    def _clamped(self, index: int) -> int:
        if self.is_empty:
            return 0
        return max(0, min(index, len(self.items) - 1))

    # -- the window ------------------------------------------------------- #

    def window(self, height: int) -> tuple[int, int]:
        """The half-open range of indices visible in a window ``height`` tall.

        Scrolls just far enough to keep the cursor at least :attr:`margin` rows
        from the edge it is moving toward, and never past either end of the
        list. The margin shrinks on a window too short to honour it, so a
        two-row window still tracks the cursor.
        """
        count = len(self.items)
        if height <= 0 or count == 0:
            self.offset = 0
            return (0, 0)
        if count <= height:
            self.offset = 0
            return (0, count)

        margin = min(self.margin, (height - 1) // 2)
        offset = min(self.offset, self.cursor - margin)
        offset = max(offset, self.cursor + margin - height + 1)
        self.offset = max(0, min(offset, count - height))
        return (self.offset, self.offset + height)

    def visible(self, height: int) -> Sequence[T]:
        """The items inside :meth:`window`."""
        start, stop = self.window(height)
        return self.items[start:stop]

    def rows(self, height: int) -> list[tuple[int, T]]:
        """The visible items paired with their index in the full list.

        Screens need the absolute index to decide what is selected, grabbed or
        highlighted, so handing back bare items would only make every caller
        recompute it.
        """
        start, stop = self.window(height)
        return [(index, self.items[index]) for index in range(start, stop)]

    def has_above(self, height: int) -> bool:
        """Whether any item sits above the window."""
        return self.window(height)[0] > 0

    def has_below(self, height: int) -> bool:
        """Whether any item sits below the window."""
        return self.window(height)[1] < len(self.items)


# --------------------------------------------------------------------------- #
# Text helpers
# --------------------------------------------------------------------------- #


def visible_len(text: str) -> int:
    """How many cells ``text`` occupies, ignoring its colour escapes."""
    return len(_ANSI_ESCAPE_RE.sub("", text))


def pad_line(text: str, width: int) -> str:
    """``text`` padded *or clipped* to exactly ``width`` visible cells.

    Padding rather than ``\033[K`` is what keeps a pane inside its columns:
    erase-to-end-of-line would take the preview with it. Clipping is the other
    half of the same guarantee - a hint row longer than a narrow pane would
    otherwise paint into the gutter and across the preview.

    Colour escapes cost no cells and are copied through; a clipped line is
    closed with a reset so its colour cannot bleed into the pane beside it.
    """
    out: list[str] = []
    used = 0
    styled = False
    index = 0
    while index < len(text):
        match = _ANSI_ESCAPE_RE.match(text, index)
        if match:
            out.append(match.group())
            styled = True
            index = match.end()
            continue
        if used >= width:
            break
        out.append(text[index])
        used += 1
        index += 1
    if styled:
        out.append(SGR_RESET)
    out.append(" " * max(0, width - used))
    return "".join(out)


def ellipsise(text: str, width: int) -> str:
    """``text`` cut to ``width`` visible characters, ending in an ellipsis."""
    if width <= 0:
        return ""
    if len(text) <= width:
        return text
    if width <= 3:
        return text[:width]
    return text[: width - 3] + "..."


def rule(label: str, width: int, style: str = "", indent: str = "") -> str:
    """A horizontal rule ``width`` cells wide with ``label`` centred in it."""
    width = max(0, width - len(indent))
    label = label[:width]
    padding = width - len(label)
    left = padding // 2
    reset = "\033[0m" if style else ""
    return f"{indent}{style}{'─' * left}{label}{'─' * (padding - left)}{reset}"


def widest_that_fits(variants: Sequence[str], width: int) -> str:
    """The first of ``variants`` that fits in ``width`` cells, else the last.

    Hint rows are written longest-first, so a wide pane gets the full text and
    a narrow one gets an abbreviation rather than a sentence cut in half.
    """
    for variant in variants:
        if visible_len(variant) <= width:
            return variant
    return variants[-1] if variants else ""

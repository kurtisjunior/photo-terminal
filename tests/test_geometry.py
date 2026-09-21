"""Geometry: cell measurement, the fit matrix, and the layout split.

These are the assertions the old code could not have made, because the same
numbers were recomputed at six call sites with two different clamp policies. The
size half of the 2026-09-21 bug lives or dies here.
"""

from __future__ import annotations

import os

import pytest

from photo_terminal.terminal.geometry import (
    ASSUMED_CELL_PX,
    CellMetrics,
    Point,
    Rect,
    Size,
    fit,
)
from photo_terminal.terminal.layout import (
    LIST_PANE_WIDTH,
    MIN_PREVIEW_HEIGHT,
    MIN_PREVIEW_WIDTH,
    PREVIEW_LEFT,
    RIGHT_MARGIN,
    Layout,
)

# The terminal shapes the preview has to be correct at, from the smallest
# standard window to a large one.
TERMINAL_SIZES = [(80, 24), (100, 30), (120, 40), (178, 58), (200, 60), (240, 80)]

# Measured cells from real terminals, plus the 1:2 fallback.
CELLS = [
    CellMetrics(px=Size(8, 16), measured=True),
    CellMetrics(px=Size(9, 19), measured=True),
    CellMetrics(px=Size(14, 30), measured=True),
    CellMetrics.assumed(),
]

SOURCES = {
    "portrait": Size(3000, 4000),
    "landscape": Size(4000, 3000),
    "square": Size(2000, 2000),
}


def preview_box(columns: int, lines: int, cell: CellMetrics) -> Size:
    return Layout.for_terminal(os.terminal_size((columns, lines)), cell).preview_box.size


class TestCellMetrics:
    def test_a_non_terminal_fd_falls_back_to_a_two_to_one_cell(self, tmp_path):
        """A pipe or a file cannot answer TIOCGWINSZ."""
        path = tmp_path / "not-a-terminal"
        path.write_text("")
        with path.open() as handle:
            cell = CellMetrics.probe(handle.fileno())

        assert cell.measured is False
        assert cell.px == Size(*ASSUMED_CELL_PX)
        assert cell.aspect == 2.0

    def test_a_closed_fd_falls_back_rather_than_raising(self):
        cell = CellMetrics.probe(-1)
        assert cell.measured is False

    def test_the_assumed_cell_is_exactly_two_to_one(self):
        """The half-block renderer stacks two pixels per row, so this ratio is
        not a guess about the font - it is the renderer's own geometry."""
        assert CellMetrics.assumed().aspect == 2.0


class TestFit:
    @pytest.mark.parametrize("cell", CELLS, ids=lambda c: f"{c.px.w}x{c.px.h}")
    @pytest.mark.parametrize("size", TERMINAL_SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
    @pytest.mark.parametrize("source", SOURCES.values(), ids=list(SOURCES))
    def test_the_requested_rectangle_matches_the_source_aspect(self, source, size, cell):
        """The drawn rectangle has the source's aspect ratio, to within one cell.

        We must not rely on the terminal to letterbox: Ghostty computes
        ``cell_width * columns`` by ``cell_height * rows`` and stretches to fill
        when both ``c`` and ``r`` are set. Aspect ratio is ours to get right.

        The assertion is on pixels, because pixels are what is displayed. The
        tolerance is one cell's worth of quantisation in each axis - landing on
        whole cells is what makes the terminal's scaling a no-op, and it is the
        only source of aspect error left.
        """
        box = preview_box(*size, cell)
        placement = fit(source, box, cell)

        displayed = placement.px.w / placement.px.h
        wanted = source.w / source.h
        tolerance = wanted * (cell.px.w / placement.px.w + cell.px.h / placement.px.h)

        assert abs(displayed - wanted) <= tolerance

    @pytest.mark.parametrize("cell", CELLS, ids=lambda c: f"{c.px.w}x{c.px.h}")
    @pytest.mark.parametrize("size", TERMINAL_SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
    @pytest.mark.parametrize("source", SOURCES.values(), ids=list(SOURCES))
    def test_the_placement_never_leaves_the_box(self, source, size, cell):
        box = preview_box(*size, cell)
        placement = fit(source, box, cell)

        assert placement.cells.w <= box.w
        assert placement.cells.h <= box.h

    @pytest.mark.parametrize("cell", CELLS, ids=lambda c: f"{c.px.w}x{c.px.h}")
    @pytest.mark.parametrize("size", TERMINAL_SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
    @pytest.mark.parametrize("source", SOURCES.values(), ids=list(SOURCES))
    def test_the_pixel_size_is_exactly_the_cell_rectangle(self, source, size, cell):
        """This is what makes the terminal's own scaling the identity transform."""
        box = preview_box(*size, cell)
        placement = fit(source, box, cell)

        assert placement.px.w == placement.cells.w * cell.px.w
        assert placement.px.h == placement.cells.h * cell.px.h

    @pytest.mark.parametrize("cell", CELLS, ids=lambda c: f"{c.px.w}x{c.px.h}")
    @pytest.mark.parametrize("size", TERMINAL_SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
    def test_a_tiny_source_is_never_upscaled(self, size, cell):
        """A 40x30 source is smaller than any preview box at any terminal size.

        The old path passed both ``-w`` and ``-h`` to an external viewer, which
        skipped its own downscale-only guard and blew a 40x30 PNG up to 116x56
        cells. The drawn rectangle here never exceeds the source's own 40x30
        pixels; cell quantisation means it may be a little under, which is the
        cost of landing on whole cells and is bounded by one cell per axis.
        """
        source = Size(40, 30)
        placement = fit(source, preview_box(*size, cell), cell)

        assert placement.px.w <= source.w
        assert placement.px.h <= source.h

    def test_a_source_at_exactly_the_box_size_fills_it(self):
        cell = CellMetrics(px=Size(8, 16), measured=True)
        box = Size(10, 5)
        placement = fit(Size(80, 80), box, cell)

        assert placement.cells == box
        assert placement.px == Size(80, 80)

    def test_the_placement_is_at_least_one_cell(self):
        """Flooring must not produce a zero-cell rectangle for a wide sliver."""
        cell = CellMetrics(px=Size(8, 16), measured=True)
        placement = fit(Size(400, 4), Size(30, 10), cell)

        assert placement.cells.h >= 1
        assert placement.cells.w >= 1

    @pytest.mark.parametrize(
        ("source", "box"),
        [
            (Size(0, 100), Size(30, 10)),
            (Size(100, 0), Size(30, 10)),
            (Size(100, 100), Size(0, 10)),
            (Size(100, 100), Size(30, 0)),
        ],
    )
    def test_a_degenerate_input_yields_an_empty_placement(self, source, box):
        placement = fit(source, box, CellMetrics.assumed())
        assert placement.is_empty


class TestLayout:
    @pytest.mark.parametrize("size", TERMINAL_SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
    def test_the_panes_never_overlap(self, size, measured_cell):
        layout = Layout.for_terminal(os.terminal_size(size), measured_cell)
        assert not (layout.list_pane.cells & layout.preview_box.cells)

    @pytest.mark.parametrize("size", TERMINAL_SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
    def test_nothing_reaches_the_window_edges(self, size, measured_cell):
        columns, lines = size
        layout = Layout.for_terminal(os.terminal_size(size), measured_cell)

        assert layout.preview_box.left == PREVIEW_LEFT
        assert layout.preview_box.left + layout.preview_box.width - 1 == columns - RIGHT_MARGIN
        assert layout.preview_box.top + layout.preview_box.height - 1 == lines - 2
        assert layout.list_pane.width <= LIST_PANE_WIDTH

    def test_the_footer_sits_below_both_panes(self, measured_cell):
        layout = Layout.for_terminal(os.terminal_size((178, 58)), measured_cell)

        assert layout.footer.top == layout.list_pane.top + layout.list_pane.height
        assert layout.footer.top == layout.preview_box.top + layout.preview_box.height
        assert layout.footer.height == 2

    @pytest.mark.parametrize("size", [(100, 30), (178, 58), (240, 80)])
    def test_a_usable_window_is_not_suppressed(self, size, measured_cell):
        layout = Layout.for_terminal(os.terminal_size(size), measured_cell)
        assert layout.preview_suppressed is False

    @pytest.mark.parametrize("size", [(60, 20), (70, 24), (80, 24), (100, 8), (20, 10)])
    def test_a_cramped_window_suppresses_the_preview(self, size, measured_cell):
        """Below this a photograph is a handful of unreadable cells, so the
        screen shows a message instead.

        An 80-column window is in this set: a 55-column list pane leaves 19
        columns, one short of the threshold. That is a consequence of the fixed
        list width, and it is a message rather than a sliver of a photograph.
        """
        layout = Layout.for_terminal(os.terminal_size(size), measured_cell)
        assert layout.preview_suppressed is True

    def test_suppression_thresholds_are_the_declared_ones(self, measured_cell):
        columns = PREVIEW_LEFT + RIGHT_MARGIN + MIN_PREVIEW_WIDTH - 1
        lines = MIN_PREVIEW_HEIGHT + 2
        layout = Layout.for_terminal(os.terminal_size((columns, lines)), measured_cell)

        assert layout.preview_box.size == Size(MIN_PREVIEW_WIDTH, MIN_PREVIEW_HEIGHT)
        assert layout.preview_suppressed is False

    def test_a_tiny_window_yields_empty_rather_than_negative_rects(self, measured_cell):
        layout = Layout.for_terminal(os.terminal_size((10, 2)), measured_cell)

        assert layout.preview_box.is_empty
        assert layout.list_pane.is_empty
        assert layout.preview_box.width >= 0
        assert layout.list_pane.height >= 0


class TestRect:
    def test_cells_enumerates_the_inclusive_origin_rectangle(self):
        rect = Rect(left=2, top=3, width=2, height=2)
        assert rect.cells == {Point(2, 3), Point(3, 3), Point(2, 4), Point(3, 4)}

    def test_or_unions_two_rects_into_a_cell_set(self):
        left = Rect(left=1, top=1, width=1, height=1)
        right = Rect(left=5, top=1, width=1, height=1)
        assert left | right == {Point(1, 1), Point(5, 1)}

    def test_an_empty_rect_has_no_cells(self):
        assert Rect(left=1, top=1, width=0, height=5).cells == frozenset()

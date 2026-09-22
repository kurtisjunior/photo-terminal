"""The reorder screen - the first coverage it has ever had.

It used to be a second, drifted copy of the select screen's machinery: its own
executor, its own cache, its own pipe, its own geometry constants, half-blocks
on every terminal and no scroll window. It is now the same code, so these tests
assert the two things that are genuinely its own - grab-and-drop, and the
prefixed filenames it returns - plus the render invariants it inherits.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest

from photo_terminal.terminal.geometry import CellMetrics
from photo_terminal.terminal.layout import Layout
from photo_terminal.terminal.screens.reorder import (
    ReorderImageSelector,
    reorder_images_interactive,
)
from tests.conftest import MEASURED_CELL, FakeTerminal

GHOSTTY_ENV = {"TERM": "xterm-ghostty", "TERM_PROGRAM": "ghostty"}

ENTER = "\r"
SPACE = " "
DOWN = ["\x1b", "[", "B"]
UP = ["\x1b", "[", "A"]


@contextmanager
def screen_on(
    images: list[Path],
    fake_term: FakeTerminal,
    environment: dict[str, str] | None = None,
    cell: CellMetrics = MEASURED_CELL,
) -> Iterator[ReorderImageSelector]:
    """A reorder screen whose every byte lands in ``fake_term``."""
    with (
        patch.dict(os.environ, GHOSTTY_ENV if environment is None else environment, clear=True),
        patch(
            "photo_terminal.terminal.screens.reorder.sample_terminal_size",
            return_value=fake_term.size,
        ),
        patch("photo_terminal.terminal.screens.reorder.probe_cell_metrics", return_value=cell),
        patch("sys.stdout", fake_term.as_stdout()),
    ):
        screen = ReorderImageSelector(images)
        try:
            yield screen
        finally:
            screen._pane.close()


def render_until_ready(screen: ReorderImageSelector, timeout: float = 5.0) -> None:
    """Render until the background render has landed, as a keypress settles."""
    deadline = time.monotonic() + timeout
    while True:
        if screen._pane.dirty:
            screen._pane.drain()
        screen.render()
        if screen._pane.token is not None and screen._pane.token[-1] == "ready":
            return
        if time.monotonic() > deadline:
            raise AssertionError("no preview was produced within the timeout")
        time.sleep(0.005)


class TestConstruction:
    def test_an_empty_list_is_refused(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            ReorderImageSelector([])

    def test_the_view_starts_on_the_first_image(self, sample_images, fake_term):
        with screen_on(sample_images, fake_term) as screen:
            assert screen._view.cursor == 0
            assert list(screen._view.items) == sample_images


class TestKeys:
    def test_enter_returns_prefixed_filenames_in_order(self, sample_images, scripted_keys):
        screen = ReorderImageSelector(sample_images)
        scripted_keys([ENTER])
        with patch.object(screen, "render"):
            result = screen.run()

        assert result == [
            (sample_images[0], f"1_{sample_images[0].name}"),
            (sample_images[1], f"2_{sample_images[1].name}"),
            (sample_images[2], f"3_{sample_images[2].name}"),
        ]

    def test_grab_and_move_reorders_the_upload(self, sample_images, scripted_keys):
        screen = ReorderImageSelector(sample_images)
        # grab the first image, move it down one, drop it, confirm
        scripted_keys([SPACE, *DOWN, SPACE, ENTER])
        with patch.object(screen, "render"):
            result = screen.run()

        assert [path for path, _ in result] == [
            sample_images[1],
            sample_images[0],
            sample_images[2],
        ]
        assert [name for _, name in result] == [
            f"1_{sample_images[1].name}",
            f"2_{sample_images[0].name}",
            f"3_{sample_images[2].name}",
        ]

    def test_j_and_k_move_the_cursor(self, sample_images, scripted_keys):
        screen = ReorderImageSelector(sample_images)
        scripted_keys(["j", "j", "k", "q"])
        with patch.object(screen, "render"):
            assert screen.run() is None
        assert screen.reorderer.get_current_index() == 1

    def test_r_resets_the_order(self, sample_images, scripted_keys):
        screen = ReorderImageSelector(sample_images)
        scripted_keys([SPACE, *DOWN, "r", ENTER])
        with patch.object(screen, "render"):
            result = screen.run()

        assert [path for path, _ in result] == sample_images

    def test_q_cancels(self, sample_images, scripted_keys):
        screen = ReorderImageSelector(sample_images)
        scripted_keys(["q"])
        with patch.object(screen, "render"):
            assert screen.run() is None

    def test_a_bare_escape_cancels(self, sample_images, scripted_keys):
        screen = ReorderImageSelector(sample_images)
        scripted_keys(["\x1b", "z"])
        with patch.object(screen, "render"):
            assert screen.run() is None

    def test_ctrl_c_propagates(self, sample_images, scripted_keys):
        """It used to be swallowed here and reported as a cancel."""
        screen = ReorderImageSelector(sample_images)
        scripted_keys(["\x03"])
        with patch.object(screen, "render"), pytest.raises(KeyboardInterrupt):
            screen.run()

    def test_the_preview_service_is_closed_on_the_way_out(self, sample_images, scripted_keys):
        screen = ReorderImageSelector(sample_images)
        scripted_keys(["q"])
        with patch.object(screen, "render"):
            screen.run()
        assert screen._preview._worker.closed is True


class TestRendering:
    def test_nothing_is_written_outside_the_panes(self, sample_images, fake_term):
        with screen_on(sample_images, fake_term) as screen:
            screen.render()
            screen.reorderer.move_down()
            screen.render()

        layout = Layout.for_terminal(fake_term.size, MEASURED_CELL)
        assert fake_term.cells_touched() <= layout.preview_box | layout.list_pane

    def test_the_preview_is_a_native_placement_on_ghostty(self, sample_images, fake_term):
        """It painted half-blocks on every terminal until this phase."""
        with screen_on(sample_images, fake_term) as screen:
            render_until_ready(screen)

        transmit = next(cmd for cmd in fake_term.kitty_commands() if cmd.get("a") == "T")
        assert transmit["C"] == "1"
        assert transmit["q"] == "2"

    def test_a_long_list_is_windowed_rather_than_overflowing(self, tmp_path, fake_term):
        images = []
        for index in range(60):
            path = tmp_path / f"image{index:02}.jpg"
            path.write_bytes(b"")
            images.append(path)

        fake_term = FakeTerminal(size=os.terminal_size((178, 30)), cell_px=MEASURED_CELL.px)
        with screen_on(images, fake_term) as screen:
            screen.render()

        layout = Layout.for_terminal(fake_term.size, MEASURED_CELL)
        assert fake_term.cells_touched() <= layout.preview_box | layout.list_pane
        rows = max(row for _, row in fake_term.cells_touched())
        assert rows <= layout.list_pane.height

    def test_the_cursor_stays_in_view_as_it_moves_down_a_long_list(self, tmp_path, fake_term):
        images = [tmp_path / f"image{index:02}.jpg" for index in range(60)]
        for path in images:
            path.write_bytes(b"")

        with screen_on(images, fake_term) as screen:
            for _ in range(40):
                screen.reorderer.move_down()
            screen.render()

            start, stop = screen._view.window(10)
            assert start <= screen._view.cursor < stop


class TestEntryPoint:
    def test_an_empty_list_returns_none_without_opening_a_screen(self):
        assert reorder_images_interactive([]) is None

    def test_it_runs_the_screen(self, sample_images, scripted_keys):
        scripted_keys([ENTER])
        with patch.object(ReorderImageSelector, "render"):
            result = reorder_images_interactive(sample_images)

        assert result is not None
        assert [path for path, _ in result] == sample_images

"""The invariants that would have caught the 2026-09-21 Ghostty preview bug.

These four tests started life as ``xfail(strict=True)`` reproductions against the
old render path and pass against the new one. They drive the real
:class:`~photo_terminal.terminal.screens.select.ImageSelector` against real image
fixtures and assert
on the bytes it actually writes.

The bug, for the record. The preview was produced by shelling out to an external
terminal image viewer with its stdout on a pipe. That viewer expects to own the
terminal: over a pipe it could not complete its Kitty capability handshake, so it
silently fell back to half-block text and terminated every row with ``\\r\\n``.
The render path wrote one cursor anchor, ``\\033[1;60H``, and then replayed the
captured blob uninspected. The ``\\r`` returned the cursor to column 1, so only
row 1 landed in the preview column and rows 2 onward painted straight across the
file list - the top strip and the bottom-left fragment in the screenshot. The
blob also carried the viewer's capability probe, which the terminal genuinely
answered on the raw-mode stdin the input loop was polling.

Four properties close all of that off:

1. the preview payload contains no carriage return,
2. no write lands outside the list pane or the preview box,
3. the requested rectangle matches the source's aspect ratio, because Ghostty
   stretches rather than letterboxes when both ``c`` and ``r`` are set,
4. navigating away deletes the outgoing placement, because text erasure does not
   touch graphics.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from photo_terminal.terminal.geometry import CellMetrics, Size
from photo_terminal.terminal.layout import Layout
from photo_terminal.terminal.preview.frames import KittyFrame
from photo_terminal.terminal.screens.preview_pane import TOO_SMALL_MESSAGE
from photo_terminal.terminal.screens.select import ImageSelector

from .conftest import MEASURED_CELL, FakeTerminal

# Ghostty's advertised identity. Both predicates in detect_graphics_protocol
# fire on this, so the selector takes the Kitty path for real.
GHOSTTY_ENV = {"TERM": "xterm-ghostty", "TERM_PROGRAM": "ghostty"}
PLAIN_ENV = {"TERM": "xterm-256color"}


@contextmanager
def selector_on(
    images: list[Path],
    fake_term: FakeTerminal,
    environment: dict[str, str],
    cell: CellMetrics = MEASURED_CELL,
) -> Iterator[ImageSelector]:
    """An ``ImageSelector`` whose every byte lands in ``fake_term``."""
    with (
        patch.dict(os.environ, environment, clear=True),
        patch(
            "photo_terminal.terminal.screens.select.sample_terminal_size",
            return_value=fake_term.size,
        ),
        patch("photo_terminal.terminal.screens.select.probe_cell_metrics", return_value=cell),
        patch("sys.stdout", fake_term.as_stdout()),
    ):
        selector = ImageSelector(images)
        try:
            yield selector
        finally:
            selector._pane.close()


SETTLED = ("ready", "too-small")


def render_until_ready(selector: ImageSelector, timeout: float = 5.0) -> None:
    """Render until the preview has settled on something other than a placeholder.

    This is what a user sees after one keypress settles: a placeholder frame,
    then the photograph when the background render lands. A cache hit settles on
    the first render, and a window too small for a preview settles on its
    message.
    """
    deadline = time.monotonic() + timeout
    while True:
        if selector._pane.dirty:
            selector._pane.drain()
        selector.render()

        token = selector._pane.token
        if token is not None and token[-1] in SETTLED:
            return
        if time.monotonic() > deadline:
            raise AssertionError("no preview was produced within the timeout")
        time.sleep(0.005)


def layout_for(fake_term: FakeTerminal) -> Layout:
    return Layout.for_terminal(fake_term.size, MEASURED_CELL)


@pytest.mark.parametrize("environment", [GHOSTTY_ENV, PLAIN_ENV], ids=["ghostty", "plain"])
def test_preview_payload_never_contains_a_carriage_return(
    sample_images: list[Path],
    fake_term: FakeTerminal,
    environment: dict[str, str],
) -> None:
    """A ``\\r`` anywhere in the payload walks the preview onto the file list."""
    with selector_on(sample_images, fake_term, environment) as selector:
        render_until_ready(selector)

    payload = fake_term.preview_payload()
    assert payload, "the preview anchor was never written"
    assert b"\r" not in payload


@pytest.mark.parametrize("environment", [GHOSTTY_ENV, PLAIN_ENV], ids=["ghostty", "plain"])
@pytest.mark.parametrize("size", [(80, 24), (100, 30), (178, 58), (240, 80)])
def test_no_write_lands_outside_the_list_pane_or_preview_box(
    sample_images: list[Path],
    environment: dict[str, str],
    size: tuple[int, int],
) -> None:
    fake_term = FakeTerminal(size=os.terminal_size(size), cell_px=MEASURED_CELL.px)

    with selector_on(sample_images, fake_term, environment) as selector:
        render_until_ready(selector)
        selector.move_down()
        render_until_ready(selector)

    layout = layout_for(fake_term)
    assert fake_term.cells_touched() <= layout.preview_box | layout.list_pane


@pytest.mark.parametrize("fixture", ["portrait_3x4", "landscape_4x3"])
def test_kitty_placement_is_bounded_and_quiet(
    request: pytest.FixtureRequest,
    fake_term: FakeTerminal,
    fixture: str,
) -> None:
    source: Path = request.getfixturevalue(fixture)

    with selector_on([source], fake_term, GHOSTTY_ENV) as selector:
        render_until_ready(selector)
        placement = selector._pane.painted

    assert isinstance(placement, KittyFrame)

    transmit = next(cmd for cmd in fake_term.kitty_commands() if cmd.get("a") == "T")
    assert transmit["C"] == "1"  # the placement must not move the cursor
    assert transmit["q"] == "2"  # no replies into our raw-mode stdin
    assert transmit["i"] == str(placement.image_id)

    box = layout_for(fake_term).preview_box
    assert int(transmit["c"]) <= box.width
    assert int(transmit["r"]) <= box.height


@pytest.mark.parametrize("fixture", ["portrait_3x4", "landscape_4x3"])
@pytest.mark.parametrize("size", [(100, 30), (178, 58), (240, 80)])
def test_requested_rectangle_matches_the_source_aspect(
    request: pytest.FixtureRequest,
    fixture: str,
    size: tuple[int, int],
) -> None:
    """We must not rely on the terminal to letterbox - Ghostty does not."""
    source: Path = request.getfixturevalue(fixture)
    with Image.open(source) as image:
        source_px = Size(image.width, image.height)

    fake_term = FakeTerminal(size=os.terminal_size(size), cell_px=MEASURED_CELL.px)
    with selector_on([source], fake_term, GHOSTTY_ENV) as selector:
        render_until_ready(selector)
        placement = selector._pane.painted

    assert isinstance(placement, KittyFrame)

    # Assert on pixels: that is what the terminal displays, and the PNG has been
    # resized to exactly the placement rectangle.
    displayed = (placement.cells.w * MEASURED_CELL.px.w) / (placement.cells.h * MEASURED_CELL.px.h)
    wanted = source_px.w / source_px.h
    tolerance = wanted * (
        1 / placement.cells.w + 1 / placement.cells.h
    )  # one cell of quantisation per axis

    assert abs(displayed - wanted) <= tolerance


def test_navigation_deletes_the_outgoing_placement(
    sample_images: list[Path],
    fake_term: FakeTerminal,
) -> None:
    """``\\033[2J`` clears images, but no other text erasure touches them, so an
    explicit ``a=d`` is the only thing that can remove the previous preview."""
    with selector_on(sample_images, fake_term, GHOSTTY_ENV) as selector:
        render_until_ready(selector)
        outgoing = selector._pane.painted
        assert isinstance(outgoing, KittyFrame)

        selector.move_down()
        render_until_ready(selector)
        incoming = selector._pane.painted
        assert isinstance(incoming, KittyFrame)

    commands = fake_term.kitty_commands()
    deletions = [cmd for cmd in commands if cmd.get("a") == "d"]

    assert {"a": "d", "d": "i", "i": str(outgoing.image_id), "q": "2"} in deletions
    # The pixels are kept, so returning to the previous image is a re-placement
    # rather than a re-transmission.
    assert not any(cmd.get("d") == "I" for cmd in deletions)

    transmits = [cmd for cmd in commands if cmd.get("a") == "T"]
    assert [cmd["i"] for cmd in transmits] == [
        str(outgoing.image_id),
        str(incoming.image_id),
    ]


def test_returning_to_a_cached_image_re_places_rather_than_re_transmits(
    sample_images: list[Path],
    fake_term: FakeTerminal,
) -> None:
    with selector_on(sample_images, fake_term, GHOSTTY_ENV) as selector:
        render_until_ready(selector)
        first = selector._pane.painted
        assert isinstance(first, KittyFrame)

        selector.move_down()
        render_until_ready(selector)
        selector.move_up()
        render_until_ready(selector)

    commands = fake_term.kitty_commands()
    assert {
        "a": "p",
        "i": str(first.image_id),
        "c": str(first.cells.w),
        "r": str(first.cells.h),
        "C": "1",
        "q": "2",
    } in commands
    assert [cmd["i"] for cmd in commands if cmd.get("a") == "T"].count(str(first.image_id)) == 1


def test_a_cramped_window_shows_a_message_instead_of_a_sliver(
    sample_images: list[Path],
) -> None:
    """A window too narrow for two panes gives its columns to the list, and
    says why in the footer rather than painting a sliver of a photograph."""
    fake_term = FakeTerminal(size=os.terminal_size((60, 20)), cell_px=MEASURED_CELL.px)

    with selector_on(sample_images, fake_term, GHOSTTY_ENV) as selector:
        selector.render()

    assert fake_term.kitty_commands() == []
    assert TOO_SMALL_MESSAGE.encode() in fake_term.bytes_written

    layout = layout_for(fake_term)
    assert layout.preview_suppressed
    assert fake_term.cells_touched() <= layout.list_pane | layout.footer

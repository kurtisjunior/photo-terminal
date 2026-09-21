"""A failing reproduction of the 2026-09-21 Ghostty preview bug.

Both tests here are ``xfail(strict=True)`` against the current graphics path and
are expected to pass once phase 2 emits the Kitty graphics protocol directly.
``xfail_strict`` in ``pyproject.toml`` means an accidental pass is a failure, so
these cannot quietly stop testing anything.

The reproduction drives the *real* ``ImageSelector.render_with_graphics_protocol``
with a recorded ``viu`` block-fallback capture standing in for the subprocess.
That pins the defect mechanism deterministically on a machine with no ``viu``
installed: the bytes are the ones viu 1.6.1 actually produced with its stdout on
a pipe, so nothing about the failure is simulated except the process boundary.

Mechanism, for the record. With stdout on a pipe viu cannot complete its Kitty
capability handshake, so it selects its block printer and terminates every row
with ``\\r\\n``. The graphics path writes one cursor anchor, ``\\033[1;60H``, and
then replays the blob uninspected. The ``\\r`` returns the cursor to column 1, so
only row 1 lands in the preview column and rows 2 onward paint across the file
list and the gutter between the panes.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from photo_terminal.tui import ImageSelector

from .conftest import ExpectedLayout, FakeTerminal

# Ghostty's advertised identity. Both predicates in detect_graphics_protocol
# fire on this, so the selector takes the graphics path for real.
GHOSTTY_ENV = {"TERM": "xterm-ghostty", "TERM_PROGRAM": "ghostty"}


def _drive_graphics_path(
    images: list[Path],
    fake_term: FakeTerminal,
    viu_capture: bytes,
) -> None:
    """Render the current graphics path twice, recording every byte.

    The first render schedules the preview and paints a placeholder; the second
    paints the cached bytes. Both frames land in ``fake_term``, which is what a
    user sees after one arrow keypress settles.
    """
    viu_result = Mock(returncode=0, stdout=viu_capture, stderr=b"")

    with (
        patch.dict(os.environ, GHOSTTY_ENV, clear=True),
        patch("photo_terminal.tui.os.get_terminal_size", return_value=fake_term.size),
        patch("photo_terminal.tui.subprocess.run", return_value=viu_result),
        patch("sys.stdout", fake_term.as_stdout()),
    ):
        selector = ImageSelector(images)
        assert selector._protocol == "kitty", "Ghostty must take the graphics path"
        try:
            selector.render_with_preview()
            _wait_for_preview(selector)
            selector.render_with_preview()
        finally:
            selector._preview_executor.shutdown(wait=True)
            os.close(selector._notify_r)
            os.close(selector._notify_w)


def _wait_for_preview(selector: ImageSelector, timeout: float = 5.0) -> None:
    """Block until a background render has landed in the cache."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if selector._preview_dirty and selector._image_cache:
            return
        time.sleep(0.005)
    raise AssertionError("no preview was produced within the timeout")


@pytest.mark.xfail(
    strict=True,
    reason="2026-09-21: viu's block fallback ends every row with \\r, which resets "
    "the cursor to column 1 and walks the preview across the file list",
)
def test_preview_payload_never_contains_a_carriage_return(
    sample_images: list[Path],
    fake_term: FakeTerminal,
    viu_block_capture: bytes,
) -> None:
    _drive_graphics_path(sample_images, fake_term, viu_block_capture)

    payload = fake_term.preview_payload()
    assert payload, "the preview anchor was never written"
    assert b"\r" not in payload


@pytest.mark.xfail(
    strict=True,
    reason="2026-09-21: the graphics path has no size clamp and no per-row "
    "anchoring, so the preview escapes its box",
)
def test_no_write_lands_outside_the_list_pane_or_preview_box(
    sample_images: list[Path],
    fake_term: FakeTerminal,
    viu_block_capture: bytes,
) -> None:
    _drive_graphics_path(sample_images, fake_term, viu_block_capture)

    layout = ExpectedLayout.for_terminal(fake_term.size)
    assert fake_term.cells_touched() <= layout.preview_box | layout.list_pane

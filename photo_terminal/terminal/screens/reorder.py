"""Stage 2: put the selected images in upload order.

The same two-pane screen as the select stage, with grab-and-drop instead of
checkboxes. It is the same code now: one layout, one preview pane, one list
view, one session. Before this it was a second copy of the machinery that had
drifted - its own executor, its own cache, its own pipe, its own geometry
constants, half-blocks on every terminal, and no scroll window.

The ordering itself stays in the domain, in
:class:`~photo_terminal.domain.reorder.ImageReorderer`: moving a *grabbed* item swaps
it with its neighbour, which is a rule about the order rather than about the
screen. The screen reads the cursor back from it each frame.
"""

from __future__ import annotations

import logging
from pathlib import Path

from photo_terminal.domain.reorder import (
    ImageReorderer,
    generate_prefixed_filenames,
    get_final_filenames_preview,
)
from photo_terminal.terminal.capabilities import detect_graphics_protocol
from photo_terminal.terminal.frame import CLEAR_AND_HOME, HOME, Frame
from photo_terminal.terminal.input import (
    KEY_DOWN,
    KEY_ESC,
    KEY_UP,
    read_key_with_timeout_or_signal,
)
from photo_terminal.terminal.layout import Layout, probe_cell_metrics, sample_terminal_size
from photo_terminal.terminal.preview.service import PreviewService
from photo_terminal.terminal.screens.preview_pane import STARTUP_PRELOAD, PreviewPane
from photo_terminal.terminal.screens.widgets import (
    ListView,
    ellipsise,
    pad_line,
    rule,
    widest_that_fits,
)
from photo_terminal.terminal.session import TerminalSession

logger = logging.getLogger(__name__)

#: The title rule and a blank.
HEADER_HEIGHT = 2
#: A blank, the position rule, the two upload-order lines, a blank, two hints.
FOOTER_HEIGHT = 7

#: Hint rows longest-first; a narrow pane takes the first one that fits.
_MOVE_HINTS = (
    "SPACE: grab/drop  ↑/↓ or j/k: move  r: reset",
    "SPACE: grab  j/k: move  r: reset",
    "SPACE: grab  r: reset",
)
_CONFIRM_HINTS = (
    "ENTER: confirm  q/Esc: cancel",
    "ENTER: confirm  q: cancel",
)


class ReorderImageSelector:
    """Image reorderer with the same two-pane TUI as the select stage."""

    def __init__(self, images: list[Path]):
        """Initialize reorder selector.

        Args:
            images: List of image paths to reorder

        Raises:
            ValueError: If the list is empty.
        """
        if not images:
            raise ValueError("Images list cannot be empty")

        self.reorderer = ImageReorderer(images)
        self._view: ListView[Path] = ListView(self.reorderer.get_ordered_images())
        self._first_render = True

        self._protocol = detect_graphics_protocol()
        self._cell = probe_cell_metrics()
        self._terminal_size = sample_terminal_size()
        self._preview = PreviewService(self._protocol, self._cell)
        self._pane = PreviewPane(self._preview)

    # -- the file list ---------------------------------------------------- #

    def _sync_view(self) -> None:
        """Adopt the domain's current order and cursor."""
        self._view.sync(self.reorderer.get_ordered_images(), self.reorderer.get_current_index())

    def _build_file_list_lines(self, width: int, height: int) -> list[str]:
        rows_height = max(1, height - HEADER_HEIGHT - FOOTER_HEIGHT)
        rows = self._view.rows(rows_height)
        start, stop = self._view.window(rows_height)

        lines = [rule(f" Reorder Images ({len(self._view)} selected) ", width, "\033[34m"), ""]
        lines += [self._row_line(index, path, width) for index, path in rows]
        lines += [""] * (rows_height - len(rows))
        lines += self._footer_lines(width, start, stop)
        return lines[:height] if height > 0 else []

    def _row_line(self, index: int, path: Path, width: int) -> str:
        grabbed = self.reorderer.get_grabbed_index()
        position = f"{index + 1}."
        # The number column is as wide as the largest position, so the names
        # line up in a folder of any size.
        digits = len(str(len(self._view)))
        name = ellipsise(path.name, width - digits - 7)

        if index == grabbed:
            return f" \033[1;32m✱ {position:>{digits + 1}} {name}\033[0m"
        if index == self._view.cursor:
            return f" \033[1;33m→ {position:>{digits + 1}} {name}\033[0m"
        return f"   {position:>{digits + 1}} {name}"

    def _footer_lines(self, width: int, start: int, stop: int) -> list[str]:
        total = len(self._view)
        position = f" {start + 1}-{stop} of {total} " if stop - start < total else ""
        order = ellipsise(get_final_filenames_preview(list(self._view.items)), width - 2)
        return [
            "",
            rule(position, max(0, width - 1), "\033[2m", indent=" "),
            " \033[2mFinal upload order:\033[0m",
            f" \033[36m{order}\033[0m",
            "",
            f" \033[2m{widest_that_fits(_MOVE_HINTS, width - 1)}\033[0m",
            f" \033[2m{widest_that_fits(_CONFIRM_HINTS, width - 1)}\033[0m",
        ]

    # -- rendering -------------------------------------------------------- #

    def render(self) -> None:
        """Paint one frame: the order on the left, the highlighted image right."""
        self._sync_view()
        self._terminal_size = sample_terminal_size()
        layout = Layout.for_terminal(self._terminal_size, self._cell)

        frame = Frame()
        if self._first_render:
            frame.write(CLEAR_AND_HOME)
            self._first_render = False
        else:
            frame.write(HOME)

        pane = layout.list_pane
        if not pane.is_empty:
            lines = self._build_file_list_lines(pane.width, pane.height)
            frame.place_lines(pane.origin, [pad_line(line, pane.width) for line in lines])

        self._pane.paint(frame, layout.preview_box, self._view.current)
        self._pane.paint_notice(frame, layout.footer, layout.preview_suppressed)
        frame.write(self._pane.take_pending_writes())
        frame.flush()

        self._pane.preload(layout.preview_box, self._view.items, self._view.cursor)

    # -- the input loop --------------------------------------------------- #

    def run(self) -> list[tuple[Path, str]] | None:
        """Run the interactive reorder UI.

        Returns:
            List of (original_path, prefixed_filename) tuples if confirmed,
            None if cancelled

        Raises:
            KeyboardInterrupt: If the user presses Ctrl-C
        """
        logger.info("Starting reorder selector")
        try:
            with TerminalSession():
                return self._loop()
        finally:
            self._pane.close()

    def _loop(self) -> list[tuple[Path, str]] | None:
        layout = Layout.for_terminal(self._terminal_size, self._cell)
        self._pane.warm(layout.preview_box, self._view.items, STARTUP_PRELOAD)

        self.render()

        while True:
            key = read_key_with_timeout_or_signal(0.05, extra_fds=[self._pane.wait_fd])

            if key is None:
                if self._pane.dirty:
                    self._pane.drain()
                    self.render()
                continue

            if key == KEY_UP or key in ("k", "K"):
                self.reorderer.move_up()
            elif key == KEY_DOWN or key in ("j", "J"):
                self.reorderer.move_down()
            elif key == KEY_ESC:
                return None
            elif key == " ":  # grab / drop
                self.reorderer.toggle_grab()
            elif key in ("r", "R"):
                self.reorderer.reset()
            elif key in ("\r", "\n"):  # confirm
                return generate_prefixed_filenames(self.reorderer.get_ordered_images())
            elif key in ("q", "Q"):
                return None
            elif key == "\x03":  # Ctrl+C
                raise KeyboardInterrupt

            self.render()


def reorder_images_interactive(images: list[Path]) -> list[tuple[Path, str]] | None:
    """Interactive function to reorder images with visual preview.

    Args:
        images: List of image paths to reorder

    Returns:
        List of (original_path, prefixed_filename) tuples if confirmed,
        None if cancelled
    """
    if not images:
        return None

    return ReorderImageSelector(images).run()

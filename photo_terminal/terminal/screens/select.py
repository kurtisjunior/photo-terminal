"""Stage 1: pick the images to upload.

A two-pane screen - the file list on the left, a live preview of the highlighted
image on the right - with a multi-stage selection workflow:

1. Mark images with ``y``/``x``/Space (shows ``[x]``)
2. Lock the selection with Enter
3. Proceed with ``n``

Rendering has no per-mode branching in it. One :class:`Layout` says where
everything goes, :class:`ListView` says which rows are on screen,
:class:`PreviewService` produces a :class:`PreviewFrame`, and the screen paints
and erases frames without ever learning which kind it holds.
"""

from __future__ import annotations

import logging
from pathlib import Path

from photo_terminal.errors import NoImagesFound
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

#: Rows of chrome above the file list: the title rule and a blank.
HEADER_HEIGHT = 2
#: Rows of chrome below it: a blank, the position rule, the current filename,
#: a blank, and two hint lines.
FOOTER_HEIGHT = 6


class ImageSelector:
    """Interactive image selector with two-pane TUI."""

    def __init__(self, images: list[Path]):
        """Initialize image selector.

        Args:
            images: List of image paths to display
        """
        self._view: ListView[Path] = ListView(images)
        self.selected_indices: set[int] = set()  # Set of selected image indices
        self._first_render = True
        self._selections_locked = False  # Track if selections are locked
        self._locked_indices: set[int] = set()  # Store locked selection indices

        self._protocol = detect_graphics_protocol()
        self._cell = probe_cell_metrics()
        self._terminal_size = sample_terminal_size()
        self._preview = PreviewService(self._protocol, self._cell)
        self._pane = PreviewPane(self._preview)

    # -- state ------------------------------------------------------------ #

    @property
    def images(self) -> list[Path]:
        """The images on offer, in display order."""
        return list(self._view.items)

    @property
    def current_index(self) -> int:
        """Which image is highlighted."""
        return self._view.cursor

    @current_index.setter
    def current_index(self, index: int) -> None:
        self._view.sync(self._view.items, index)

    def toggle_selection(self) -> None:
        """Toggle selection state of current image."""
        if self.current_index in self.selected_indices:
            self.selected_indices.remove(self.current_index)
        else:
            self.selected_indices.add(self.current_index)

    def move_up(self) -> None:
        """Move selection cursor up."""
        self._view.move_up()

    def move_down(self) -> None:
        """Move selection cursor down."""
        self._view.move_down()

    def get_selected_images(self) -> list[Path]:
        """Get list of selected image paths.

        Returns:
            List of selected image paths in order
        """
        images = self._view.items
        return [images[i] for i in sorted(self.selected_indices)]

    # -- the file list ---------------------------------------------------- #

    def _build_file_list_lines(self, width: int, height: int) -> list[str]:
        """The file list, exactly ``height`` rows tall.

        The rows between the header and the hints are a window onto the list,
        not the whole of it: a folder with more images than the window is tall
        used to paint every one of them, straight past the bottom edge.
        """
        rows_height = max(1, height - HEADER_HEIGHT - FOOTER_HEIGHT)
        rows = self._view.rows(rows_height)
        start, stop = self._view.window(rows_height)

        lines = self._header_lines(width)
        lines += [self._row_line(index, path, width) for index, path in rows]
        lines += [""] * (rows_height - len(rows))
        lines += self._footer_lines(width, start, stop)
        return lines[:height] if height > 0 else []

    def _header_lines(self, width: int) -> list[str]:
        selected = len(self.selected_indices)
        total = len(self._view)
        return [rule(f" Images ({selected}/{total} selected) ", width, "\033[34m"), ""]

    def _row_line(self, index: int, path: Path, width: int) -> str:
        checkbox = "[x]" if index in self.selected_indices else "[ ]"
        name = ellipsise(path.name, width - 8)  # room for " [x] > " plus a margin
        if index == self._view.cursor:
            return f" \033[1;36m{checkbox} \033[1;36m► {name}\033[0m"
        return f" {checkbox}   {name}"

    def _footer_lines(self, width: int, start: int, stop: int) -> list[str]:
        total = len(self._view)
        if stop - start < total:
            position = f" {start + 1}-{stop} of {total} "
        else:
            position = ""
        current = ellipsise(self._view.current.name, width - 12) if total else ""

        lines = [
            "",
            rule(position, max(0, width - 1), "\033[2m", indent=" "),
            f" \033[36mCurrent: {current}\033[0m",
            "",
        ]
        for hint in self._hint_lines(width - 1):
            lines.append(f" \033[2m{hint}\033[0m")
        return lines

    def _hint_lines(self, width: int) -> tuple[str, str]:
        """The two hint rows, abbreviated to fit a narrow pane."""
        if self._selections_locked:
            return (
                "\033[1;32m✓ Selections locked\033[0m",
                widest_that_fits(
                    [
                        "n: Next Stage  Enter: Unlock  q/Esc: Cancel",
                        "n: Next  Enter: Unlock  q: Cancel",
                        "n: Next  q: Cancel",
                    ],
                    width,
                ),
            )
        return (
            widest_that_fits(
                [
                    "↑/↓ Nav  x/y/Space: Mark [x]  a: All  Enter: Lock",
                    "↑/↓ Nav  Space: Mark  a: All  Enter: Lock",
                    "↑/↓ Nav  Space: Mark  Enter: Lock",
                ],
                width,
            ),
            "q/Esc: Cancel",
        )

    # -- rendering -------------------------------------------------------- #

    def render(self) -> None:
        """Paint one frame: the file list, and the preview if it changed.

        One write, one flush, text and graphics in order. The preview is only
        rewritten when it actually changed, and the outgoing frame is always
        erased before the incoming one is painted.
        """
        self._terminal_size = sample_terminal_size()
        layout = Layout.for_terminal(self._terminal_size, self._cell)

        frame = Frame()
        if self._first_render:
            frame.write(CLEAR_AND_HOME)
            self._first_render = False
        else:
            frame.write(HOME)

        self._paint_file_list(frame, layout)
        self._pane.paint(frame, layout.preview_box, self._view.current)
        self._pane.paint_notice(frame, layout.footer, layout.preview_suppressed)

        # Anything the cache owes the terminal - today, freeing the pixels of an
        # evicted placement - rides along in this frame rather than in a write
        # of its own.
        frame.write(self._pane.take_pending_writes())
        frame.flush()

        self._pane.preload(layout.preview_box, self._view.items, self._view.cursor)

    def _paint_file_list(self, frame: Frame, layout: Layout) -> None:
        pane = layout.list_pane
        if pane.is_empty:
            return
        lines = self._build_file_list_lines(pane.width, pane.height)
        frame.place_lines(pane.origin, [pad_line(line, pane.width) for line in lines])

    # -- the input loop --------------------------------------------------- #

    def run(self) -> list[Path] | None:
        """Run the interactive selector.

        Returns:
            List of selected image paths, or None if cancelled

        Raises:
            KeyboardInterrupt: If the user presses Ctrl-C
        """
        logger.info("Starting TUI selector")

        try:
            with TerminalSession():
                return self._loop()
        finally:
            self._pane.close()

    def _loop(self) -> list[Path] | None:
        """The key loop, inside a terminal the session already owns."""
        # Warm the first screenful before the initial paint
        layout = Layout.for_terminal(self._terminal_size, self._cell)
        self._pane.warm(layout.preview_box, self._view.items, STARTUP_PRELOAD)

        # Initial render
        self.render()

        while True:
            # Read key with a short timeout; wakes immediately on preview completion
            key = read_key_with_timeout_or_signal(0.05, extra_fds=[self._pane.wait_fd])

            if key is None:
                if self._pane.dirty:
                    self._pane.drain()
                    self.render()
                continue

            # Handle navigation keys
            if key == KEY_UP:
                logger.debug("Up arrow pressed")
                self.move_up()
            elif key == KEY_DOWN:
                logger.debug("Down arrow pressed")
                self.move_down()
            elif key == KEY_ESC:
                logger.info("Escape pressed, exiting")
                return None

            # Handle other keys
            elif key == " ":  # Spacebar
                logger.debug("Space pressed")
                self.toggle_selection()
            elif key == "\r" or key == "\n":  # Enter
                logger.info("Enter pressed")
                if not self._selections_locked:
                    # Lock the selections
                    if not self.selected_indices:
                        # No images selected, continue
                        logger.warning("No images selected, cannot lock")
                        continue
                    self._selections_locked = True
                    self._locked_indices = self.selected_indices.copy()
                    logger.info(f"Selections locked: {len(self._locked_indices)} images")
                else:
                    # Unlock the selections
                    self._selections_locked = False
                    self._locked_indices = set()
                    logger.info("Selections unlocked")
                # Don't return - stay in the loop
            elif key in ("y", "Y", "x", "X"):
                # Just mark the image, don't proceed
                logger.info(f"'{key}' pressed - toggling selection")
                self.toggle_selection()
            elif key == "n" or key == "N":
                if not self._selections_locked:
                    logger.info("'n' pressed but selections not locked - ignoring")
                    continue
                logger.info("'n' pressed - proceeding to next stage")
                return self.get_selected_images()
            elif key == "a" or key == "A":
                # Toggle select all
                logger.info("'a' pressed - toggling select all")
                if len(self.selected_indices) == len(self._view):
                    # All selected, deselect all
                    self.selected_indices = set()
                    logger.info("Deselected all images")
                else:
                    # Some or none selected, select all
                    self.selected_indices = set(range(len(self._view)))
                    logger.info(f"Selected all {len(self._view)} images")
                # Don't return - let user confirm with Enter
            elif key == "q" or key == "Q":  # Quit
                logger.info("Q pressed, exiting")
                return None
            elif key == "\x03":  # Ctrl+C
                logger.info("Ctrl+C pressed")
                raise KeyboardInterrupt

            # Redraw with new preview
            self.render()


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def select_images(images: list[Path]) -> list[Path]:
    """Interactive image selection with TUI.

    Args:
        images: List of valid image paths from scanner

    Returns:
        The selected image paths, or an empty list if the user chose nothing.
        Cancelling is an answer, not a failure: the caller decides what it
        means and which exit code it earns.

    Raises:
        NoImagesFound: If there was nothing to select from.
        KeyboardInterrupt: If the user presses Ctrl-C. All three full-screen
            screens propagate it, and the caller handles it in one place.
    """
    logger.info(f"select_images called with {len(images)} images")

    if not images:
        logger.error("No images provided")
        raise NoImagesFound("No images provided for selection")

    logger.info("Creating ImageSelector")
    selector = ImageSelector(images)
    logger.info("ImageSelector created, calling run()")

    selected = selector.run()
    logger.info(f"Selector returned {len(selected) if selected else 0} images")

    if not selected:
        logger.info("User cancelled or no images selected")
        print("\nNo images selected")
        return []

    return selected

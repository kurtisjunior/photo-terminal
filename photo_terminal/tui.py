"""Two-pane TUI for interactive image selection with an inline image preview.

Provides a terminal interface with:
- File list (left pane) with checkboxes and navigation
- Live preview (right pane) showing the highlighted image, as a native Kitty
  graphics placement on Kitty/Ghostty/WezTerm and as ANSI half-blocks elsewhere
- Multi-stage selection workflow:
  1. Mark images with y/Space (shows [x])
  2. Lock selections with Enter (prevents accidental changes)
  3. Proceed to next stage with 'n'
- Keyboard controls: arrows to navigate, y/spacebar to mark, a to select all, enter to lock, n to proceed

Rendering has no per-mode branching left in it. One :class:`Layout` says where
everything goes, :class:`~photo_terminal.terminal.preview.service.PreviewService`
produces a :class:`~photo_terminal.terminal.preview.frames.PreviewFrame`, and the
screen paints and erases frames without ever learning which kind it holds.
"""

import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from photo_terminal.input_utils import (
    KEY_DOWN,
    KEY_ESC,
    KEY_UP,
    read_key_with_timeout_or_signal,
)
from photo_terminal.terminal.capabilities import detect_graphics_protocol
from photo_terminal.terminal.frame import (
    CLEAR_AND_HOME,
    HIDE_CURSOR,
    HOME,
    SHOW_CURSOR,
    Frame,
)
from photo_terminal.terminal.geometry import CellMetrics, Point
from photo_terminal.terminal.layout import Layout
from photo_terminal.terminal.preview.frames import MessageFrame, PreviewFrame
from photo_terminal.terminal.preview.service import PreviewService

# Pre-compiled regex for stripping ANSI escape codes (hot path optimisation)
_ANSI_ESCAPE_RE = re.compile(r"\033\[[0-9;]*m")

# Set up logging
logger = logging.getLogger(__name__)

FALLBACK_TERMINAL_SIZE = os.terminal_size((120, 40))

LOADING_MESSAGE = "[Loading preview...]"
TOO_SMALL_MESSAGE = "[Preview: window too small]"

# Which neighbours to warm after each render, in the order a user is most likely
# to need them.
PRELOAD_OFFSETS = (1, -1, 2, -2)
STARTUP_PRELOAD = 5


class ImageSelector:
    """Interactive image selector with two-pane TUI."""

    def __init__(self, images: list[Path]):
        """Initialize image selector.

        Args:
            images: List of image paths to display
        """
        self.images = images
        self.selected_indices: set[int] = set()  # Set of selected image indices
        self.current_index = 0  # Currently highlighted image
        self._first_render = True
        self._selections_locked = False  # Track if selections are locked
        self._locked_indices: set[int] = set()  # Store locked selection indices

        self._protocol = detect_graphics_protocol()
        self._cell = _probe_cell_metrics()
        self._terminal_size = _sample_terminal_size()
        self._preview = PreviewService(self._protocol, self._cell)

        # What is currently on screen, so it can be erased before the next
        # preview is painted. Text erasure does not remove a graphics
        # placement, so this is the only thing that can.
        self._painted: PreviewFrame | None = None
        self._painted_at: Point | None = None
        self._painted_token: tuple[object, ...] | None = None

    # -- state ------------------------------------------------------------ #

    def toggle_selection(self) -> None:
        """Toggle selection state of current image."""
        if self.current_index in self.selected_indices:
            self.selected_indices.remove(self.current_index)
        else:
            self.selected_indices.add(self.current_index)

    def move_up(self) -> None:
        """Move selection cursor up."""
        if self.current_index > 0:
            self.current_index -= 1

    def move_down(self) -> None:
        """Move selection cursor down."""
        if self.current_index < len(self.images) - 1:
            self.current_index += 1

    def get_selected_images(self) -> list[Path]:
        """Get list of selected image paths.

        Returns:
            List of selected image paths in order
        """
        return [self.images[i] for i in sorted(self.selected_indices)]

    # -- the file list ---------------------------------------------------- #

    @staticmethod
    def _visible_len(text: str) -> int:
        """Calculate visible length of text excluding ANSI escape codes."""
        return len(_ANSI_ESCAPE_RE.sub("", text))

    @classmethod
    def _pad_line(cls, text: str, width: int) -> str:
        """Pad text with spaces to a fixed visible width."""
        return text + " " * max(0, width - cls._visible_len(text))

    def _build_file_list_lines(self, width: int) -> list[str]:
        """Build file list display lines with direct ANSI formatting."""
        lines = []
        sel = len(self.selected_indices)
        total = len(self.images)
        header_text = f" Images ({sel}/{total} selected) "
        border_w = max(0, width - len(header_text) - 2)
        left_b = border_w // 2
        right_b = border_w - left_b
        lines.append(f"\033[34m{'─' * left_b}{header_text}{'─' * right_b}\033[0m")
        lines.append("")

        max_name = width - 8  # room for " [x] > " prefix
        for i, img in enumerate(self.images):
            checkbox = "[x]" if i in self.selected_indices else "[ ]"
            name = img.name
            if len(name) > max_name:
                name = name[: max_name - 3] + "..."
            if i == self.current_index:
                lines.append(f" \033[1;36m{checkbox} \033[1;36m► {name}\033[0m")
            else:
                lines.append(f" {checkbox}   {name}")

        lines.append("")
        lines.append(f" \033[2m{'─' * (width - 2)}\033[0m")
        cur_name = self.images[self.current_index].name
        if len(cur_name) > width - 12:
            cur_name = cur_name[: width - 15] + "..."
        lines.append(f" \033[36mCurrent: {cur_name}\033[0m")
        lines.append("")

        if self._selections_locked:
            lines.append(" \033[1;32m✓ Selections locked\033[0m")
            lines.append("")
            lines.append(" \033[2mn: Next Stage  Enter: Unlock  q/Esc: Cancel\033[0m")
        else:
            lines.append(" \033[2m↑/↓ Nav  x/y/Space: Mark [x]  a: All  Enter: Lock\033[0m")
            lines.append(" \033[2mq/Esc: Cancel\033[0m")

        lines.append("")
        return lines

    # -- rendering -------------------------------------------------------- #

    def render(self) -> None:
        """Paint one frame: the file list, and the preview if it changed.

        One write, one flush, text and graphics in order. The preview is only
        rewritten when it actually changed, and the outgoing frame is always
        erased before the incoming one is painted.
        """
        self._terminal_size = _sample_terminal_size()
        layout = Layout.for_terminal(self._terminal_size, self._cell)

        frame = Frame()
        if self._first_render:
            frame.write(CLEAR_AND_HOME)
            self._first_render = False
        else:
            frame.write(HOME)

        self._paint_file_list(frame, layout)
        self._paint_preview(frame, layout)

        # Anything the cache owes the terminal - today, freeing the pixels of an
        # evicted placement - rides along in this frame rather than in a write
        # of its own.
        frame.write(self._preview.take_pending_writes())
        frame.flush()

        self._trigger_preload(layout)

    def _paint_file_list(self, frame: Frame, layout: Layout) -> None:
        pane = layout.list_pane
        if pane.is_empty:
            return
        lines = self._build_file_list_lines(pane.width)
        # Clipped to the pane: a folder with more images than the window is tall
        # must not paint past the bottom. A scroll window follows in phase 4.
        visible = [self._pad_line(line, pane.width) for line in lines[: pane.height]]
        frame.place_lines(pane.origin, visible)

    def _paint_preview(self, frame: Frame, layout: Layout) -> None:
        box = layout.preview_box
        if box.is_empty:
            self._erase_painted(frame)
            return

        path = self.images[self.current_index]
        incoming, token = self._incoming_preview(path, layout)
        if token == self._painted_token:
            return

        self._erase_painted(frame)
        if incoming is not None:
            frame.write(incoming.paint(box.origin))
        self._painted = incoming
        self._painted_at = box.origin
        self._painted_token = token

    def _incoming_preview(
        self, path: Path, layout: Layout
    ) -> tuple[PreviewFrame | None, tuple[object, ...]]:
        """The frame to show for ``path``, and a token identifying it.

        The token is what the change detector compares. It has to distinguish a
        placeholder from the real image for the same path and box, because that
        transition is exactly when a repaint is required.
        """
        box = layout.preview_box.size
        if layout.preview_suppressed:
            message = MessageFrame(TOO_SMALL_MESSAGE, box.w)
            return message, (path, box, "too-small")

        frame = self._preview.frame_for(path, box)
        if frame is None:
            return MessageFrame(LOADING_MESSAGE, box.w), (path, box, "loading")
        return frame, (path, box, "ready")

    def _erase_painted(self, frame: Frame) -> None:
        if self._painted is None or self._painted_at is None:
            return
        frame.write(self._painted.erase(self._painted_at))
        self._painted = None
        self._painted_at = None
        self._painted_token = None

    def _trigger_preload(self, layout: Layout) -> None:
        """Warm the neighbours of the cursor in the background."""
        if layout.preview_suppressed or layout.preview_box.is_empty:
            return
        box = layout.preview_box.size
        for offset in PRELOAD_OFFSETS:
            target = self.current_index + offset
            if 0 <= target < len(self.images):
                self._preview.request(self.images[target], box)

    # -- the input loop --------------------------------------------------- #

    def run(self) -> list[Path] | None:
        """Run the interactive selector.

        Returns:
            List of selected image paths, or None if cancelled

        Raises:
            SystemExit: If user cancels (q/Escape)
        """
        # Import here to avoid issues if not in interactive terminal
        import termios
        import tty

        # Save terminal settings
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)

        logger.info("Starting TUI selector")

        try:
            # Set terminal to raw mode for key capture
            tty.setraw(fd)

            # Hide cursor
            sys.stdout.write(HIDE_CURSOR)
            sys.stdout.flush()

            # Warm the first screenful before the initial paint
            layout = Layout.for_terminal(self._terminal_size, self._cell)
            if not layout.preview_suppressed and not layout.preview_box.is_empty:
                for i in range(min(STARTUP_PRELOAD, len(self.images))):
                    self._preview.request(self.images[i], layout.preview_box.size)

            # Initial render
            self.render()

            while True:
                # Read key with a short timeout; wakes immediately on preview completion
                key = read_key_with_timeout_or_signal(0.05, extra_fds=[self._preview.wait_fd])

                if key is None:
                    if self._preview.dirty:
                        self._preview.drain()
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
                    if len(self.selected_indices) == len(self.images):
                        # All selected, deselect all
                        self.selected_indices = set()
                        logger.info("Deselected all images")
                    else:
                        # Some or none selected, select all
                        self.selected_indices = set(range(len(self.images)))
                        logger.info(f"Selected all {len(self.images)} images")
                    # Don't return - let user confirm with Enter
                elif key == "q" or key == "Q":  # Quit
                    logger.info("Q pressed, exiting")
                    return None
                elif key == "\x03":  # Ctrl+C
                    logger.info("Ctrl+C pressed")
                    raise KeyboardInterrupt

                # Redraw with new preview
                self.render()

        finally:
            # Restore terminal settings. The full clear is what removes any
            # graphics placement still on screen; the alternate screen buffer
            # replaces it in phase 3.
            sys.stdout.write(SHOW_CURSOR)
            sys.stdout.write(CLEAR_AND_HOME)
            sys.stdout.flush()
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            self._preview.close()


def _stdout_fd() -> int | None:
    """The descriptor we are painting to, or ``None`` when there isn't one.

    Both the cell measurement and the size sample have to ask the *same*
    descriptor, or they can disagree about which terminal they are describing.
    """
    try:
        fd = sys.stdout.fileno()
    except (OSError, AttributeError, ValueError):
        return None
    return fd if isinstance(fd, int) else None


def _sample_terminal_size() -> os.terminal_size:
    """The terminal's cell dimensions, with a fallback for a detached stdout."""
    fd = _stdout_fd()
    try:
        return os.get_terminal_size() if fd is None else os.get_terminal_size(fd)
    except OSError:
        return FALLBACK_TERMINAL_SIZE


def _probe_cell_metrics() -> CellMetrics:
    """Measure one cell in pixels, falling back to the 1:2 assumption."""
    fd = _stdout_fd()
    return CellMetrics.assumed() if fd is None else CellMetrics.probe(fd)


def show_processing_config(
    locked_images: list[Path], config: dict[str, Any]
) -> dict[str, Any] | None:
    """Show processing configuration screen for locked images.

    Args:
        locked_images: List of selected image paths
        config: Configuration dict from photo-uploader.yaml

    Returns:
        Processing configuration dict with user's choices
    """
    import termios
    import tty

    console = Console()

    # Available output formats
    AVAILABLE_FORMATS = ["JPEG", "PNG", "WEBP"]

    # Configuration options with defaults
    options: dict[str, Any] = {
        "resize": True,  # Apply size optimization
        "preserve_exif": True,  # Preserve EXIF data
        "output_format": "JPEG",  # Output format (cycles through AVAILABLE_FORMATS)
    }

    current_option = 0  # Currently highlighted option
    option_keys = list(options.keys())

    # Save terminal settings
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    def render_config_screen():
        """Render the configuration screen."""
        console.clear()

        # Header
        header = Text()
        header.append("Processing Configuration\n", style="bold cyan")
        header.append(
            f"Configure processing for {len(locked_images)} locked image(s)\n", style="dim"
        )
        console.print(Panel(header, border_style="cyan"))
        console.print()

        # Create options table
        table = Table(show_header=True, box=None, padding=(0, 2))
        table.add_column("", width=3)
        table.add_column("Option", style="bold")
        table.add_column("Description")
        table.add_column("Value", justify="right")

        # Resize option
        resize_checkbox = "[x]" if options["resize"] else "[ ]"
        if current_option == 0:
            table.add_row(
                Text("►", style="bold cyan"),
                Text("Resize images", style="bold cyan"),
                Text(f"Optimize to ~{config.get('target_size_kb', 400)}KB", style="cyan"),
                Text(resize_checkbox, style="bold cyan"),
            )
        else:
            table.add_row(
                Text(""),
                Text("Resize images"),
                Text(f"Optimize to ~{config.get('target_size_kb', 400)}KB"),
                Text(resize_checkbox),
            )

        # EXIF preservation option
        exif_checkbox = "[x]" if options["preserve_exif"] else "[ ]"
        if current_option == 1:
            table.add_row(
                Text("►", style="bold cyan"),
                Text("Preserve EXIF data", style="bold cyan"),
                Text("Keep camera, date, GPS info", style="cyan"),
                Text(exif_checkbox, style="bold cyan"),
            )
        else:
            table.add_row(
                Text(""),
                Text("Preserve EXIF data"),
                Text("Keep camera, date, GPS info"),
                Text(exif_checkbox),
            )

        # Output format option
        format_value = options["output_format"]
        format_desc = {
            "JPEG": "Lossy compression, smallest size",
            "PNG": "Lossless, larger size",
            "WEBP": "Modern, balanced size/quality",
        }.get(format_value, "")

        if current_option == 2:
            table.add_row(
                Text("►", style="bold cyan"),
                Text("Output format", style="bold cyan"),
                Text(format_desc, style="cyan"),
                Text(format_value, style="bold cyan"),
            )
        else:
            table.add_row(Text(""), Text("Output format"), Text(format_desc), Text(format_value))

        # Display table in panel
        console.print(Panel(table, title="Processing Options", border_style="blue"))
        console.print()

        # Controls
        controls = Text()
        controls.append("↑/↓: Navigate  ", style="dim")
        controls.append("Space: Toggle/Cycle  ", style="dim")
        controls.append("y: Confirm  ", style="dim")
        controls.append("b: Go Back  ", style="dim")
        controls.append("q/Esc: Cancel", style="dim")
        console.print(controls)

    try:
        # Set terminal to raw mode
        tty.setraw(fd)

        # Hide cursor
        sys.stdout.write(HIDE_CURSOR)
        sys.stdout.flush()

        # Initial render
        render_config_screen()

        while True:
            # Read a single character
            char = sys.stdin.read(1)

            # Handle escape sequences (arrow keys)
            if char == "\x1b":  # ESC
                next_char = sys.stdin.read(1)
                if next_char == "[":
                    arrow = sys.stdin.read(1)
                    if arrow == "A":  # Up arrow
                        current_option = max(0, current_option - 1)
                    elif arrow == "B":  # Down arrow
                        current_option = min(len(option_keys) - 1, current_option + 1)
                else:
                    # Escape key pressed (without arrow)
                    return None

            # Handle other keys
            elif char == " ":  # Spacebar - toggle/cycle current option
                option_key = option_keys[current_option]
                if option_key == "output_format":
                    # Cycle through available formats
                    current_format = options["output_format"]
                    current_index = AVAILABLE_FORMATS.index(current_format)
                    next_index = (current_index + 1) % len(AVAILABLE_FORMATS)
                    options["output_format"] = AVAILABLE_FORMATS[next_index]
                else:
                    # Toggle boolean option
                    options[option_key] = not options[option_key]

            elif char == "y" or char == "Y":  # Y - confirm
                # Build result dictionary
                result = {
                    "resize": options["resize"],
                    "target_size_kb": config.get("target_size_kb", 400),
                    "preserve_exif": options["preserve_exif"],
                    "output_format": options["output_format"],
                }
                return result

            elif char == "b" or char == "B":  # Go back
                return None

            elif char == "q" or char == "Q":  # Quit
                return None

            elif char == "\x03":  # Ctrl+C
                raise KeyboardInterrupt

            # Redraw screen
            render_config_screen()

    finally:
        # Restore terminal settings
        sys.stdout.write(SHOW_CURSOR)
        sys.stdout.flush()
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def select_images(images: list[Path]) -> list[Path]:
    """Interactive image selection with TUI.

    Args:
        images: List of valid image paths from scanner

    Returns:
        List of selected image paths

    Raises:
        SystemExit: If user cancels
    """
    logger.info(f"select_images called with {len(images)} images")

    # Validate input
    if not images:
        logger.error("No images provided")
        print("Error: No images provided for selection")
        raise SystemExit(1)

    # Run interactive selector
    logger.info("Creating ImageSelector")
    selector = ImageSelector(images)
    logger.info("ImageSelector created, calling run()")

    try:
        selected = selector.run()
        logger.info(f"Selector returned {len(selected) if selected else 0} images")

        if selected is None or not selected:
            logger.info("User cancelled or no images selected")
            print("\nNo images selected")
            raise SystemExit(1)

        return selected

    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt caught")
        print("\nCancelled by user")
        raise SystemExit(1) from None

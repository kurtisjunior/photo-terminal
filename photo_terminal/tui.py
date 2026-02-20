"""Two-pane TUI for interactive image selection with viu preview.

Provides a terminal interface with:
- File list (left pane) with checkboxes and navigation
- Live viu preview (right pane) showing selected image
- Multi-stage selection workflow:
  1. Mark images with y/Space (shows [x])
  2. Lock selections with Enter (prevents accidental changes)
  3. Proceed to next stage with 'n'
- Keyboard controls: arrows to navigate, y/spacebar to mark, a to select all, enter to lock, n to proceed
"""

import logging
import os
import re
import shutil
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Optional

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from photo_terminal.input_utils import KEY_DOWN, KEY_ESC, KEY_UP, read_key_with_timeout, read_key_with_timeout_or_signal
from photo_terminal.renderer import render_image_to_ansi

# Pre-compiled regex for stripping ANSI escape codes (hot path optimisation)
_ANSI_ESCAPE_RE = re.compile(r'\033\[[0-9;]*m')

# Set up logging
logger = logging.getLogger(__name__)


class TerminalCapabilities:
    """Detect and manage terminal graphics capabilities.

    This class provides methods to detect which graphics protocol (if any) the
    current terminal supports for inline image rendering. Detection is automatic and
    heuristic-based, and may produce false positives on older terminal versions.

    Supported terminals:
    - iTerm2 (iTerm2 inline image protocol)
    - Ghostty (Kitty graphics protocol)
    - Kitty (Kitty graphics protocol)
    - Sixel-capable terminals (Sixel protocol)
    - All other terminals (Unicode block fallback)

    Important notes:
    - Detection is automatic based on environment variables
    - Older versions of terminals may be detected as supporting protocols they don't
    - Terminal multiplexers (tmux, screen) force block mode as fallback
    """

    @staticmethod
    def detect_graphics_protocol() -> str:
        """Detect which graphics protocol is supported by the terminal.

        Automatic detection order:
        1. Check for terminal multiplexers (tmux/screen) - forces 'blocks' if detected
        2. Check TERM_PROGRAM for iTerm2 - returns 'iterm' if detected
        3. Check TERM_PROGRAM for Ghostty or 'ghostty' in TERM - returns 'kitty' if detected
        4. Check TERM for Kitty - returns 'kitty' if detected
        5. Check TERM for Sixel - returns 'sixel' if detected
        6. Fallback to 'blocks' for universal compatibility

        Note: These are heuristic checks based on environment variables. They may
        false-positive on older terminal versions that set these variables but don't
        fully support the graphics protocols. Ghostty supports the Kitty graphics
        protocol, so it returns 'kitty' when detected.

        Terminal multiplexers (tmux, screen) typically don't support graphics protocols,
        so they force block mode as a fallback.

        Returns:
            str: One of 'iterm', 'kitty', 'sixel', or 'blocks'
        """
        # Check for terminal multiplexers first
        # TMUX is set when inside tmux, STY is set when inside GNU screen
        # They typically break graphics protocols
        if os.environ.get('TMUX') or os.environ.get('STY'):
            return 'blocks'

        # Proceed with protocol detection
        term_program = os.environ.get('TERM_PROGRAM', '')
        term = os.environ.get('TERM', '')

        # iTerm2 detection (heuristic, may false-positive on older versions)
        if term_program == 'iTerm.app':
            return 'iterm'

        # Ghostty detection (uses Kitty graphics protocol)
        if term_program == 'ghostty' or 'ghostty' in term:
            return 'kitty'

        # Kitty detection (heuristic)
        if 'kitty' in term or term == 'xterm-kitty':
            return 'kitty'

        # Sixel detection (heuristic; TERM doesn't guarantee sixel support)
        if 'sixel' in term:
            return 'sixel'

        # Fallback to blocks for universal compatibility
        return 'blocks'

    @staticmethod
    def supports_inline_images() -> bool:
        """Check if terminal supports any inline image protocol.

        Returns:
            bool: True if terminal supports iTerm2, Kitty, or Sixel protocols,
                  False if only block-mode rendering is available
        """
        protocol = TerminalCapabilities.detect_graphics_protocol()
        return protocol in ('iterm', 'kitty', 'sixel')


def check_viu_availability() -> bool:
    """Check if viu is available on the system.

    Returns:
        True if viu is found, False otherwise
    """
    return shutil.which("viu") is not None


def fail_viu_not_found() -> None:
    """Print error message about viu not being installed and exit.

    Raises:
        SystemExit: Always exits with code 1
    """
    print("Error: viu is not installed")
    print()
    print("viu is required for image preview in the terminal.")
    print()
    print("Installation instructions:")
    print("  macOS:   brew install viu")
    print("  Linux:   cargo install viu  (or use your package manager)")
    print()
    print("More info: https://github.com/atanunq/viu")
    raise SystemExit(1)


def get_viu_preview(image_path: Path, width: int, height: int = None) -> str:
    """Generate viu preview output for an image.

    Args:
        image_path: Path to image file
        width: Width in characters for preview
        height: Maximum height in lines (optional, will be cropped if exceeded)

    Returns:
        String containing viu output with ANSI escape codes
    """
    logger.debug(f"get_viu_preview: {image_path.name}, width={width}, height={height}")
    try:
        # Run viu with appropriate flags
        # -b: force block output (ANSI colors instead of graphics protocols)
        # -w: width in terminal columns (viu will calculate height for aspect ratio)
        # Don't use -h to let viu maintain proper aspect ratio, crop afterwards if needed
        logger.debug("Running viu subprocess...")
        result = subprocess.run(
            ["viu", "-b", "-w", str(width), str(image_path)],
            capture_output=True,
            text=True,
            timeout=5
        )
        logger.debug(f"viu completed with returncode={result.returncode}")

        if result.returncode == 0:
            output = result.stdout
            logger.debug(f"viu output: {len(output)} chars, {len(output.splitlines())} lines")
            # Crop to max height if specified
            if height:
                lines = output.splitlines()
                if len(lines) > height:
                    output = "\n".join(lines[:height])
                    logger.debug(f"Cropped to {height} lines")
            return output
        else:
            logger.error(f"viu failed: {result.stderr}")
            return f"[Error rendering preview]\n{result.stderr}"

    except subprocess.TimeoutExpired:
        logger.error("viu timed out")
        return "[Preview timed out]"
    except Exception as e:
        logger.error(f"viu exception: {e}", exc_info=True)
        return f"[Preview error: {e}]"


class ImageSelector:
    """Interactive image selector with two-pane TUI."""

    def __init__(self, images: List[Path]):
        """Initialize image selector.

        Args:
            images: List of image paths to display
        """
        self.images = images
        self.selected_indices = set()  # Set of selected image indices
        self.current_index = 0  # Currently highlighted image
        self.console = Console(color_system="truecolor", force_terminal=True)
        self._first_render = True  # Track first render for graphics protocol mode
        self._image_cache = {}  # Cache for rendered image output: {image_path: output}
        self._selections_locked = False  # Track if selections are locked
        self._locked_indices = set()  # Store locked selection indices
        self._preview_executor = ThreadPoolExecutor(max_workers=4)
        self._preview_futures = {}
        self._preview_lock = threading.Lock()
        self._preview_dirty = False
        self._last_preview_key = None
        self._last_preview_cached = False  # Whether last preview render was from cache
        self._notify_r, self._notify_w = os.pipe()
        os.set_blocking(self._notify_r, False)
        self._protocol = TerminalCapabilities.detect_graphics_protocol()
        try:
            self._terminal_size = os.get_terminal_size()
        except OSError:
            self._terminal_size = os.terminal_size((120, 40))

    def _schedule_preview(self, cache_key: str, image_path: Path, width: int, height: int, mode: str) -> None:
        """Schedule preview rendering if not already cached or in flight."""
        if cache_key in self._image_cache:
            return
        with self._preview_lock:
            if cache_key in self._preview_futures:
                return
            future = self._preview_executor.submit(
                self._render_preview_output,
                image_path,
                width,
                height,
                mode
            )
            self._preview_futures[cache_key] = future
        future.add_done_callback(lambda f, key=cache_key: self._store_preview_result(key, f))

    def _store_preview_result(self, cache_key: str, future) -> None:
        """Store preview render result and mark UI dirty."""
        try:
            output = future.result()
        except Exception as e:
            if cache_key.startswith("graphics:"):
                output = f"[Preview error: {e}]".encode('utf-8', errors='replace')
            else:
                output = [f"[Preview error: {e}]"]
        with self._preview_lock:
            self._preview_futures.pop(cache_key, None)
            if output is not None:
                if cache_key.startswith("graphics:") and isinstance(output, list):
                    output = "\n".join(output).encode('utf-8', errors='replace')
                if cache_key.startswith("blocks:") and isinstance(output, bytes):
                    output = output.decode('utf-8', errors='replace').splitlines()
                self._image_cache[cache_key] = output
            self._preview_dirty = True
            try:
                os.write(self._notify_w, b'\x00')
            except OSError:
                pass

    def _render_preview_output(self, image_path: Path, width: int, height: int, mode: str):
        """Render preview output via viu (blocks or graphics)."""
        if mode == "graphics":
            result = subprocess.run(
                ["viu", "-w", str(width), "-h", str(height), str(image_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5
            )
            if result.returncode == 0:
                return result.stdout
            error_msg = result.stderr.decode('utf-8', errors='replace').strip()
            return f"[Preview error: {error_msg}]".encode('utf-8', errors='replace')

        # Block mode: use in-process Pillow renderer (no subprocess overhead)
        return render_image_to_ansi(image_path, width, height)

    @staticmethod
    def _loading_lines(width: int, height: int) -> List[str]:
        """Create a placeholder preview to avoid blocking on render."""
        if height <= 0:
            return ["[Loading preview...]"]
        lines = [" " * width for _ in range(height)]
        lines[0] = "[Loading preview...]"
        return lines

    @staticmethod
    def _visible_len(text: str) -> int:
        """Calculate visible length of text excluding ANSI escape codes."""
        return len(_ANSI_ESCAPE_RE.sub('', text))

    @staticmethod
    def _pad_line(text: str, width: int) -> str:
        """Pad text with spaces to a fixed visible width."""
        visible = len(_ANSI_ESCAPE_RE.sub('', text))
        return text + ' ' * max(0, width - visible)

    def _build_file_list_lines(self, width: int) -> List[str]:
        """Build file list display lines with direct ANSI formatting.

        Much faster than Rich Panel/Table/Console capture cycle.
        """
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
                name = name[:max_name - 3] + "..."
            if i == self.current_index:
                lines.append(f" \033[1;36m{checkbox} \033[1;36m► {name}\033[0m")
            else:
                lines.append(f" {checkbox}   {name}")

        lines.append("")
        lines.append(f" \033[2m{'─' * (width - 2)}\033[0m")
        cur_name = self.images[self.current_index].name
        if len(cur_name) > width - 12:
            cur_name = cur_name[:width - 15] + "..."
        lines.append(f" \033[36mCurrent: {cur_name}\033[0m")
        lines.append("")

        if self._selections_locked:
            lines.append(f" \033[1;32m✓ Selections locked\033[0m")
            lines.append("")
            lines.append(f" \033[2mn: Next Stage  Enter: Unlock  q/Esc: Cancel\033[0m")
        else:
            lines.append(f" \033[2m↑/↓ Nav  x/y/Space: Mark [x]  a: All  Enter: Lock\033[0m")
            lines.append(f" \033[2mq/Esc: Cancel\033[0m")

        lines.append("")
        return lines

    def _preload_image(self, index: int) -> None:
        """Pre-load image at index into cache in background.

        Args:
            index: Index of image to pre-load
        """
        if index < 0 or index >= len(self.images):
            return  # Out of bounds

        image_path = self.images[index]
        protocol = self._protocol
        terminal_size = self._terminal_size

        if protocol in ('iterm', 'kitty', 'ghostty', 'sixel'):
            # Graphics protocol dimensions
            terminal_width = terminal_size.columns
            terminal_height = terminal_size.lines
            image_column = 60
            image_width = terminal_width - image_column - 2
            image_height = terminal_height - 2

            cache_key = f"graphics:{image_path}:{image_width}:{image_height}"
            self._schedule_preview(cache_key, image_path, image_width, image_height, "graphics")
        else:
            # Block mode dimensions
            file_list_width = 55
            image_column = file_list_width + 5
            image_width = max(20, min(terminal_size.columns - image_column - 2, 60))
            image_height = max(10, min(terminal_size.lines - 5, 35))

            cache_key = f"blocks:{image_path}:{image_width}:{image_height}"
            self._schedule_preview(cache_key, image_path, image_width, image_height, "blocks")

    def _trigger_preload(self) -> None:
        """Pre-load adjacent images in background."""
        idx = self.current_index
        for offset in (1, -1, 2, -2):
            target = idx + offset
            if 0 <= target < len(self.images):
                self._preload_image(target)

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

    def get_selected_images(self) -> List[Path]:
        """Get list of selected image paths.

        Returns:
            List of selected image paths in order
        """
        selected_indices = sorted(self.selected_indices)
        return [self.images[i] for i in selected_indices]

    def create_file_list_panel(self) -> Panel:
        """Create the file list panel with checkboxes.

        Returns:
            Panel containing the file list
        """
        logger.debug(f"create_file_list_panel: {len(self.images)} images, current={self.current_index}")

        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("checkbox", width=3)
        table.add_column("filename", overflow="ellipsis")

        for i, img in enumerate(self.images):
            # Checkbox indicator
            if i in self.selected_indices:
                checkbox = "[x]"
            else:
                checkbox = "[ ]"

            # Filename with highlight for current selection
            filename = img.name

            # Style based on current index
            if i == self.current_index:
                checkbox_text = Text(checkbox, style="bold cyan")
                filename_text = Text(f"► {filename}", style="bold cyan")
            else:
                checkbox_text = Text(checkbox)
                filename_text = Text(f"  {filename}")

            table.add_row(checkbox_text, filename_text)

        # Add current image info
        current_image = self.images[self.current_index]
        info_text = Text()
        info_text.append("\n" + "─" * 40 + "\n", style="dim")
        info_text.append(f"Current: {current_image.name}\n\n", style="cyan")

        # Show lock status if selections are locked
        if self._selections_locked:
            info_text.append("✓ Selections locked - Press 'n' for next stage\n", style="bold green")

        # Add controls footer
        controls_text = Text()
        if self._selections_locked:
            controls_text.append("n: Next Stage  Enter: Unlock  q/Esc: Cancel", style="dim")
        else:
            controls_text.append("↑/↓ Nav  x/y/Space: Mark [x]  a: All  Enter: Lock\n", style="dim")
            controls_text.append("q/Esc: Cancel", style="dim")

        title = f"Images ({len(self.selected_indices)}/{len(self.images)} selected)"
        logger.debug(f"Panel created with title: {title}")
        return Panel(Group(table, info_text, controls_text), title=title, border_style="blue")

    def create_layout(self) -> Panel:
        """Create the file list panel (no preview due to Rich limitations).

        Returns:
            Panel with file list
        """
        logger.debug("create_layout called")
        panel = self.create_file_list_panel()
        logger.debug(f"Layout created: {type(panel)}")
        return panel

    def render_with_blocks(self, full_render: bool = True):
        """Render the TUI using block mode (Unicode blocks with ANSI colors).

        Uses direct ANSI line building for the file list (no Rich overhead)
        and skips preview rewrite when the image hasn't changed.

        Double-buffered: all output is collected into a list and written
        in a single sys.stdout.write() call to eliminate visual tearing.
        """
        parts = []

        # Anti-flicker: only clear screen on first render
        if self._first_render:
            parts.append('\033[2J\033[H')
            self._first_render = False
        else:
            parts.append('\033[H')

        current_image = self.images[self.current_index]
        self._terminal_size = os.get_terminal_size()
        terminal_size = self._terminal_size
        file_list_column = 1
        file_list_width = 55
        image_column = file_list_width + 5
        image_width = max(20, min(terminal_size.columns - image_column - 2, 60))
        image_height = max(10, min(terminal_size.lines - 5, 35))

        # Determine if preview needs updating
        cache_key = f"blocks:{current_image}:{image_width}:{image_height}"
        cache_hit = cache_key in self._image_cache
        preview_changed = (cache_key != self._last_preview_key) or (cache_hit and not self._last_preview_cached)

        if preview_changed:
            self._last_preview_key = cache_key
            self._last_preview_cached = cache_hit
            if cache_hit:
                viu_lines = self._image_cache[cache_key]
            elif check_viu_availability():
                self._schedule_preview(cache_key, current_image, image_width, image_height, "blocks")
                viu_lines = self._loading_lines(image_width, image_height)
            else:
                viu_lines = []
        else:
            viu_lines = None  # Skip preview rewrite

        # Build file list (fast direct ANSI, no Rich)
        file_list_lines = self._build_file_list_lines(file_list_width)

        # Write file list (always, padded to overwrite stale content)
        for row, line in enumerate(file_list_lines):
            parts.append(f'\033[{row + 1};{file_list_column}H')
            parts.append(self._pad_line(line, file_list_width))

        # Write preview (only when changed)
        if viu_lines is not None:
            for row in range(image_height):
                parts.append(f'\033[{row + 1};{image_column}H')
                if row < len(viu_lines):
                    parts.append(viu_lines[row])
                parts.append('\033[K')

        sys.stdout.write(''.join(parts))
        sys.stdout.flush()
        self._trigger_preload()

    def render_with_graphics_protocol(self):
        """Render TUI using graphics protocol for HD images.

        Uses direct ANSI line building (no Rich overhead) and skips preview
        rewrite when the image hasn't changed. No full-screen clear on
        subsequent renders to eliminate flickering.

        Double-buffered: text output is collected into a list and written
        in a single sys.stdout.write() call to eliminate visual tearing.
        Binary preview data (graphics protocol) is written separately via
        sys.stdout.buffer after flushing the text buffer.
        """
        parts = []

        self._terminal_size = os.get_terminal_size()
        terminal_size = self._terminal_size
        terminal_width = terminal_size.columns
        terminal_height = terminal_size.lines
        file_list_width = 55
        image_column = 60
        image_width = terminal_width - image_column - 2
        image_height = terminal_height - 2

        if self._first_render:
            parts.append('\033[2J\033[H')
            self._first_render = False
        else:
            parts.append('\033[H')

        # Build file list (fast direct ANSI, no Rich)
        file_list_lines = self._build_file_list_lines(file_list_width)

        # Write file list padded to fixed width (overwrites stale content)
        for row, line in enumerate(file_list_lines):
            parts.append(f'\033[{row + 1};1H')
            parts.append(self._pad_line(line, file_list_width))

        # Determine if preview needs updating
        current_image = self.images[self.current_index]
        cache_key = f"graphics:{current_image}:{image_width}:{image_height}"
        cache_hit = cache_key in self._image_cache
        preview_changed = (cache_key != self._last_preview_key) or (cache_hit and not self._last_preview_cached)

        # Binary preview data to write after flushing text buffer
        binary_preview = None

        if preview_changed:
            self._last_preview_key = cache_key
            self._last_preview_cached = cache_hit

            parts.append(f'\033[1;{image_column}H')

            if cache_hit:
                # Binary data must be written separately after text flush
                binary_preview = self._image_cache[cache_key]
            else:
                self._schedule_preview(cache_key, current_image, image_width, image_height, "graphics")
                parts.append("[Loading preview...]")

        # Flush all text output in a single write
        sys.stdout.write(''.join(parts))
        sys.stdout.flush()

        # Write binary preview data separately (can't join with strings)
        if binary_preview is not None:
            sys.stdout.buffer.write(binary_preview)
            sys.stdout.flush()

        self._trigger_preload()

    def render_with_preview(self, full_render: bool = True):
        """Render the TUI with appropriate method based on terminal capabilities.

        This is the main dispatcher that routes rendering to the appropriate renderer
        based on the detected graphics protocol support. It maintains backward
        compatibility while enabling high-fidelity image previews when available.

        Rendering paths:
        - Graphics protocol path (iterm/kitty/sixel): Always performs full render
          using render_with_graphics_protocol(). Graphics protocols render images
          as atomic escape sequences that can't be partially updated.

        - Block mode path (fallback): Uses render_with_blocks() with configurable
          full_render parameter. Block mode uses colored Unicode characters (▄▀)
          that are line-based text and support partial rendering for future
          optimization (currently always full render).

        Args:
            full_render: If True, performs full screen clear and render.
                        If False, performs partial update (block mode only).
                        Note: Graphics protocol path always does full render
                        regardless of this parameter.
        """
        protocol = self._protocol

        if protocol in ('iterm', 'kitty', 'sixel'):
            # Graphics protocol path - always full render
            self.render_with_graphics_protocol()
        else:
            # Block mode path - supports partial rendering
            self.render_with_blocks(full_render=full_render)

    def run(self) -> Optional[List[Path]]:
        """Run the interactive selector.

        Returns:
            List of selected image paths, or None if cancelled

        Raises:
            SystemExit: If user cancels (q/Escape)
        """
        # Import here to avoid issues if not in interactive terminal
        import tty
        import termios

        # Check viu availability
        if not check_viu_availability():
            fail_viu_not_found()

        # Save terminal settings
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)

        logger.info("Starting TUI selector")

        try:
            # Set terminal to raw mode for key capture
            tty.setraw(fd)

            # Hide cursor
            sys.stdout.write('\033[?25l')
            sys.stdout.flush()

            # Pre-load first few images on startup
            for i in range(min(5, len(self.images))):
                self._preload_image(i)

            # Initial render
            self.render_with_preview()

            while True:
                # Read key with a short timeout; wakes immediately on preview completion
                key = read_key_with_timeout_or_signal(0.05, extra_fds=[self._notify_r])

                if key is None:
                    if self._preview_dirty:
                        # Drain notification pipe
                        try:
                            os.read(self._notify_r, 1024)
                        except OSError:
                            pass
                        self._preview_dirty = False
                        self.render_with_preview()
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
                elif key == ' ':  # Spacebar
                    logger.debug("Space pressed")
                    self.toggle_selection()
                elif key == '\r' or key == '\n':  # Enter
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
                elif key in ('y', 'Y', 'x', 'X'):
                    # Just mark the image, don't proceed
                    logger.info(f"'{key}' pressed - toggling selection")
                    self.toggle_selection()
                elif key == 'n' or key == 'N':
                    if not self._selections_locked:
                        logger.info("'n' pressed but selections not locked - ignoring")
                        continue
                    logger.info("'n' pressed - proceeding to next stage")
                    return self.get_selected_images()
                elif key == 'a' or key == 'A':
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
                elif key == 'q' or key == 'Q':  # Quit
                    logger.info("Q pressed, exiting")
                    return None
                elif key == '\x03':  # Ctrl+C
                    logger.info("Ctrl+C pressed")
                    raise KeyboardInterrupt

                # Redraw with new preview
                self.render_with_preview()

        finally:
            # Restore terminal settings
            sys.stdout.write('\033[?25h')  # Show cursor
            sys.stdout.write('\033[2J\033[H')  # Clear screen
            sys.stdout.flush()
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            try:
                self._preview_executor.shutdown(wait=False, cancel_futures=True)
            except Exception:
                pass
            try:
                os.close(self._notify_r)
                os.close(self._notify_w)
            except OSError:
                pass


def show_processing_config(locked_images: List[Path], config: dict) -> dict:
    """Show processing configuration screen for locked images.

    Args:
        locked_images: List of selected image paths
        config: Configuration dict from photo-uploader.yaml

    Returns:
        Processing configuration dict with user's choices
    """
    import tty
    import termios

    console = Console()

    # Available output formats
    AVAILABLE_FORMATS = ['JPEG', 'PNG', 'WEBP']

    # Configuration options with defaults
    options = {
        'resize': True,  # Apply size optimization
        'preserve_exif': True,  # Preserve EXIF data
        'output_format': 'JPEG',  # Output format (cycles through AVAILABLE_FORMATS)
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
        header.append(f"Configure processing for {len(locked_images)} locked image(s)\n", style="dim")
        console.print(Panel(header, border_style="cyan"))
        console.print()

        # Create options table
        table = Table(show_header=True, box=None, padding=(0, 2))
        table.add_column("", width=3)
        table.add_column("Option", style="bold")
        table.add_column("Description")
        table.add_column("Value", justify="right")

        # Resize option
        resize_checkbox = "[x]" if options['resize'] else "[ ]"
        if current_option == 0:
            table.add_row(
                Text("►", style="bold cyan"),
                Text("Resize images", style="bold cyan"),
                Text(f"Optimize to ~{config.get('target_size_kb', 400)}KB", style="cyan"),
                Text(resize_checkbox, style="bold cyan")
            )
        else:
            table.add_row(
                Text(""),
                Text("Resize images"),
                Text(f"Optimize to ~{config.get('target_size_kb', 400)}KB"),
                Text(resize_checkbox)
            )

        # EXIF preservation option
        exif_checkbox = "[x]" if options['preserve_exif'] else "[ ]"
        if current_option == 1:
            table.add_row(
                Text("►", style="bold cyan"),
                Text("Preserve EXIF data", style="bold cyan"),
                Text("Keep camera, date, GPS info", style="cyan"),
                Text(exif_checkbox, style="bold cyan")
            )
        else:
            table.add_row(
                Text(""),
                Text("Preserve EXIF data"),
                Text("Keep camera, date, GPS info"),
                Text(exif_checkbox)
            )

        # Output format option
        format_value = options['output_format']
        format_desc = {
            'JPEG': 'Lossy compression, smallest size',
            'PNG': 'Lossless, larger size',
            'WEBP': 'Modern, balanced size/quality'
        }.get(format_value, '')

        if current_option == 2:
            table.add_row(
                Text("►", style="bold cyan"),
                Text("Output format", style="bold cyan"),
                Text(format_desc, style="cyan"),
                Text(format_value, style="bold cyan")
            )
        else:
            table.add_row(
                Text(""),
                Text("Output format"),
                Text(format_desc),
                Text(format_value)
            )

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
        sys.stdout.write('\033[?25l')
        sys.stdout.flush()

        # Initial render
        render_config_screen()

        while True:
            # Read a single character
            char = sys.stdin.read(1)

            # Handle escape sequences (arrow keys)
            if char == '\x1b':  # ESC
                next_char = sys.stdin.read(1)
                if next_char == '[':
                    arrow = sys.stdin.read(1)
                    if arrow == 'A':  # Up arrow
                        current_option = max(0, current_option - 1)
                    elif arrow == 'B':  # Down arrow
                        current_option = min(len(option_keys) - 1, current_option + 1)
                else:
                    # Escape key pressed (without arrow)
                    return None

            # Handle other keys
            elif char == ' ':  # Spacebar - toggle/cycle current option
                option_key = option_keys[current_option]
                if option_key == 'output_format':
                    # Cycle through available formats
                    current_format = options['output_format']
                    current_index = AVAILABLE_FORMATS.index(current_format)
                    next_index = (current_index + 1) % len(AVAILABLE_FORMATS)
                    options['output_format'] = AVAILABLE_FORMATS[next_index]
                else:
                    # Toggle boolean option
                    options[option_key] = not options[option_key]

            elif char == 'y' or char == 'Y':  # Y - confirm
                # Build result dictionary
                result = {
                    'resize': options['resize'],
                    'target_size_kb': config.get('target_size_kb', 400),
                    'preserve_exif': options['preserve_exif'],
                    'output_format': options['output_format'],
                }
                return result

            elif char == 'b' or char == 'B':  # Go back
                return None

            elif char == 'q' or char == 'Q':  # Quit
                return None

            elif char == '\x03':  # Ctrl+C
                raise KeyboardInterrupt

            # Redraw screen
            render_config_screen()

    finally:
        # Restore terminal settings
        sys.stdout.write('\033[?25h')  # Show cursor
        sys.stdout.flush()
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def select_images(images: List[Path]) -> List[Path]:
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
        raise SystemExit(1)

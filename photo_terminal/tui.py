"""Two-pane TUI for interactive image selection with viu preview.

Provides a terminal interface with:
- File list (left pane) with checkboxes and navigation
- Live viu preview (right pane) showing selected image
- Keyboard controls: arrows to navigate, spacebar to toggle, y to quick select, a to select all, enter to confirm
"""

import logging
import os
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import List, Optional

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

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

    def _preload_image(self, index: int) -> None:
        """Pre-load image at index into cache in background.

        Args:
            index: Index of image to pre-load
        """
        if index < 0 or index >= len(self.images):
            return  # Out of bounds

        image_path = self.images[index]
        protocol = TerminalCapabilities.detect_graphics_protocol()

        # Calculate dimensions (same as render methods)
        terminal_size = os.get_terminal_size()

        if protocol in ('iterm', 'kitty', 'ghostty', 'sixel'):
            # Graphics protocol dimensions
            terminal_width = terminal_size.columns
            terminal_height = terminal_size.lines
            image_column = 60
            image_width = terminal_width - image_column - 2
            image_height = terminal_height - 2

            cache_key = f"graphics:{image_path}:{image_width}:{image_height}"
            if cache_key not in self._image_cache:
                try:
                    result = subprocess.run(
                        ["viu", "-w", str(image_width), "-h", str(image_height), str(image_path)],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        timeout=5
                    )
                    if result.returncode == 0:
                        self._image_cache[cache_key] = result.stdout
                        logger.debug(f"Pre-loaded graphics output for {image_path.name}")
                except Exception as e:
                    logger.error(f"Pre-load failed for {image_path.name}: {e}")
        else:
            # Block mode dimensions
            file_list_width = 55
            image_column = file_list_width + 5
            image_width = max(20, min(terminal_size.columns - image_column - 2, 60))
            image_height = max(10, min(terminal_size.lines - 5, 35))

            cache_key = f"blocks:{image_path}:{image_width}:{image_height}"
            if cache_key not in self._image_cache:
                try:
                    result = subprocess.run(
                        ["viu", "-b", "-w", str(image_width), "-h", str(image_height), str(image_path)],
                        capture_output=True,
                        text=False,
                        timeout=5
                    )
                    if result.returncode == 0:
                        viu_lines = result.stdout.decode('utf-8', errors='replace').splitlines()
                        self._image_cache[cache_key] = viu_lines
                        logger.debug(f"Pre-loaded blocks output for {image_path.name}")
                except Exception as e:
                    logger.error(f"Pre-load failed for {image_path.name}: {e}")

    def _trigger_preload(self) -> None:
        """Pre-load adjacent images in background."""
        # Pre-load next image (N+1)
        if self.current_index + 1 < len(self.images):
            threading.Thread(
                target=self._preload_image,
                args=(self.current_index + 1,),
                daemon=True
            ).start()

        # Pre-load previous image (N-1)
        if self.current_index - 1 >= 0:
            threading.Thread(
                target=self._preload_image,
                args=(self.current_index - 1,),
                daemon=True
            ).start()

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
                checkbox = "[✓]"
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

        # Add controls footer
        controls_text = Text()
        controls_text.append("↑/↓ Nav  Space: Toggle  y: Quick Select  a: All\n", style="dim")
        controls_text.append("Enter: Confirm  q/Esc: Cancel", style="dim")

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

        This is the block-mode renderer that uses viu's -b flag to generate
        colored Unicode characters (▄▀) for image preview. It uses a side-by-side
        layout with the file list on the left and image preview on the right.

        This works because block output is line-based text - each line of viu output
        can be positioned independently using ANSI cursor positioning escape codes,
        allowing the file list and image to be rendered side-by-side.

        Args:
            full_render: If True, performs a full screen clear and render.
                        If False, performs partial update (currently unused but kept
                        for future optimization to reduce flicker).

        Layout:
            - File list: Column 1-55 (left side)
            - Image preview: Column 70+ (right side)
        """
        # Anti-flicker optimization: only clear screen on first render
        if self._first_render:
            # First render: Clear entire screen
            sys.stdout.write('\033[2J\033[H')
            self._first_render = False
        else:
            # Subsequent renders: Move cursor to home without clearing
            sys.stdout.write('\033[H')
        sys.stdout.flush()

        # Get current image
        current_image = self.images[self.current_index]

        # Calculate dimensions dynamically based on terminal size
        terminal_size = os.get_terminal_size()
        file_list_column = 1   # Start file list at column 1 (left)
        file_list_width = 55
        image_column = file_list_width + 5  # Start image after file list with spacing
        image_width = max(20, min(terminal_size.columns - image_column - 2, 60))
        image_height = max(10, min(terminal_size.lines - 5, 35))

        # Get the image lines with blocks (viu 1.6.1 only supports blocks)
        # Use cache to eliminate navigation delay
        cache_key = f"blocks:{current_image}:{image_width}:{image_height}"
        viu_lines = []

        if cache_key in self._image_cache:
            # Use cached output - instant!
            viu_lines = self._image_cache[cache_key]
            logger.debug(f"Using cached blocks output for {current_image.name}")
        elif check_viu_availability():
            try:
                # Use blocks - this viu version (1.6.1) doesn't support graphics protocols
                # Blocks are low-res by nature, but larger size helps
                result = subprocess.run(
                    ["viu", "-b", "-w", str(image_width), "-h", str(image_height), str(current_image)],
                    capture_output=True,
                    text=False,
                    timeout=5
                )

                if result.returncode == 0:
                    viu_lines = result.stdout.decode('utf-8', errors='replace').splitlines()
                    # Cache the splitlines() output for instant replay
                    self._image_cache[cache_key] = viu_lines
                    logger.debug(f"Cached blocks output for {current_image.name} ({len(viu_lines)} lines)")
            except Exception as e:
                logger.error(f"viu preview failed: {e}")
                viu_lines = [f"[Preview error: {e}]"]

        # Get file list lines (rendered to max 55 chars wide to not overlap image)
        narrow_console = Console(width=55, force_terminal=True)
        with narrow_console.capture() as capture:
            narrow_console.print(self.create_file_list_panel())
        file_list_lines = capture.get().splitlines()

        # Render both side-by-side using cursor positioning
        max_lines = max(len(file_list_lines), len(viu_lines))

        for row in range(max_lines):
            # Position and print file list line on the left
            if row < len(file_list_lines):
                sys.stdout.write(f'\033[{row + 1};{file_list_column}H')
                sys.stdout.write(file_list_lines[row])

            # Position and print image line on the right
            if row < len(viu_lines):
                sys.stdout.write(f'\033[{row + 1};{image_column}H')
                sys.stdout.write(viu_lines[row])

        sys.stdout.flush()

        # Pre-load adjacent images for faster navigation
        self._trigger_preload()

    def render_with_graphics_protocol(self):
        """Render TUI using graphics protocol for HD images.

        Layout: Side-by-side (file list left, image right) - macOS Finder style

        Rendering strategy to eliminate flickering:
        - First render: Clear entire screen, render file list + image
        - Subsequent renders: Move cursor to top, re-render file list in place,
          then clear and update only the image area
        - This approach updates the cursor/selection without full screen flash
        """
        # Calculate dimensions
        terminal_size = os.get_terminal_size()
        terminal_width = terminal_size.columns
        terminal_height = terminal_size.lines

        # Side-by-side layout: file list on left, image on right
        file_list_width = 55  # Fixed width for file list
        image_column = 60     # Where image starts (column position)
        image_width = terminal_width - image_column - 2  # Right side only
        image_height = terminal_height - 2  # Full height

        if self._first_render:
            # First render: Clear entire screen
            sys.stdout.write('\033[2J\033[H')
            sys.stdout.flush()
            self._first_render = False
        else:
            # Subsequent renders: Move cursor to home without clearing
            sys.stdout.write('\033[H')
            sys.stdout.flush()

        # Render file list at left (always, to show cursor changes)
        narrow_console = Console(width=file_list_width, force_terminal=True)
        with narrow_console.capture() as capture:
            narrow_console.print(self.create_file_list_panel())
        file_list_output = capture.get()
        file_list_lines = file_list_output.splitlines()

        # Clear screen (for refreshing both panes)
        sys.stdout.write('\033[J')

        # Write file list line-by-line on left side
        for row, line in enumerate(file_list_lines, start=1):
            sys.stdout.write(f'\033[{row};1H')  # Position at row, column 1
            sys.stdout.write(line)

        sys.stdout.flush()

        # Render new image with caching for instant navigation
        current_image = self.images[self.current_index]

        # Cache key includes dimensions to handle terminal resizes
        cache_key = f"graphics:{current_image}:{image_width}:{image_height}"

        # Position cursor at top-right where image should render
        sys.stdout.write(f'\033[1;{image_column}H')
        sys.stdout.flush()

        if cache_key in self._image_cache:
            # Use cached output - INSTANT!
            cached_output = self._image_cache[cache_key]
            sys.stdout.buffer.write(cached_output)
            sys.stdout.flush()
            logger.debug(f"Using cached graphics output for {current_image.name}")
        else:
            # Call viu and cache result
            # CRITICAL: Capture output to cache, then write it
            # This preserves the binary graphics protocol escape sequences
            try:
                result = subprocess.run(
                    ["viu", "-w", str(image_width), "-h", str(image_height), str(current_image)],
                    stdout=subprocess.PIPE,  # Capture for caching
                    stderr=subprocess.PIPE,
                    timeout=5
                )
                if result.returncode == 0:
                    # Cache and display the output
                    self._image_cache[cache_key] = result.stdout
                    sys.stdout.buffer.write(result.stdout)
                    sys.stdout.flush()
                    logger.debug(f"Cached graphics output for {current_image.name} ({len(result.stdout)} bytes)")
                else:
                    error_msg = result.stderr.decode('utf-8', errors='replace').strip()
                    sys.stdout.write(f"\n[Preview error: {error_msg}]\n")
                    sys.stdout.flush()
            except subprocess.TimeoutExpired:
                sys.stdout.write("[Preview timed out]")
                sys.stdout.flush()
            except Exception as e:
                sys.stdout.write(f"[Preview error: {e}]")
                sys.stdout.flush()

        # Pre-load adjacent images for faster navigation
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
        protocol = TerminalCapabilities.detect_graphics_protocol()

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

            # Initial render
            self.render_with_preview()

            while True:
                # Read a single character
                char = sys.stdin.read(1)

                # Handle escape sequences (arrow keys)
                if char == '\x1b':  # ESC
                    next_char = sys.stdin.read(1)
                    if next_char == '[':
                        arrow = sys.stdin.read(1)
                        if arrow == 'A':  # Up arrow
                            logger.debug("Up arrow pressed")
                            self.move_up()
                        elif arrow == 'B':  # Down arrow
                            logger.debug("Down arrow pressed")
                            self.move_down()
                    else:
                        # Escape key pressed (without arrow)
                        logger.info("Escape pressed, exiting")
                        return None

                # Handle other keys
                elif char == ' ':  # Spacebar
                    logger.debug("Space pressed")
                    self.toggle_selection()
                elif char == '\r' or char == '\n':  # Enter
                    logger.info("Enter pressed")
                    selected = self.get_selected_images()
                    if not selected:
                        # No images selected, continue
                        logger.warning("No images selected")
                        continue
                    return selected
                elif char == 'y' or char == 'Y':
                    # Select current image and proceed immediately
                    logger.info("'y' pressed - selecting current image and proceeding")
                    self.selected_indices = {self.current_index}  # Clear all, select only current
                    return self.get_selected_images()  # Return immediately
                elif char == 'a' or char == 'A':
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
                elif char == 'q' or char == 'Q':  # Quit
                    logger.info("Q pressed, exiting")
                    return None
                elif char == '\x03':  # Ctrl+C
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

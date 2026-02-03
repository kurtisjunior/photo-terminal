"""Interactive UI for image reordering with visual preview.

Uses the same two-pane rendering as Stage 1 (tui.py) with grab-and-drop reordering.
"""

from pathlib import Path
from typing import List, Optional, Tuple
import os
import subprocess
import sys
import termios
import tty

from photo_terminal.reorder import ImageReorderer, generate_prefixed_filenames, get_final_filenames_preview
from photo_terminal.tui import check_viu_availability, TerminalCapabilities


class ReorderImageSelector:
    """Image reorderer with two-pane TUI (same rendering as Stage 1)."""

    def __init__(self, images: List[Path]):
        """Initialize reorder selector.

        Args:
            images: List of image paths to reorder
        """
        if not images:
            raise ValueError("Images list cannot be empty")

        self.reorderer = ImageReorderer(images)
        self._image_cache = {}
        self._first_render = True
        self._protocol = TerminalCapabilities.detect_graphics_protocol()

    def _get_preview_lines(self, image_path: Path, width: int, height: int) -> List[str]:
        """Get cached preview lines for an image (same as tui.py)."""
        # Detect if we should use graphics protocol or blocks
        use_blocks = self._protocol == 'blocks'
        cache_key = f"{'blocks' if use_blocks else 'graphics'}:{image_path}:{width}:{height}"

        if cache_key in self._image_cache:
            return self._image_cache[cache_key]

        try:
            # Use graphics protocol if available (better quality), otherwise use blocks
            if use_blocks:
                cmd = ["viu", "-b", "-w", str(width), "-h", str(height), str(image_path)]
            else:
                # Graphics protocol - no -b flag for high quality
                cmd = ["viu", "-w", str(width), "-h", str(height), str(image_path)]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=False,
                timeout=3
            )
            if result.returncode == 0:
                lines = result.stdout.decode('utf-8', errors='replace').splitlines()
                self._image_cache[cache_key] = lines
                return lines
        except Exception:
            pass
        return ["[Preview error]"]

    def _create_file_list_lines(self) -> List[str]:
        """Create file list display lines."""
        images = self.reorderer.get_ordered_images()
        current_idx = self.reorderer.get_current_index()
        grabbed_idx = self.reorderer.get_grabbed_index()

        lines = []
        lines.append("╔═══════════════════════════════════════════════════╗")
        lines.append(f"║ Reorder Images ({len(images)} selected)")
        lines.append("╠═══════════════════════════════════════════════════╣")
        lines.append("║")

        for idx, img_path in enumerate(images):
            # Cursor and grabbed indicators
            if idx == current_idx and grabbed_idx is not None:
                cursor = "✱"
            elif idx == current_idx:
                cursor = "→"
            else:
                cursor = " "

            # Position number
            pos = f"{idx + 1}."

            # Filename (truncate if needed)
            filename = img_path.name
            if len(filename) > 35:
                filename = filename[:32] + "..."

            # Add grabbed indicator
            if idx == grabbed_idx:
                line = f"║ \033[1;32m{cursor}\033[0m {pos:3} \033[1;32m{filename}\033[0m"
            elif idx == current_idx:
                line = f"║ \033[1;33m{cursor}\033[0m {pos:3} \033[1;33m{filename}\033[0m"
            else:
                line = f"║ {cursor} {pos:3} {filename}"

            lines.append(line)

        lines.append("║")
        lines.append("╟───────────────────────────────────────────────────╢")
        lines.append("║ Final upload order:")
        preview = get_final_filenames_preview(images)
        if len(preview) > 45:
            preview = preview[:42] + "..."
        lines.append(f"║ \033[36m{preview}\033[0m")
        lines.append("╟───────────────────────────────────────────────────╢")
        lines.append("║ SPACE: grab/drop  ↑↓/j/k: move  r: reset")
        lines.append("║ ENTER: confirm  q: cancel")
        lines.append("╚═══════════════════════════════════════════════════╝")

        return lines

    def render(self):
        """Render two-pane UI (same approach as tui.py render_with_blocks)."""
        # Anti-flicker optimization
        if self._first_render:
            sys.stdout.write('\033[2J\033[H')
            self._first_render = False
        else:
            sys.stdout.write('\033[H')
        sys.stdout.flush()

        # Get dimensions
        terminal_size = os.get_terminal_size()
        file_list_column = 1
        file_list_width = 53
        image_column = file_list_width + 3
        image_width = max(40, min(terminal_size.columns - image_column - 2, 70))
        image_height = max(15, min(terminal_size.lines - 5, 35))

        # Get current image preview
        images = self.reorderer.get_ordered_images()
        current_idx = self.reorderer.get_current_index()
        current_image = images[current_idx]
        preview_lines = self._get_preview_lines(current_image, image_width, image_height)

        # Get file list
        file_list_lines = self._create_file_list_lines()

        # Render side-by-side
        max_lines = max(len(file_list_lines), len(preview_lines))
        for row in range(max_lines):
            # File list on left
            if row < len(file_list_lines):
                sys.stdout.write(f'\033[{row + 1};{file_list_column}H')
                sys.stdout.write(file_list_lines[row])

            # Preview on right
            if row < len(preview_lines):
                sys.stdout.write(f'\033[{row + 1};{image_column}H')
                sys.stdout.write(preview_lines[row])

        sys.stdout.flush()

    def run(self) -> Optional[List[Tuple[Path, str]]]:
        """Run the interactive reorder UI.

        Returns:
            List of (original_path, prefixed_filename) tuples if confirmed,
            None if cancelled
        """
        # Check viu availability
        if not check_viu_availability():
            print("Warning: viu not available, preview will be limited")

        # Save terminal settings
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)

        try:
            # Set raw mode
            tty.setraw(fd)

            # Hide cursor
            sys.stdout.write('\033[?25l')
            sys.stdout.flush()

            # Initial render
            self.render()

            while True:
                # Read key
                char = sys.stdin.read(1)

                # Handle escape sequences
                if char == '\x1b':
                    next_char = sys.stdin.read(1)
                    if next_char == '[':
                        arrow = sys.stdin.read(1)
                        if arrow == 'A':  # Up
                            self.reorderer.move_up()
                        elif arrow == 'B':  # Down
                            self.reorderer.move_down()
                    else:
                        # Lone ESC = cancel
                        return None

                # Handle regular keys
                elif char in ('j', 'J'):
                    self.reorderer.move_down()
                elif char in ('k', 'K'):
                    self.reorderer.move_up()
                elif char == ' ':  # Space = grab/drop
                    self.reorderer.toggle_grab()
                elif char in ('r', 'R'):  # Reset
                    self.reorderer.reset()
                elif char in ('\r', '\n'):  # Enter = confirm
                    ordered_images = self.reorderer.get_ordered_images()
                    return generate_prefixed_filenames(ordered_images)
                elif char in ('q', 'Q'):  # Quit
                    return None
                elif char == '\x03':  # Ctrl+C
                    raise KeyboardInterrupt

                # Redraw
                self.render()

        except KeyboardInterrupt:
            return None

        finally:
            # Restore terminal
            sys.stdout.write('\033[?25h')  # Show cursor
            sys.stdout.write('\033[2J\033[H')  # Clear screen
            sys.stdout.flush()
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def reorder_images_interactive(images: List[Path]) -> Optional[List[Tuple[Path, str]]]:
    """Interactive function to reorder images with visual preview.

    Args:
        images: List of image paths to reorder

    Returns:
        List of (original_path, prefixed_filename) tuples if confirmed,
        None if cancelled
    """
    if not images:
        return None

    selector = ReorderImageSelector(images)
    return selector.run()

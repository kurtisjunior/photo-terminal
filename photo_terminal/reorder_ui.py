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
import threading
from concurrent.futures import ThreadPoolExecutor

from photo_terminal.reorder import ImageReorderer, generate_prefixed_filenames, get_final_filenames_preview
from photo_terminal.tui import check_viu_availability, TerminalCapabilities
from photo_terminal.input_utils import KEY_DOWN, KEY_ESC, KEY_UP, read_key_with_timeout


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
        self._preview_executor = ThreadPoolExecutor(max_workers=2)
        self._preview_futures = {}
        self._preview_lock = threading.Lock()
        self._preview_dirty = False

    def _schedule_preview(self, cache_key: str, image_path: Path, width: int, height: int, use_blocks: bool) -> None:
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
                use_blocks
            )
            self._preview_futures[cache_key] = future
        future.add_done_callback(lambda f, key=cache_key: self._store_preview_result(key, f))

    def _store_preview_result(self, cache_key: str, future) -> None:
        try:
            output = future.result()
        except Exception as e:
            output = [f"[Preview error: {e}]"]
        with self._preview_lock:
            self._preview_futures.pop(cache_key, None)
            if output is not None:
                self._image_cache[cache_key] = output
            self._preview_dirty = True

    @staticmethod
    def _render_preview_output(image_path: Path, width: int, height: int, use_blocks: bool):
        if use_blocks:
            cmd = ["viu", "-b", "-w", str(width), "-h", str(height), str(image_path)]
        else:
            cmd = ["viu", "-w", str(width), "-h", str(height), str(image_path)]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=False,
            timeout=3
        )
        if result.returncode == 0:
            return result.stdout.decode('utf-8', errors='replace').splitlines()
        error_msg = result.stderr.decode('utf-8', errors='replace').strip()
        return [f"[Preview error: {error_msg}]"]

    def _get_preview_lines(self, image_path: Path, width: int, height: int) -> List[str]:
        """Get cached preview lines for an image (same as tui.py)."""
        # Detect if we should use graphics protocol or blocks
        use_blocks = self._protocol == 'blocks'
        cache_key = f"{'blocks' if use_blocks else 'graphics'}:{image_path}:{width}:{height}"

        if cache_key in self._image_cache:
            return self._image_cache[cache_key]

        self._schedule_preview(cache_key, image_path, width, height, use_blocks)
        return ["[Loading preview...]"]

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
                key = read_key_with_timeout(0.05)

                if key is None:
                    if self._preview_dirty:
                        self._preview_dirty = False
                        self.render()
                    continue

                if key == KEY_UP:
                    self.reorderer.move_up()
                elif key == KEY_DOWN:
                    self.reorderer.move_down()
                elif key == KEY_ESC:
                    return None

                # Handle regular keys
                elif key in ('j', 'J'):
                    self.reorderer.move_down()
                elif key in ('k', 'K'):
                    self.reorderer.move_up()
                elif key == ' ':  # Space = grab/drop
                    self.reorderer.toggle_grab()
                elif key in ('r', 'R'):  # Reset
                    self.reorderer.reset()
                elif key in ('\r', '\n'):  # Enter = confirm
                    ordered_images = self.reorderer.get_ordered_images()
                    return generate_prefixed_filenames(ordered_images)
                elif key in ('q', 'Q'):  # Quit
                    return None
                elif key == '\x03':  # Ctrl+C
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
            try:
                self._preview_executor.shutdown(wait=False, cancel_futures=True)
            except Exception:
                pass


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

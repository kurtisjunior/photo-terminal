"""Two-pane TUI for interactive image selection with viu preview.

Provides a terminal interface with:
- File list (left pane) with checkboxes and navigation
- Live viu preview (right pane) showing selected image
- Keyboard controls: arrows to navigate, spacebar to toggle, enter to confirm
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


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


def get_viu_preview(image_path: Path, width: int, height: int) -> str:
    """Generate viu preview output for an image.

    Args:
        image_path: Path to image file
        width: Width in characters for preview
        height: Height in characters for preview

    Returns:
        String containing viu output with ANSI escape codes
    """
    try:
        # Run viu with appropriate flags
        # -w: width in terminal columns
        # -h: height in terminal rows
        # -t: transparent background
        result = subprocess.run(
            ["viu", "-w", str(width), "-h", str(height), "-t", str(image_path)],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode == 0:
            return result.stdout
        else:
            return f"[Error rendering preview]\n{result.stderr}"

    except subprocess.TimeoutExpired:
        return "[Preview timed out]"
    except Exception as e:
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
        self.console = Console()

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

        # Add controls footer
        controls_text = Text()
        controls_text.append("\n" + "─" * 30 + "\n", style="dim")
        controls_text.append("↑/↓: Navigate  Space: Toggle\n", style="dim")
        controls_text.append("Enter: Confirm  q/Esc: Cancel", style="dim")

        title = f"Images ({len(self.selected_indices)}/{len(self.images)} selected)"
        return Panel(Group(table, controls_text), title=title, border_style="blue")

    def create_preview_panel(self) -> Panel:
        """Create the preview panel with viu output.

        Returns:
            Panel containing the image preview
        """
        current_image = self.images[self.current_index]

        # Get terminal size to calculate preview dimensions
        terminal_width = self.console.width or 80
        terminal_height = self.console.height or 24

        # Reserve space for file list (left pane) and borders
        # File list takes ~40% of width, preview takes ~60%
        preview_width = int(terminal_width * 0.5)
        preview_height = terminal_height - 10  # Reserve space for panels and controls

        # Get viu preview
        preview = get_viu_preview(current_image, preview_width, preview_height)

        title = f"Preview: {current_image.name}"
        return Panel(preview, title=title, border_style="green")

    def create_layout(self) -> Layout:
        """Create the two-pane layout.

        Returns:
            Layout with file list and preview panels
        """
        layout = Layout()
        layout.split_row(
            Layout(name="file_list", ratio=2),
            Layout(name="preview", ratio=3)
        )

        layout["file_list"].update(self.create_file_list_panel())
        layout["preview"].update(self.create_preview_panel())

        return layout

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

        # Save terminal settings
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)

        try:
            # Set terminal to raw mode for key capture
            tty.setraw(fd)

            with Live(self.create_layout(), console=self.console, refresh_per_second=4) as live:
                while True:
                    # Read a single character
                    char = sys.stdin.read(1)

                    # Handle escape sequences (arrow keys)
                    if char == '\x1b':  # ESC
                        next_char = sys.stdin.read(1)
                        if next_char == '[':
                            arrow = sys.stdin.read(1)
                            if arrow == 'A':  # Up arrow
                                self.move_up()
                            elif arrow == 'B':  # Down arrow
                                self.move_down()
                        else:
                            # Escape key pressed (without arrow)
                            raise SystemExit(1)

                    # Handle other keys
                    elif char == ' ':  # Spacebar
                        self.toggle_selection()
                    elif char == '\r' or char == '\n':  # Enter
                        selected = self.get_selected_images()
                        if not selected:
                            # No images selected, continue
                            continue
                        return selected
                    elif char == 'q' or char == 'Q':  # Quit
                        raise SystemExit(1)
                    elif char == '\x03':  # Ctrl+C
                        raise KeyboardInterrupt

                    # Update the display
                    live.update(self.create_layout())

        finally:
            # Restore terminal settings
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def select_images(images: List[Path]) -> List[Path]:
    """Interactive image selection with two-pane TUI.

    Args:
        images: List of valid image paths from scanner

    Returns:
        List of selected image paths

    Raises:
        SystemExit: If viu not available or user cancels
    """
    # Check viu availability first (fail-fast)
    if not check_viu_availability():
        fail_viu_not_found()

    # Validate input
    if not images:
        print("Error: No images provided for selection")
        raise SystemExit(1)

    # Run interactive selector
    selector = ImageSelector(images)

    try:
        selected = selector.run()

        if selected is None or not selected:
            print("\nNo images selected")
            raise SystemExit(1)

        return selected

    except KeyboardInterrupt:
        print("\n\nCancelled by user")
        raise SystemExit(1)

"""Interactive UI for image reordering with Rich library.

Provides a slick, keyboard-driven interface for reordering images
using grab-and-drop interaction model.
"""

from pathlib import Path
from typing import List, Optional, Tuple
import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.layout import Layout
from rich.live import Live
from rich import box

from photo_terminal.reorder import ImageReorderer, generate_prefixed_filenames, get_final_filenames_preview


class ReorderUI:
    """Interactive UI for reordering images.

    Provides a slick interface with keyboard controls:
    - j/k or ↑/↓: Navigate up/down
    - Space: Grab/drop current image
    - r: Reset to original order
    - Enter: Confirm and continue
    - q: Cancel and exit

    Uses Rich library for smooth real-time rendering.
    """

    def __init__(self, images: List[Path], console: Optional[Console] = None):
        """Initialize reorder UI.

        Args:
            images: List of image paths to reorder
            console: Optional Rich Console instance (creates new if None)

        Raises:
            ValueError: If images list is empty
        """
        if not images:
            raise ValueError("Images list cannot be empty")

        self.reorderer = ImageReorderer(images)
        self.console = console or Console()
        self.should_exit = False
        self.cancelled = False

    def _render(self) -> Panel:
        """Render the current UI state.

        Returns:
            Rich Panel containing the full UI
        """
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=1),
            Layout(name="main"),
            Layout(name="preview", size=3),
            Layout(name="controls", size=3)
        )

        # Header
        images = self.reorderer.get_ordered_images()
        header_text = Text(f"Reorder Images ({len(images)} selected)", style="bold cyan")
        layout["header"].update(header_text)

        # Main image list
        table = Table(show_header=False, box=box.SIMPLE, padding=(0, 1))
        table.add_column("Cursor", width=3)
        table.add_column("Number", width=4)
        table.add_column("Filename", style="white")

        current_idx = self.reorderer.get_current_index()
        grabbed_idx = self.reorderer.get_grabbed_index()

        for idx, img_path in enumerate(images):
            # Cursor indicator
            if idx == current_idx:
                cursor = "→" if grabbed_idx is None else "✱"
                cursor_style = "bold yellow" if grabbed_idx is None else "bold green"
            else:
                cursor = ""
                cursor_style = "dim"

            # Position number
            pos = f"{idx + 1}."

            # Filename with styling
            filename = img_path.name
            if idx == grabbed_idx:
                # Grabbed item - highlight
                filename_style = "bold green"
            elif idx == current_idx:
                # Current selection
                filename_style = "bold yellow"
            else:
                # Normal item
                filename_style = "white"

            table.add_row(
                Text(cursor, style=cursor_style),
                Text(pos, style="dim"),
                Text(filename, style=filename_style)
            )

        layout["main"].update(table)

        # Preview of final filenames
        preview_text = Text()
        preview_text.append("Final upload names:\n", style="dim")
        preview_text.append(get_final_filenames_preview(images), style="cyan")
        layout["preview"].update(preview_text)

        # Controls
        controls = Table.grid(padding=(0, 2))
        controls.add_row(
            Text("SPACE", style="bold"),
            Text("grab/drop", style="dim"),
            Text("•", style="dim"),
            Text("↑↓ or j/k", style="bold"),
            Text("move", style="dim"),
            Text("•", style="dim"),
            Text("r", style="bold"),
            Text("reset", style="dim")
        )
        controls.add_row(
            Text("ENTER", style="bold green"),
            Text("confirm", style="dim"),
            Text("•", style="dim"),
            Text("q", style="bold red"),
            Text("cancel", style="dim"),
            Text("", style="dim"),
            Text("", style="dim"),
            Text("", style="dim")
        )
        layout["controls"].update(controls)

        # Wrap in panel
        panel = Panel(
            layout,
            border_style="cyan",
            box=box.ROUNDED
        )

        return panel

    def _handle_key(self, key: str) -> bool:
        """Handle keyboard input.

        Args:
            key: Key pressed by user

        Returns:
            True if UI should continue, False if should exit
        """
        # Navigation
        if key in ('j', 'down'):
            self.reorderer.move_down()
        elif key in ('k', 'up'):
            self.reorderer.move_up()

        # Grab/drop
        elif key == ' ':
            self.reorderer.toggle_grab()

        # Reset
        elif key == 'r':
            self.reorderer.reset()

        # Confirm
        elif key in ('enter', '\r', '\n'):
            self.should_exit = True
            return False

        # Cancel
        elif key in ('q', 'Q'):
            self.cancelled = True
            self.should_exit = True
            return False

        return True

    def run(self) -> Optional[List[Tuple[Path, str]]]:
        """Run the interactive reorder UI.

        Displays the UI and handles keyboard input until user confirms or cancels.

        Returns:
            List of (original_path, prefixed_filename) tuples if confirmed,
            None if cancelled

        Example:
            ui = ReorderUI(image_paths)
            result = ui.run()
            if result:
                # User confirmed order
                for original, new_name in result:
                    print(f"{original} → {new_name}")
        """
        # Import here to avoid issues on systems without proper terminal support
        try:
            import readchar
        except ImportError:
            self.console.print(
                "[red]Error: readchar library not installed. "
                "Install with: pip install readchar[/red]"
            )
            return None

        # Run live display
        with Live(self._render(), console=self.console, refresh_per_second=10) as live:
            while not self.should_exit:
                try:
                    # Read a key (blocking)
                    key = readchar.readkey()

                    # Map arrow keys
                    if key == readchar.key.UP:
                        key = 'up'
                    elif key == readchar.key.DOWN:
                        key = 'down'
                    elif key == readchar.key.ENTER or key == '\r' or key == '\n':
                        key = 'enter'

                    # Handle the key
                    should_continue = self._handle_key(key)

                    if not should_continue:
                        break

                    # Update display
                    live.update(self._render())

                except KeyboardInterrupt:
                    # Ctrl+C pressed - cancel
                    self.cancelled = True
                    break

        # Return result
        if self.cancelled:
            return None

        ordered_images = self.reorderer.get_ordered_images()
        return generate_prefixed_filenames(ordered_images)


def reorder_images_interactive(images: List[Path]) -> Optional[List[Tuple[Path, str]]]:
    """Interactive function to reorder images.

    Convenience function that creates UI and runs it.

    Args:
        images: List of image paths to reorder

    Returns:
        List of (original_path, prefixed_filename) tuples if confirmed,
        None if cancelled

    Example:
        result = reorder_images_interactive(image_paths)
        if result:
            for original, new_name in result:
                process_image(original, new_name)
    """
    if not images:
        return None

    ui = ReorderUI(images)
    return ui.run()

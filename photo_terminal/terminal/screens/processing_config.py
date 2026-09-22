"""Stage 3: choose how the locked images are processed.

Three options - resize, EXIF preservation, output format - navigated with the
arrows and toggled with Space. Rich draws the table here rather than the
in-house painter: there is no graphics placement on this screen and no cursor
positioning to control, which is exactly the case Rich is good at.

It reads keys through the shared reader like every other screen. It used to
call ``sys.stdin.read(1)`` and parse escape sequences itself, with no ESC
timeout, so a bare Escape blocked until the next keypress.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from photo_terminal.terminal.input import KEY_DOWN, KEY_ESC, KEY_UP, read_key
from photo_terminal.terminal.session import TerminalSession


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

    def render_config_screen() -> None:
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

    with TerminalSession():
        # Initial render
        render_config_screen()

        while True:
            # One reader for every screen: a bare ESC acts immediately instead
            # of blocking until the next keypress.
            char = read_key()

            if char is None:  # an escape sequence this screen has no use for
                continue

            if char == KEY_UP:
                current_option = max(0, current_option - 1)

            elif char == KEY_DOWN:
                current_option = min(len(option_keys) - 1, current_option + 1)

            elif char == KEY_ESC:
                return None

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

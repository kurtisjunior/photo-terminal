#!/usr/bin/env python3
"""Minimal TUI test to diagnose blank screen."""

import sys
import tty
import termios
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.live import Live

# Get images
image_dir = Path("~/Desktop/new-post/Oct").expanduser()
images = sorted(list(image_dir.glob("*.JPG")))

if not images:
    print("No images found")
    exit(1)

print(f"Found {len(images)} images")
print("Starting TUI in 2 seconds...")
import time
time.sleep(2)

console = Console()

# Test 1: Can we create a simple panel?
text = Text("Hello World\n")
text.append("Line 2\n")
text.append("Line 3")
panel = Panel(text, title="Test Panel")

print("\nTest 1: Print panel normally")
console.print(panel)

print("\nPress Enter to test Live rendering...")
input()

# Test 2: Can Live render the same panel?
fd = sys.stdin.fileno()
old_settings = termios.tcgetattr(fd)

try:
    tty.setraw(fd)

    with Live(panel, console=console, refresh_per_second=2, screen=True) as live:
        print("Live started, waiting for input...")
        char = sys.stdin.read(1)

finally:
    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

print("\nTest complete!")

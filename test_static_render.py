#!/usr/bin/env python3
"""Test static rendering without Live."""

import subprocess
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.layout import Layout

# Get first image
image_dir = Path("~/Desktop/new-post/Oct").expanduser()
images = sorted(list(image_dir.glob("*.JPG")))
if not images:
    print("No images found")
    exit(1)

image = images[0]
print(f"Testing with: {image.name}\n")

# Run viu
result = subprocess.run(
    ["viu", "-b", "-w", "30", str(image)],
    capture_output=True,
    text=True,
    timeout=5
)

print(f"viu returned {len(result.stdout)} chars, {len(result.stdout.splitlines())} lines\n")

# Try to render it
console = Console()

print("=== Test 1: Direct print of viu output ===")
print(result.stdout[:500])  # First 500 chars

print("\n=== Test 2: Rich Text.from_ansi ===")
text = Text.from_ansi(result.stdout)
print(f"Text object: {len(text)} chars")
console.print(text)

print("\n=== Test 3: Inside Panel ===")
panel = Panel(text, title="Preview")
console.print(panel)

print("\n=== Test 4: Inside Layout ===")
layout = Layout()
layout.split_row(
    Layout(Panel("File List", title="Images")),
    Layout(Panel(text, title="Preview"))
)
console.print(layout)

print("\nIf you see the image in tests 2-4, rendering works!")
print("If not, Rich has issues with the ANSI output.")

#!/usr/bin/env python3
"""Simple test to isolate the TUI rendering issue."""

import subprocess
from pathlib import Path
from rich.console import Console
from rich.text import Text
from rich.panel import Panel

# Test with one of your images
test_image = Path("~/Desktop/new-post/Oct").expanduser()
images = list(test_image.glob("*.jpg")) + list(test_image.glob("*.JPG"))

if not images:
    print("No images found")
    exit(1)

image = images[0]
print(f"Testing with: {image}")

# Test 1: Can we run viu at all?
print("\n1. Testing viu command directly...")
result = subprocess.run(
    ["viu", "-b", "-w", "30", str(image)],
    capture_output=True,
    text=True,
    timeout=5
)
print(f"Return code: {result.returncode}")
print(f"Output length: {len(result.stdout)} chars")
print(f"First line: {result.stdout.splitlines()[0] if result.stdout else 'EMPTY'}")

# Test 2: Can Rich render the ANSI output?
print("\n2. Testing Rich Text.from_ansi...")
console = Console()
preview_text = Text.from_ansi(result.stdout)
print(f"Text object created: {len(preview_text)} chars")

# Test 3: Can we display it in a Panel?
print("\n3. Testing Panel rendering...")
panel = Panel(preview_text, title="Test Preview")
console.print(panel)

print("\nIf you see the image above, Rich rendering works.")
print("If not, the issue is with Rich's ANSI processing.")

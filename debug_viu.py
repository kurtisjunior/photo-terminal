#!/usr/bin/env python3
"""Debug script to test viu output directly."""

import subprocess
import sys
from pathlib import Path

if len(sys.argv) < 2:
    print("Usage: python debug_viu.py <image_path>")
    sys.exit(1)

image_path = Path(sys.argv[1])

if not image_path.exists():
    print(f"Error: {image_path} does not exist")
    sys.exit(1)

print("Testing viu with different parameters...")
print("=" * 80)

# Test 1: Small size (what the TUI would use)
print("\n1. Small size (50x25):")
print("-" * 80)
result = subprocess.run(
    ["viu", "-b", "-w", "50", "-h", "25", str(image_path)],
    capture_output=False
)

print("\n" + "=" * 80)

# Test 2: Without height constraint
print("\n2. Width only (50):")
print("-" * 80)
result = subprocess.run(
    ["viu", "-b", "-w", "50", str(image_path)],
    capture_output=False
)

print("\n" + "=" * 80)

# Test 3: Larger size
print("\n3. Larger size (80x40):")
print("-" * 80)
result = subprocess.run(
    ["viu", "-b", "-w", "80", "-h", "40", str(image_path)],
    capture_output=False
)

print("\n" + "=" * 80)
print("\nIf images look correct here, the issue is with Rich rendering.")
print("If images look broken here, the issue is with viu parameters.")

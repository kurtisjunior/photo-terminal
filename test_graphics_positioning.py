#!/usr/bin/env python3
import subprocess
import sys

# Print instructions
print("Testing graphics protocol column positioning...")
print("Expected: Text on left, image on right")
print("If image overwrites text, graphics protocol doesn't respect column positioning")
print()
print("Press Enter to start test...")
input()

# Clear screen
sys.stdout.write('\033[2J\033[H')

# Write text on left side (columns 1-50)
for i in range(1, 20):
    sys.stdout.write(f'\033[{i};1H')
    sys.stdout.write(f"Line {i:2d} - Text on LEFT side (col 1-50)")

sys.stdout.flush()

# Position cursor at column 60, row 1 for image
sys.stdout.write('\033[1;60H')
sys.stdout.flush()

# Run viu WITHOUT -b flag (graphics protocol)
# Use a test image from the Oct folder
subprocess.run([
    "viu",
    "-w", "50",  # 50 columns wide
    "-h", "15",  # 15 lines tall
    "/Users/kurtis/Desktop/new-post/Oct/22690027.JPG"
], stdout=sys.stdout)

print("\n\nTest complete. Did the image appear on the right without overwriting left text? (y/n)")

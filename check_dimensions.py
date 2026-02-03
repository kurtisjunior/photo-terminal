"""Check image dimensions."""
import sys
from PIL import Image
from pathlib import Path

path = Path(sys.argv[1])
img = Image.open(path)
print(f"Dimensions: {img.width} x {img.height}")
print(f"Pixels: {img.width * img.height:,}")
print(f"File size: {path.stat().st_size / 1024:.1f}KB")

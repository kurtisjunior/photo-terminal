"""Debug script to test optimizer with actual files."""

import sys
from pathlib import Path
from photo_terminal.optimizer import optimize_image
import tempfile


if len(sys.argv) < 2:
    print("Usage: python debug_optimizer.py <image_path>")
    sys.exit(1)

input_path = Path(sys.argv[1])
if not input_path.exists():
    print(f"Error: File not found: {input_path}")
    sys.exit(1)

print(f"Testing optimizer with: {input_path}")
print(f"Original size: {input_path.stat().st_size / 1024:.1f}KB")
print("-" * 60)

with tempfile.TemporaryDirectory() as tmpdir:
    output_path = Path(tmpdir) / "output.jpg"

    result = optimize_image(
        input_path,
        output_path,
        target_size_kb=400,
        output_format='JPEG',
        max_dimension=1920
    )

    print(f"Original size:     {result['original_size'] / 1024:.1f}KB")
    print(f"Final size:        {result['final_size'] / 1024:.1f}KB")
    print(f"Quality used:      {result['quality_used']}")
    print(f"Original format:   {result['format']}")
    print(f"Output format:     {result['output_format']}")
    print(f"Resized:           {result['resized']}")
    print(f"Original dims:     {result['original_dimensions'][0]} x {result['original_dimensions'][1]}")
    print(f"Final dims:        {result['final_dimensions'][0]} x {result['final_dimensions'][1]}")

    if result['warnings']:
        print(f"\nWarnings:")
        for warning in result['warnings']:
            print(f"  - {warning}")

    print("-" * 60)

    if result['final_size'] > 400 * 1024:
        print(f"❌ FAILED: Final size {result['final_size'] / 1024:.1f}KB exceeds 400KB target!")
        sys.exit(1)
    else:
        print(f"✓ PASSED: Final size respects 400KB limit")

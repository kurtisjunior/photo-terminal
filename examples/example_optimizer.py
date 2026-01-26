#!/usr/bin/env python3
"""Example script demonstrating the optimizer module.

This script shows how to use the optimizer to reduce image file sizes
while preserving EXIF data and aspect ratio.
"""

from pathlib import Path
import tempfile
from photo_terminal.optimizer import optimize_image


def main():
    """Run optimizer example with test.jpeg file."""
    # Input file
    test_image = Path(__file__).parent / "test.jpeg"

    if not test_image.exists():
        print(f"Error: test.jpeg not found at {test_image}")
        return

    print("Image Optimizer Example")
    print("=" * 60)
    print(f"Input: {test_image}")
    print(f"Original size: {test_image.stat().st_size / 1024:.1f} KB")
    print()

    # Create temp directory for outputs
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Example 1: Optimize to 400KB (default)
        print("Example 1: Optimize to 400KB target")
        print("-" * 60)
        output1 = temp_path / "optimized_400kb.jpg"
        result1 = optimize_image(test_image, output1, target_size_kb=400)
        print(f"Output: {output1}")
        print(f"Final size: {result1['final_size'] / 1024:.1f} KB")
        print(f"Quality used: {result1['quality_used']}")
        print(f"Format: {result1['format']}")
        if result1['warnings']:
            print(f"Warnings:")
            for warning in result1['warnings']:
                print(f"  - {warning}")
        print()

        # Example 2: Optimize to 200KB (smaller target)
        print("Example 2: Optimize to 200KB target")
        print("-" * 60)
        output2 = temp_path / "optimized_200kb.jpg"
        result2 = optimize_image(test_image, output2, target_size_kb=200)
        print(f"Output: {output2}")
        print(f"Final size: {result2['final_size'] / 1024:.1f} KB")
        print(f"Quality used: {result2['quality_used']}")
        if result2['warnings']:
            print(f"Warnings:")
            for warning in result2['warnings']:
                print(f"  - {warning}")
        print()

        # Example 3: Optimize to 800KB (larger target)
        print("Example 3: Optimize to 800KB target")
        print("-" * 60)
        output3 = temp_path / "optimized_800kb.jpg"
        result3 = optimize_image(test_image, output3, target_size_kb=800)
        print(f"Output: {output3}")
        print(f"Final size: {result3['final_size'] / 1024:.1f} KB")
        print(f"Quality used: {result3['quality_used']}")
        if result3['warnings']:
            print(f"Warnings:")
            for warning in result3['warnings']:
                print(f"  - {warning}")
        print()

        # Summary
        print("Summary")
        print("=" * 60)
        print(f"Original size: {test_image.stat().st_size / 1024:.1f} KB")
        print(f"400KB target: {result1['final_size'] / 1024:.1f} KB (quality {result1['quality_used']})")
        print(f"200KB target: {result2['final_size'] / 1024:.1f} KB (quality {result2['quality_used']})")
        print(f"800KB target: {result3['final_size'] / 1024:.1f} KB (quality {result3['quality_used']})")
        print()
        print("Note: Temp files cleaned up automatically")


if __name__ == "__main__":
    main()

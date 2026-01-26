#!/usr/bin/env python3
"""Example demonstrating dry-run mode functionality.

This example shows how dry_run_upload processes images and displays
size information without actually uploading to S3.
"""

import tempfile
from pathlib import Path
from PIL import Image

from dry_run import dry_run_upload


def create_test_images(output_dir: Path, count: int = 3) -> list[Path]:
    """Create sample test images with varying sizes.

    Args:
        output_dir: Directory to save test images
        count: Number of test images to create

    Returns:
        List of paths to created images
    """
    images = []

    # Create images with different sizes
    sizes = [(2000, 1500), (1600, 1200), (1920, 1080)]
    colors = [(255, 100, 100), (100, 255, 100), (100, 100, 255)]

    for i in range(min(count, len(sizes))):
        img_path = output_dir / f"sample_image_{i+1}.jpg"

        # Create image with specific size and color
        img = Image.new('RGB', sizes[i], color=colors[i])

        # Save with high quality to ensure large file size
        img.save(img_path, 'JPEG', quality=95)

        images.append(img_path)
        print(f"Created test image: {img_path.name} ({sizes[i][0]}x{sizes[i][1]})")

    return images


def main():
    """Run dry-run example."""
    print("Dry-Run Mode Example")
    print("=" * 50)
    print()
    print("This example demonstrates the dry-run mode which:")
    print("  1. Processes images to calculate sizes")
    print("  2. Shows original vs. processed file sizes")
    print("  3. Displays target S3 location")
    print("  4. Lists S3 keys that would be created")
    print("  5. Does NOT upload anything to S3")
    print("  6. Cleans up temp files after displaying info")
    print()

    # Create temporary directory for test images
    with tempfile.TemporaryDirectory(prefix="dry_run_example_") as tmp_dir:
        tmp_path = Path(tmp_dir)

        print("Creating test images...")
        images = create_test_images(tmp_path, count=3)
        print()

        print("Running dry-run mode...")
        print()

        try:
            # Run dry-run upload
            dry_run_upload(
                images=images,
                bucket='example-bucket',
                prefix='photos/vacation/2024',
                target_size_kb=400,
                aws_profile='default'
            )
        except SystemExit as e:
            # Dry-run always exits, check exit code
            if e.code == 0:
                print()
                print("Dry-run completed successfully!")
            else:
                print()
                print(f"Dry-run failed with exit code: {e.code}")


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Example usage of the image processor module.

Demonstrates how to use the process_images function to batch process
images with automatic cleanup and retry scenarios.
"""

from pathlib import Path
from processor import (
    process_images,
    ProcessingError,
    InsufficientDiskSpaceError
)


def main():
    # Example 1: Basic usage with automatic cleanup
    print("Example 1: Basic usage")
    print("-" * 50)

    # Create a list of image paths (replace with actual paths)
    image_paths = [
        Path("path/to/image1.jpg"),
        Path("path/to/image2.jpg"),
        Path("path/to/image3.jpg"),
    ]

    # Note: For this example to work, you need actual images
    # Uncomment and modify paths as needed:
    # image_paths = [
    #     Path.home() / "Pictures" / "photo1.jpg",
    #     Path.home() / "Pictures" / "photo2.jpg",
    # ]

    print(f"Processing {len(image_paths)} images...")
    print()

    try:
        # Process images with default target size (400KB)
        temp_dir, processed_images = process_images(image_paths)

        print("\nProcessing complete!")
        print(f"Temp directory: {temp_dir.name}")
        print()

        # Review results
        for i, proc_img in enumerate(processed_images, 1):
            print(f"Image {i}: {proc_img.original_path.name}")
            print(f"  Original size: {proc_img.original_size / 1024:.1f} KB")
            print(f"  Final size: {proc_img.final_size / 1024:.1f} KB")
            print(f"  Quality used: {proc_img.quality_used}")
            print(f"  Reduction: {(1 - proc_img.final_size / proc_img.original_size) * 100:.1f}%")

            if proc_img.warnings:
                print(f"  Warnings:")
                for warning in proc_img.warnings:
                    print(f"    - {warning}")
            print()

        # At this point, you would typically upload the processed images
        # For example: upload_to_s3(processed_images)

        # When done successfully, cleanup temp directory
        print("Cleaning up temp directory...")
        temp_dir.cleanup()
        print("Done!")

    except InsufficientDiskSpaceError as e:
        print(f"Error: {e}")
        print("Please free up disk space and try again.")

    except ProcessingError as e:
        print(f"Error: {e}")
        print("Processing failed.")

    print()
    print()

    # Example 2: Custom target size
    print("Example 2: Custom target size")
    print("-" * 50)

    try:
        # Process with 500KB target instead of default 400KB
        temp_dir, processed_images = process_images(
            image_paths,
            target_size_kb=500
        )

        print(f"\nProcessed {len(processed_images)} images with 500KB target")

        # Show results
        for proc_img in processed_images:
            print(f"  {proc_img.original_path.name}: "
                  f"{proc_img.original_size / 1024:.1f}KB → "
                  f"{proc_img.final_size / 1024:.1f}KB")

        temp_dir.cleanup()

    except Exception as e:
        print(f"Error: {e}")

    print()
    print()

    # Example 3: Retry scenario (persist temp files on failure)
    print("Example 3: Retry scenario")
    print("-" * 50)

    temp_dir = None
    processed_images = None

    try:
        # First attempt - processing
        temp_dir, processed_images = process_images(image_paths)

        print(f"\nProcessing complete. Processed files in: {temp_dir.name}")

        # Simulate upload failure
        # upload_to_s3(processed_images)  # This might fail
        raise Exception("Simulated upload failure")

    except ProcessingError as e:
        print(f"Processing error: {e}")
        print("Cannot retry - processing failed.")

    except Exception as e:
        print(f"Upload error: {e}")
        print(f"\nTemp files preserved in: {temp_dir.name}")
        print("You can retry upload without reprocessing:")
        print(f"  - Temp files are still available")
        print(f"  - Use processed_images metadata for upload")
        print(f"  - Call temp_dir.cleanup() when done")

        # On retry, you would:
        # 1. Use the existing processed_images list
        # 2. Attempt upload again
        # 3. Call temp_dir.cleanup() on success

        # For this example, cleanup now
        if temp_dir:
            temp_dir.cleanup()
            print("\nTemp directory cleaned up.")

    print()
    print()

    # Example 4: Processing with warnings
    print("Example 4: Handling warnings")
    print("-" * 50)

    try:
        # Process with very small target size to trigger warnings
        temp_dir, processed_images = process_images(
            image_paths,
            target_size_kb=10  # Very small - will likely trigger warnings
        )

        print("\nProcessing results:")
        for proc_img in processed_images:
            if proc_img.warnings:
                print(f"\n{proc_img.original_path.name}:")
                print(f"  Quality: {proc_img.quality_used}")
                print(f"  Final size: {proc_img.final_size / 1024:.1f}KB")
                print("  Warnings:")
                for warning in proc_img.warnings:
                    print(f"    - {warning}")

        temp_dir.cleanup()

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    print("Image Processor Example")
    print("=" * 50)
    print()
    print("Note: This example requires actual image files.")
    print("Modify the image_paths list with real file paths to test.")
    print()

    # Uncomment to run examples (after setting real image paths):
    # main()

    print("Example code is ready. Update paths and uncomment main() to run.")

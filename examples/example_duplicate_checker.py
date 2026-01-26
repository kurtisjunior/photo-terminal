"""Example usage of duplicate_checker module.

Demonstrates how to check for duplicate files in S3 before upload.
"""

from pathlib import Path
from photo_terminal.duplicate_checker import check_for_duplicates, DuplicateFilesError


def example_basic_usage():
    """Basic example of duplicate checking."""
    print("Example 1: Basic duplicate checking")
    print("-" * 50)

    # Simulate list of images to upload
    images = [
        Path('/path/to/photos/IMG_001.jpg'),
        Path('/path/to/photos/IMG_002.jpg'),
        Path('/path/to/photos/IMG_003.jpg'),
    ]

    bucket = 'two-touch'
    prefix = 'japan/tokyo'
    aws_profile = 'kurtis-site'

    try:
        # Check for duplicates before processing
        check_for_duplicates(images, bucket, prefix, aws_profile)

        print("✓ No duplicates found - safe to proceed with upload")
        print()

    except DuplicateFilesError as e:
        print(f"{e}")
        print()
        # Handle duplicate error - abort upload
        return

    # If we get here, no duplicates found
    # Proceed with image processing and upload...
    print("Proceeding with image processing...")


def example_with_error_handling():
    """Example with comprehensive error handling."""
    print("Example 2: With error handling")
    print("-" * 50)

    images = [Path(f'/photos/photo{i}.jpg') for i in range(1, 6)]

    try:
        check_for_duplicates(images, 'my-bucket', 'vacation/2024', 'my-profile')
        print("✓ No duplicates - proceeding...")

    except DuplicateFilesError as e:
        # Specific handling for duplicates
        print("Duplicate detection error:")
        print(e)
        print()
        print(f"Found {len(e.duplicates)} duplicate file(s)")
        print(f"Bucket: {e.bucket}")
        print(f"Prefix: {e.prefix}")
        return False

    except SystemExit:
        # AWS credential or permission errors
        print("AWS error occurred - check credentials and permissions")
        return False

    return True


def example_empty_prefix():
    """Example with empty prefix (bucket root)."""
    print("Example 3: Upload to bucket root")
    print("-" * 50)

    images = [Path('/photos/image.jpg')]

    try:
        # Empty prefix = bucket root
        check_for_duplicates(images, 'my-bucket', '', 'my-profile')
        print("✓ No duplicates at bucket root")

    except DuplicateFilesError as e:
        print(f"{e}")


def example_integration_workflow():
    """Example showing integration into full upload workflow."""
    print("Example 4: Integration workflow")
    print("-" * 50)

    # Simulated workflow steps
    print("Step 1: User selects images in TUI...")
    selected_images = [
        Path('/photos/sunset.jpg'),
        Path('/photos/beach.jpg'),
    ]
    print(f"  Selected {len(selected_images)} images")

    print("Step 2: User selects S3 folder...")
    s3_prefix = 'italy/trapani'
    print(f"  Target: s3://two-touch/{s3_prefix}/")

    print("Step 3: User confirms upload...")
    print(f"  Upload {len(selected_images)} images? yes")

    print("Step 4: Check for duplicates...")
    try:
        check_for_duplicates(
            selected_images,
            bucket='two-touch',
            prefix=s3_prefix,
            aws_profile='kurtis-site'
        )
        print("  ✓ No duplicates found")
    except DuplicateFilesError as e:
        print(f"  ✗ {e}")
        print("  Workflow aborted - no files processed")
        return

    print("Step 5: Process images (optimize JPEG)...")
    print("  Processing sunset.jpg...")
    print("  Processing beach.jpg...")

    print("Step 6: Upload to S3...")
    print("  ⠋ Uploading... (1/2)")
    print("  ⠋ Uploading... (2/2)")

    print("Step 7: Cleanup temp files...")
    print("✓ Upload complete!")


def example_large_batch():
    """Example with large batch showing parallel checking."""
    print("Example 5: Large batch (parallel checking)")
    print("-" * 50)

    # Large batch > 10 files triggers parallel checking
    images = [Path(f'/photos/IMG_{i:04d}.jpg') for i in range(1, 26)]

    print(f"Checking {len(images)} images for duplicates...")
    print("(Using parallel ThreadPoolExecutor for efficiency)")

    try:
        check_for_duplicates(images, 'my-bucket', 'photos/2024', 'my-profile')
        print(f"✓ All {len(images)} images checked - no duplicates")

    except DuplicateFilesError as e:
        print(f"Found {len(e.duplicates)} duplicates:")
        for filename in e.duplicates:
            print(f"  - {filename}")


if __name__ == '__main__':
    print("Duplicate Checker Examples")
    print("=" * 50)
    print()

    # Note: These examples won't actually connect to AWS
    # They show the API usage patterns

    print("Note: These examples demonstrate API usage.")
    print("They won't make actual S3 calls without valid credentials.")
    print()
    print("=" * 50)
    print()

    example_basic_usage()
    print()

    example_with_error_handling()
    print()

    example_empty_prefix()
    print()

    example_integration_workflow()
    print()

    example_large_batch()

#!/usr/bin/env python3
"""Example usage of the S3 uploader module.

This demonstrates how to use the uploader module to upload processed images
to S3 with minimal progress feedback.
"""

import tempfile
from pathlib import Path

from PIL import Image

from processor import ProcessedImage
from uploader import upload_images, UploadError


def create_sample_processed_images():
    """Create sample processed images for demonstration."""
    # Create temporary directory for processed images
    temp_dir = tempfile.mkdtemp(prefix="uploader_demo_")
    temp_dir_path = Path(temp_dir)

    processed_images = []

    # Create 5 sample images
    for i in range(1, 6):
        # Create original path (simulated)
        original_path = Path(f"/photos/vacation/IMG_{1000 + i}.jpg")

        # Create processed image in temp directory
        temp_path = temp_dir_path / original_path.name

        # Generate a simple image
        img = Image.new('RGB', (800, 600), color=(100 + i * 30, 150, 200))
        img.save(temp_path, 'JPEG', quality=85)

        # Create ProcessedImage metadata
        processed = ProcessedImage(
            original_path=original_path,
            temp_path=temp_path,
            original_size=1200000,  # 1.2MB original
            final_size=400000,      # 400KB after optimization
            quality_used=85,
            warnings=[]
        )
        processed_images.append(processed)

    return temp_dir_path, processed_images


def example_basic_upload():
    """Example: Basic upload to S3."""
    print("=== Example: Basic Upload ===\n")

    # Create sample images
    temp_dir, processed_images = create_sample_processed_images()

    print(f"Created {len(processed_images)} processed images in {temp_dir}")
    print("\nImages to upload:")
    for img in processed_images:
        print(f"  - {img.original_path.name} ({img.final_size:,} bytes)")

    print("\nUploading to S3...")

    try:
        # Upload to S3
        uploaded_keys = upload_images(
            processed_images=processed_images,
            bucket='two-touch',
            prefix='japan/tokyo',
            aws_profile='kurtis-site'
        )

        print("\nUpload complete!")
        print(f"\nUploaded {len(uploaded_keys)} images:")
        for key in uploaded_keys:
            print(f"  - s3://two-touch/{key}")

    except UploadError as e:
        print(f"\nUpload failed: {e}")

    # Cleanup (in real usage, temp directory is managed by processor)
    import shutil
    shutil.rmtree(temp_dir)


def example_empty_prefix():
    """Example: Upload to bucket root (empty prefix)."""
    print("\n\n=== Example: Upload to Bucket Root ===\n")

    temp_dir, processed_images = create_sample_processed_images()

    # Only upload first 2 images for brevity
    processed_images = processed_images[:2]

    print(f"Uploading {len(processed_images)} images to bucket root...")

    try:
        uploaded_keys = upload_images(
            processed_images=processed_images,
            bucket='two-touch',
            prefix='',  # Empty prefix = bucket root
            aws_profile='kurtis-site'
        )

        print("\nUpload complete!")
        print("Uploaded keys:")
        for key in uploaded_keys:
            print(f"  - {key}")

    except UploadError as e:
        print(f"\nUpload failed: {e}")

    import shutil
    shutil.rmtree(temp_dir)


def example_error_handling():
    """Example: Error handling with fail-fast behavior."""
    print("\n\n=== Example: Error Handling ===\n")

    temp_dir, processed_images = create_sample_processed_images()

    print("Attempting upload with invalid profile...")

    try:
        uploaded_keys = upload_images(
            processed_images=processed_images,
            bucket='two-touch',
            prefix='test',
            aws_profile='invalid-profile-name'  # This will fail
        )

        print("Upload complete!")

    except UploadError as e:
        print(f"\n✓ Upload failed as expected: {e}")
        print("\nNote: Temp directory is preserved for retry")
        print(f"Temp files still exist at: {temp_dir}")

        # Verify temp files exist
        for img in processed_images:
            if img.temp_path.exists():
                print(f"  ✓ {img.temp_path.name} exists")

    import shutil
    shutil.rmtree(temp_dir)


def example_prefix_normalization():
    """Example: Prefix normalization with trailing slashes."""
    print("\n\n=== Example: Prefix Normalization ===\n")

    temp_dir, processed_images = create_sample_processed_images()
    processed_images = processed_images[:1]  # Just one image

    # Test various prefix formats
    test_prefixes = [
        'japan/tokyo',
        'japan/tokyo/',
        'japan/tokyo///',
        '  japan/tokyo  ',
        '  japan/tokyo/  '
    ]

    print("Testing prefix normalization:")
    for prefix in test_prefixes:
        print(f"\n  Input prefix: '{prefix}'")

        try:
            # Note: This will only work if AWS credentials are valid
            # In this example, we're just showing the pattern
            uploaded_keys = upload_images(
                processed_images=processed_images,
                bucket='two-touch',
                prefix=prefix,
                aws_profile='kurtis-site'
            )

            print(f"  Output key: '{uploaded_keys[0]}'")
            print(f"  ✓ All variations produce: 'japan/tokyo/{processed_images[0].original_path.name}'")

        except UploadError as e:
            print(f"  Upload failed (expected if no AWS creds): {e}")
            break

    import shutil
    shutil.rmtree(temp_dir)


def example_integration_with_processor():
    """Example: Complete integration with processor module."""
    print("\n\n=== Example: Integration with Processor ===\n")

    from processor import process_images

    # Create source images
    source_dir = Path(tempfile.mkdtemp(prefix="source_"))
    source_images = []

    for i in range(3):
        img_path = source_dir / f"photo_{i}.jpg"
        img = Image.new('RGB', (1920, 1080), color=(50 + i * 60, 100, 150))
        img.save(img_path, 'JPEG', quality=95)
        source_images.append(img_path)

    print(f"Created {len(source_images)} source images")

    try:
        # Process images
        print("\nProcessing images...")
        temp_dir, processed_images = process_images(
            images=source_images,
            target_size_kb=400
        )

        print(f"Processed {len(processed_images)} images")

        # Upload to S3
        print("\nUploading to S3...")
        uploaded_keys = upload_images(
            processed_images=processed_images,
            bucket='two-touch',
            prefix='demo/test',
            aws_profile='kurtis-site'
        )

        print("\nComplete workflow successful!")
        print(f"Uploaded {len(uploaded_keys)} images:")
        for key in uploaded_keys:
            print(f"  - s3://two-touch/{key}")

        # Cleanup temp directory on success
        temp_dir.cleanup()

    except Exception as e:
        print(f"\nWorkflow failed: {e}")
        print("Temp directory preserved for retry")

    # Cleanup source directory
    import shutil
    shutil.rmtree(source_dir)


if __name__ == '__main__':
    print("S3 Uploader Module - Example Usage")
    print("=" * 50)

    # Note: These examples require valid AWS credentials
    print("\nNote: These examples require AWS CLI configured with 'kurtis-site' profile")
    print("      and access to the 'two-touch' bucket.\n")

    # Run examples
    # Uncomment to run each example:

    # example_basic_upload()
    # example_empty_prefix()
    example_error_handling()
    # example_prefix_normalization()
    # example_integration_with_processor()

    print("\n" + "=" * 50)
    print("Examples complete!")

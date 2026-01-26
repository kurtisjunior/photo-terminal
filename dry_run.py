"""Dry-run mode for photo upload showing size changes without uploading.

Displays what would happen without actually uploading to S3. Shows original
and processed sizes for each selected image, processes images to get accurate
size info, but doesn't perform S3 operations. Cleans up temp files after
displaying information.
"""

from pathlib import Path
from typing import List
import sys

from processor import process_images, ProcessedImage
from uploader import _normalize_prefix, _construct_s3_key


def dry_run_upload(
    images: List[Path],
    bucket: str,
    prefix: str,
    target_size_kb: int,
    aws_profile: str
) -> None:
    """Show what would be uploaded without actually uploading.

    Processes images to get accurate size information, displays a comprehensive
    dry-run report showing original → processed sizes, target S3 location,
    and S3 keys that would be created. Cleans up temp files after displaying.

    Args:
        images: List of image paths to process
        bucket: S3 bucket name
        prefix: S3 prefix/folder path (may be empty string for root)
        target_size_kb: Target file size in kilobytes
        aws_profile: AWS CLI profile name (not used in dry-run)

    Raises:
        SystemExit: Always exits after displaying dry-run report
    """
    # Display dry-run header
    _print_header(bucket, prefix, target_size_kb)

    # Process images to get accurate size information
    print("Processing images to calculate sizes...")
    print()

    try:
        temp_dir, processed_images = process_images(images, target_size_kb)
    except Exception as e:
        print(f"Error during image processing: {e}")
        raise SystemExit(1)

    try:
        # Display file-by-file report
        _print_files_report(processed_images)

        # Display summary statistics
        _print_summary(processed_images)

        # Display S3 keys that would be created
        _print_s3_keys(processed_images, prefix)

        print()
        print("DRY RUN COMPLETE - No files were uploaded")
        print()

    finally:
        # Always cleanup temp files
        temp_dir.cleanup()

    # Exit after dry-run
    raise SystemExit(0)


def _print_header(bucket: str, prefix: str, target_size_kb: int) -> None:
    """Print dry-run mode header.

    Args:
        bucket: S3 bucket name
        prefix: S3 prefix/folder path
        target_size_kb: Target file size in kilobytes
    """
    print()
    print("DRY RUN MODE - No files will be uploaded")
    print("═" * 50)
    print()

    # Build S3 target string
    if prefix:
        s3_target = f"s3://{bucket}/{prefix}/"
    else:
        s3_target = f"s3://{bucket}/"

    print(f"Target location: {s3_target}")
    print(f"Target size:     {target_size_kb} KB")
    print()


def _print_files_report(processed_images: List[ProcessedImage]) -> None:
    """Print file-by-file processing report.

    Args:
        processed_images: List of ProcessedImage objects from processor
    """
    print("Files to process:")
    print()

    for proc_img in processed_images:
        # Format file sizes
        orig_mb = proc_img.original_size / (1024 * 1024)
        final_kb = proc_img.final_size / 1024

        # Calculate reduction percentage
        reduction = (1 - (proc_img.final_size / proc_img.original_size)) * 100

        # Print file information
        print(f"File: {proc_img.original_path.name}")
        print(f"  Original:  {orig_mb:.1f} MB")
        print(f"  Processed: {final_kb:.0f} KB")
        print(f"  Reduction: {reduction:.1f}%")

        # Display warnings if any
        if proc_img.warnings:
            for warning in proc_img.warnings:
                print(f"  Warning: {warning}")

        print()


def _print_summary(processed_images: List[ProcessedImage]) -> None:
    """Print summary statistics.

    Args:
        processed_images: List of ProcessedImage objects from processor
    """
    # Calculate totals
    total_files = len(processed_images)
    total_original = sum(img.original_size for img in processed_images)
    total_processed = sum(img.final_size for img in processed_images)
    total_reduction = (1 - (total_processed / total_original)) * 100 if total_original > 0 else 0

    # Format sizes
    orig_mb = total_original / (1024 * 1024)
    proc_mb = total_processed / (1024 * 1024)

    # Print summary
    print("SUMMARY")
    print("─" * 50)
    print(f"Total files:      {total_files}")
    print(f"Original size:    {orig_mb:.1f} MB")
    print(f"Processed size:   {proc_mb:.1f} MB")
    print(f"Total reduction:  {total_reduction:.1f}%")
    print()


def _print_s3_keys(processed_images: List[ProcessedImage], prefix: str) -> None:
    """Print S3 keys that would be created.

    Args:
        processed_images: List of ProcessedImage objects from processor
        prefix: S3 prefix/folder path
    """
    # Normalize prefix
    normalized_prefix = _normalize_prefix(prefix)

    print("S3 keys that would be created:")

    for proc_img in processed_images:
        # Construct S3 key
        s3_key = _construct_s3_key(normalized_prefix, proc_img.original_path.name)
        print(f"  - {s3_key}")

    print()

"""Completion summary display for successful uploads.

Shows upload completion information with statistics, file list, and S3 locations.
Minimal output aligned with fail-fast philosophy.
"""

from typing import List

from photo_terminal.processor import ProcessedImage


def show_completion_summary(
    processed_images: List[ProcessedImage],
    uploaded_keys: List[str],
    bucket: str,
    prefix: str
) -> None:
    """Display upload completion summary with statistics and file list.

    Shows:
    - Count of uploaded files
    - Original and processed total sizes
    - Total size savings (bytes and percentage)
    - S3 bucket and prefix location
    - List of uploaded files with their S3 keys
    - S3 URLs for uploaded files

    Args:
        processed_images: List of ProcessedImage objects from processor
        uploaded_keys: List of S3 keys for uploaded files (from uploader)
        bucket: S3 bucket name
        prefix: S3 prefix/folder path (may be empty string for root)

    Raises:
        ValueError: If processed_images and uploaded_keys lengths don't match
    """
    # Validate inputs match
    if len(processed_images) != len(uploaded_keys):
        raise ValueError(
            f"Mismatch: {len(processed_images)} processed images "
            f"but {len(uploaded_keys)} uploaded keys"
        )

    # Calculate statistics
    total_files = len(processed_images)
    total_original = sum(img.original_size for img in processed_images)
    total_processed = sum(img.final_size for img in processed_images)
    total_savings = total_original - total_processed
    savings_percent = (total_savings / total_original * 100) if total_original > 0 else 0

    # Format sizes in appropriate units
    orig_size_str = _format_size(total_original)
    proc_size_str = _format_size(total_processed)
    savings_str = _format_size(total_savings)

    # Build S3 location string
    if prefix:
        s3_location = f"s3://{bucket}/{prefix}/"
    else:
        s3_location = f"s3://{bucket}/"

    # Print completion header
    print()
    print("UPLOAD COMPLETE")
    print("═" * 50)
    print()

    # Print statistics
    print(f"Files uploaded:    {total_files}")
    print(f"Original size:     {orig_size_str}")
    print(f"Processed size:    {proc_size_str}")
    print(f"Total savings:     {savings_str} ({savings_percent:.1f}%)")
    print()

    # Print S3 location
    print(f"Location: {s3_location}")
    print()

    # Print uploaded files with S3 keys
    print("Uploaded files:")
    for proc_img, s3_key in zip(processed_images, uploaded_keys):
        filename = proc_img.original_path.name
        print(f"  - {filename} → {s3_key}")

    print()


def _format_size(size_bytes: int) -> str:
    """Format file size in human-readable format.

    Args:
        size_bytes: Size in bytes

    Returns:
        Formatted string (e.g., "5.8 MB", "450 KB", "1.2 GB")
    """
    # Convert to appropriate unit
    if size_bytes >= 1024 * 1024 * 1024:  # >= 1 GB
        size_value = size_bytes / (1024 * 1024 * 1024)
        return f"{size_value:.1f} GB"
    elif size_bytes >= 1024 * 1024:  # >= 1 MB
        size_value = size_bytes / (1024 * 1024)
        return f"{size_value:.1f} MB"
    elif size_bytes >= 1024:  # >= 1 KB
        size_value = size_bytes / 1024
        return f"{size_value:.0f} KB"
    else:  # < 1 KB
        return f"{size_bytes} bytes"

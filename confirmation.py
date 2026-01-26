"""Selection confirmation for photo upload.

Provides user confirmation before proceeding with image processing and upload.
Follows fail-fast philosophy - exits immediately on user cancellation.
"""

from pathlib import Path
from typing import List


def confirm_upload(images: List[Path], bucket: str, prefix: str) -> bool:
    """Display upload summary and prompt for user confirmation.

    Args:
        images: List of image paths to upload
        bucket: S3 bucket name
        prefix: S3 prefix/folder path (may be empty string for root)

    Returns:
        True if user confirms, never returns False (exits instead)

    Raises:
        SystemExit(1): If user cancels the upload
    """
    # Build S3 target string
    if prefix:
        s3_target = f"s3://{bucket}/{prefix}"
    else:
        s3_target = f"s3://{bucket}/"

    # Display summary header
    print("Upload Confirmation")
    print("=" * 50)
    print()
    print(f"Images to upload: {len(images)}")
    print(f"Target location:  {s3_target}")
    print()

    # Display file list (with truncation if many files)
    MAX_DISPLAY = 10
    if len(images) <= MAX_DISPLAY:
        print("Files:")
        for img in images:
            print(f"  - {img.name}")
    else:
        print(f"Files (showing first {MAX_DISPLAY}):")
        for img in images[:MAX_DISPLAY]:
            print(f"  - {img.name}")
        remaining = len(images) - MAX_DISPLAY
        print(f"  ... and {remaining} more")

    print()

    # Prompt for confirmation
    while True:
        try:
            response = input(f"Upload {len(images)} image(s) to {s3_target}? [y/n]: ").strip().lower()
        except EOFError:
            # Handle Ctrl+D as cancellation
            print()
            print("Upload cancelled.")
            raise SystemExit(1)

        if response in ('y', 'yes'):
            print()
            return True
        elif response in ('n', 'no'):
            print()
            print("Upload cancelled.")
            raise SystemExit(1)
        else:
            print("Invalid input. Please enter 'y' or 'n'.")

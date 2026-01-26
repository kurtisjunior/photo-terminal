"""S3 upload module with minimal progress feedback.

Handles batch uploads of processed images to S3 with fail-fast error handling
and simple spinner + count progress feedback. No retry logic - fails immediately
on any upload error.
"""

import sys
import time
from typing import List

import boto3
from botocore.exceptions import ClientError, BotoCoreError

from photo_terminal.processor import ProcessedImage


# Spinner animation frames
SPINNER_FRAMES = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']


class UploadError(Exception):
    """Raised when S3 upload fails."""
    pass


def upload_images(
    processed_images: List[ProcessedImage],
    bucket: str,
    prefix: str,
    aws_profile: str
) -> List[str]:
    """Upload processed images to S3 with minimal progress feedback.

    Uploads each processed image from temp directory to S3 bucket with the
    specified prefix. Shows a simple spinner with count during upload.
    Fails immediately on any upload error without retry.

    Args:
        processed_images: List of ProcessedImage objects from processor
        bucket: S3 bucket name
        prefix: S3 key prefix (folder path)
        aws_profile: AWS CLI profile name to use

    Returns:
        List of S3 keys for successfully uploaded images

    Raises:
        ValueError: If processed_images list is empty
        UploadError: If any upload fails (includes AWS error details)
    """
    # Fail-fast: Empty images list
    if not processed_images:
        raise ValueError("Processed images list cannot be empty")

    # Normalize prefix (handle empty string, trailing slashes)
    normalized_prefix = _normalize_prefix(prefix)

    # Create boto3 S3 client with specified profile
    try:
        session = boto3.Session(profile_name=aws_profile)
        s3_client = session.client('s3')
    except Exception as e:
        raise UploadError(
            f"Failed to create AWS session with profile '{aws_profile}': {e}"
        ) from e

    # Upload each image with progress feedback
    uploaded_keys = []
    total_count = len(processed_images)

    try:
        for idx, processed_img in enumerate(processed_images, start=1):
            # Construct S3 key
            s3_key = _construct_s3_key(normalized_prefix, processed_img.original_path.name)

            # Show progress with spinner
            _show_progress(idx, total_count)

            # Upload to S3
            try:
                s3_client.upload_file(
                    Filename=str(processed_img.temp_path),
                    Bucket=bucket,
                    Key=s3_key
                )
                uploaded_keys.append(s3_key)

            except ClientError as e:
                # Clear progress line before showing error
                _clear_progress()

                # Extract error details
                error_code = e.response.get('Error', {}).get('Code', 'Unknown')
                error_msg = e.response.get('Error', {}).get('Message', str(e))

                # Fail-fast with detailed error message
                raise UploadError(
                    f"Failed to upload '{processed_img.original_path.name}' "
                    f"to s3://{bucket}/{s3_key}\n"
                    f"AWS Error [{error_code}]: {error_msg}"
                ) from e

            except (BotoCoreError, Exception) as e:
                # Clear progress line before showing error
                _clear_progress()

                # Fail-fast on any other error
                raise UploadError(
                    f"Failed to upload '{processed_img.original_path.name}' "
                    f"to s3://{bucket}/{s3_key}\n"
                    f"Error: {e}"
                ) from e

        # Clear progress line after completion
        _clear_progress()

        return uploaded_keys

    except UploadError:
        # Re-raise UploadError as-is
        raise


def _normalize_prefix(prefix: str) -> str:
    """Normalize S3 prefix by removing trailing slashes.

    Args:
        prefix: S3 key prefix (may be empty, have trailing slash, etc.)

    Returns:
        Normalized prefix (no trailing slash, empty string if no prefix)

    Examples:
        "" -> ""
        "japan" -> "japan"
        "japan/" -> "japan"
        "japan/tokyo" -> "japan/tokyo"
        "japan/tokyo/" -> "japan/tokyo"
    """
    # Strip whitespace
    normalized = prefix.strip()

    # Remove trailing slashes
    normalized = normalized.rstrip('/')

    return normalized


def _construct_s3_key(prefix: str, filename: str) -> str:
    """Construct S3 key from prefix and filename.

    Args:
        prefix: Normalized S3 prefix (no trailing slash)
        filename: Original filename

    Returns:
        Full S3 key

    Examples:
        ("japan/tokyo", "image.jpg") -> "japan/tokyo/image.jpg"
        ("", "image.jpg") -> "image.jpg"
        ("japan", "image.jpg") -> "japan/image.jpg"
    """
    if prefix:
        return f"{prefix}/{filename}"
    else:
        return filename


def _show_progress(current: int, total: int) -> None:
    """Show spinner with upload count on same line.

    Args:
        current: Current upload number (1-indexed)
        total: Total number of uploads
    """
    # Use frame based on current count for smooth animation
    frame_idx = (current - 1) % len(SPINNER_FRAMES)
    spinner = SPINNER_FRAMES[frame_idx]

    # Write progress to stdout with carriage return
    sys.stdout.write(f"\r{spinner} Uploading... ({current}/{total})")
    sys.stdout.flush()


def _clear_progress() -> None:
    """Clear the progress line."""
    # ANSI escape codes: clear line and return to start
    sys.stdout.write("\033[2K\r")
    sys.stdout.flush()

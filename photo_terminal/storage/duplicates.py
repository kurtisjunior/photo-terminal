"""Duplicate detection for S3 uploads.

Checks if filenames already exist in target S3 prefix before upload.
Uses boto3 HeadObject for fail-fast duplicate detection.

Every failure here is raised as a typed error. The credential and permission
branches used to print seven lines of guidance and raise ``SystemExit(1)`` from
inside a head-object loop; the guidance is now the exception's message and the
exit code is the caller's decision.

The ``ThreadPoolExecutor`` below is deliberately not
:class:`~photo_terminal.terminal.background.BackgroundWorker`. That class
exists to wake a ``select``-based keystroke loop through a self-pipe; this is a
blocking parallel map with no input loop to wake, and storage sits below
``terminal`` in the dependency contract besides.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import ClientError

from photo_terminal.domain.errors import DuplicateKeyError, S3AccessError

__all__ = ["DuplicateKeyError", "S3AccessError", "check_for_duplicates"]


def check_for_duplicates(
    images: list[Path], bucket: str, prefix: str, aws_profile: str | None
) -> None:
    """Check if any image filenames already exist in S3 target prefix.

    Pre-checks ALL selected filenames before processing starts using HeadObject.
    Fails immediately with list of conflicting files if any duplicates found.

    Args:
        images: List of image paths to check
        bucket: S3 bucket name
        prefix: S3 prefix (folder path). Empty string for bucket root.
        aws_profile: AWS CLI profile name to use, or None to let boto3 resolve
            credentials from the environment (e.g. AWS_ACCESS_KEY_ID)

    Returns:
        None if no duplicates found (all clear to proceed)

    Raises:
        DuplicateKeyError: If any duplicate files found in S3
        S3AccessError: On AWS credential/permission errors or network failures
    """
    if not images:
        return

    # Initialize S3 client with profile (or from environment)
    try:
        session = boto3.Session(profile_name=aws_profile) if aws_profile else boto3.Session()
        s3_client = session.client("s3")
    except Exception as e:
        if aws_profile:
            raise S3AccessError(
                f"Failed to initialize AWS session with profile '{aws_profile}'\n"
                f"Details: {e}\n"
                f"\nMake sure AWS CLI is configured with: aws configure --profile {aws_profile}"
            ) from None
        raise S3AccessError(
            f"Failed to initialize AWS session\n"
            f"Details: {e}\n"
            "\nSet AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in .env "
            "(see .env.example), or configure an AWS CLI profile with: "
            "aws configure --profile <profile-name>"
        ) from None

    # Normalize prefix (ensure no leading slash, add trailing slash if not empty)
    if prefix:
        prefix = prefix.strip("/")
        if prefix:
            prefix = prefix + "/"
    else:
        prefix = ""

    # Check for duplicates (use parallel checks if many files)
    duplicates = []

    if len(images) > 10:
        # Parallel checks for large batches
        duplicates = _check_parallel(s3_client, images, bucket, prefix)
    else:
        # Sequential checks for small batches
        duplicates = _check_sequential(s3_client, images, bucket, prefix)

    # Raise error if any duplicates found
    if duplicates:
        raise DuplicateKeyError(duplicates, bucket, prefix)


def _check_sequential(s3_client: Any, images: list[Path], bucket: str, prefix: str) -> list[str]:
    """Check for duplicates sequentially.

    Args:
        s3_client: Boto3 S3 client. Untyped because boto3 has no stubs here;
            the port in :mod:`photo_terminal.storage.ports` is what callers see
        images: List of image paths to check
        bucket: S3 bucket name
        prefix: S3 prefix with trailing slash (or empty string)

    Returns:
        List of duplicate filenames found
    """
    duplicates = []

    for image_path in images:
        filename = image_path.name
        s3_key = prefix + filename

        if _key_exists(s3_client, bucket, s3_key):
            duplicates.append(filename)

    return duplicates


def _check_parallel(s3_client: Any, images: list[Path], bucket: str, prefix: str) -> list[str]:
    """Check for duplicates in parallel using ThreadPoolExecutor.

    Args:
        s3_client: Boto3 S3 client
        images: List of image paths to check
        bucket: S3 bucket name
        prefix: S3 prefix with trailing slash (or empty string)

    Returns:
        List of duplicate filenames found

    Raises:
        S3AccessError: On AWS errors, surfaced from the first worker to hit one.
            The sequential path has always propagated these; the parallel path
            used to swallow them, which turned a permission failure on a batch
            of more than ten files into "no duplicates found".
    """
    duplicates = []

    # Use ThreadPoolExecutor for parallel HEAD requests
    with ThreadPoolExecutor(max_workers=10) as executor:
        # Submit all checks
        future_to_filename = {}
        for image_path in images:
            filename = image_path.name
            s3_key = prefix + filename
            future = executor.submit(_key_exists, s3_client, bucket, s3_key)
            future_to_filename[future] = filename

        # Collect results as they complete
        for future in as_completed(future_to_filename):
            filename = future_to_filename[future]
            if future.result():
                duplicates.append(filename)

    return duplicates


def _key_exists(s3_client: Any, bucket: str, key: str) -> bool:
    """Check if S3 key exists using HeadObject.

    Args:
        s3_client: Boto3 S3 client
        bucket: S3 bucket name
        key: S3 key to check

    Returns:
        True if key exists, False if not found

    Raises:
        S3AccessError: On AWS errors (permissions, network, etc.)
    """
    try:
        s3_client.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")

        # 404 means key doesn't exist - this is expected and good
        if error_code == "404":
            return False

        # 403 means permission denied
        if error_code == "403":
            raise S3AccessError(
                f"Permission denied accessing S3 bucket '{bucket}'\n"
                f"Details: {e}\n"
                "\nMake sure your AWS credentials have s3:GetObject permission"
            ) from None

        # Other errors are unexpected
        raise S3AccessError(f"Failed to check S3 key: {key}\nDetails: {e}") from None
    except Exception as e:
        # Network or other errors
        raise S3AccessError(f"Failed to connect to S3\nDetails: {e}") from None

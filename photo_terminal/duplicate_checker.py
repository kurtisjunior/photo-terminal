"""Duplicate detection for S3 uploads.

Checks if filenames already exist in target S3 prefix before upload.
Uses boto3 HeadObject for fail-fast duplicate detection.
"""

from pathlib import Path
from typing import List
from concurrent.futures import ThreadPoolExecutor, as_completed

import boto3
from botocore.exceptions import ClientError


class DuplicateFilesError(Exception):
    """Raised when duplicate files are found in S3 target prefix."""

    def __init__(self, duplicates: List[str], bucket: str, prefix: str):
        """Initialize with list of duplicate filenames.

        Args:
            duplicates: List of filenames that already exist in S3
            bucket: S3 bucket name
            prefix: S3 prefix where duplicates were found
        """
        self.duplicates = duplicates
        self.bucket = bucket
        self.prefix = prefix

        # Format error message
        files_list = '\n  - '.join(duplicates)
        s3_path = f"s3://{bucket}/{prefix}" if prefix else f"s3://{bucket}/"

        message = (
            f"Error: The following files already exist in {s3_path}:\n"
            f"  - {files_list}\n\n"
            f"Aborting to prevent overwrites. No files were uploaded."
        )
        super().__init__(message)


def check_for_duplicates(
    images: List[Path],
    bucket: str,
    prefix: str,
    aws_profile: str
) -> None:
    """Check if any image filenames already exist in S3 target prefix.

    Pre-checks ALL selected filenames before processing starts using HeadObject.
    Fails immediately with list of conflicting files if any duplicates found.

    Args:
        images: List of image paths to check
        bucket: S3 bucket name
        prefix: S3 prefix (folder path). Empty string for bucket root.
        aws_profile: AWS CLI profile name to use

    Returns:
        None if no duplicates found (all clear to proceed)

    Raises:
        DuplicateFilesError: If any duplicate files found in S3
        SystemExit: On AWS credential/permission errors or network failures
    """
    if not images:
        return

    # Initialize S3 client with profile
    try:
        session = boto3.Session(profile_name=aws_profile)
        s3_client = session.client('s3')
    except Exception as e:
        print(f"Error: Failed to initialize AWS session with profile '{aws_profile}'")
        print(f"Details: {e}")
        print(f"\nMake sure AWS CLI is configured with: aws configure --profile {aws_profile}")
        raise SystemExit(1)

    # Normalize prefix (ensure no leading slash, add trailing slash if not empty)
    if prefix:
        prefix = prefix.strip('/')
        if prefix:
            prefix = prefix + '/'
    else:
        prefix = ''

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
        raise DuplicateFilesError(duplicates, bucket, prefix)


def _check_sequential(
    s3_client,
    images: List[Path],
    bucket: str,
    prefix: str
) -> List[str]:
    """Check for duplicates sequentially.

    Args:
        s3_client: Boto3 S3 client
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


def _check_parallel(
    s3_client,
    images: List[Path],
    bucket: str,
    prefix: str
) -> List[str]:
    """Check for duplicates in parallel using ThreadPoolExecutor.

    Args:
        s3_client: Boto3 S3 client
        images: List of image paths to check
        bucket: S3 bucket name
        prefix: S3 prefix with trailing slash (or empty string)

    Returns:
        List of duplicate filenames found
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
            try:
                if future.result():
                    duplicates.append(filename)
            except Exception:
                # _key_exists handles errors internally
                # This should not happen, but catch just in case
                pass

    return duplicates


def _key_exists(s3_client, bucket: str, key: str) -> bool:
    """Check if S3 key exists using HeadObject.

    Args:
        s3_client: Boto3 S3 client
        bucket: S3 bucket name
        key: S3 key to check

    Returns:
        True if key exists, False if not found

    Raises:
        SystemExit: On AWS errors (permissions, network, etc.)
    """
    try:
        s3_client.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', '')

        # 404 means key doesn't exist - this is expected and good
        if error_code == '404':
            return False

        # 403 means permission denied
        if error_code == '403':
            print(f"Error: Permission denied accessing S3 bucket '{bucket}'")
            print(f"Details: {e}")
            print(f"\nMake sure your AWS credentials have s3:GetObject permission")
            raise SystemExit(1)

        # Other errors are unexpected
        print(f"Error: Failed to check S3 key: {key}")
        print(f"Details: {e}")
        raise SystemExit(1)
    except Exception as e:
        # Network or other errors
        print(f"Error: Failed to connect to S3")
        print(f"Details: {e}")
        raise SystemExit(1)

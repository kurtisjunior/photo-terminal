"""S3 access: credentials, prefix listing, and the wiring for the browser screen.

What is left here is infrastructure. The screen half moved to
:mod:`photo_terminal.terminal.screens.s3_browse`, which takes a
:class:`~photo_terminal.terminal.screens.s3_browse.FolderLister` port and makes
no AWS calls of its own; this module provides the boto3 implementation of that
port and composes the two. (Phase 6 moves the whole file under ``storage/``.)
"""

import boto3
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    EndpointConnectionError,
    NoCredentialsError,
    ProfileNotFound,
)

from photo_terminal.terminal.screens.s3_browse import S3FolderBrowser


class S3AccessError(Exception):
    """Raised when S3 access validation fails."""

    pass


def validate_s3_access(bucket: str, aws_profile: str | None) -> None:
    """Validate S3 access early to fail-fast on credential/permission issues.

    Args:
        bucket: S3 bucket name
        aws_profile: AWS profile name, or None to let boto3 resolve credentials
            from the environment (e.g. AWS_ACCESS_KEY_ID)

    Raises:
        S3AccessError: If S3 access fails with detailed error message
    """
    try:
        session = boto3.Session(profile_name=aws_profile) if aws_profile else boto3.Session()
        s3_client = session.client("s3")

        # Test ListBucket permission with minimal request
        s3_client.list_objects_v2(Bucket=bucket, MaxKeys=1)

    except ProfileNotFound as e:
        raise S3AccessError(
            f"AWS profile '{aws_profile}' not found.\n\n"
            f"Recommended: create a .env file with AWS_ACCESS_KEY_ID and\n"
            f"AWS_SECRET_ACCESS_KEY (see .env.example) instead of using a profile.\n\n"
            f"Or configure AWS CLI with:\n"
            f"  aws configure --profile {aws_profile}\n\n"
            f"Or check your ~/.aws/credentials file."
        ) from e

    except NoCredentialsError as e:
        raise S3AccessError(
            "AWS credentials not found.\n\n"
            "Recommended: create a .env file in the project root with:\n"
            "  AWS_ACCESS_KEY_ID=...\n"
            "  AWS_SECRET_ACCESS_KEY=...\n"
            "(see .env.example; direnv loads it automatically).\n\n"
            "Or configure AWS CLI with:\n"
            "  aws configure --profile <profile-name>"
        ) from e

    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")

        if error_code == "NoSuchBucket":
            raise S3AccessError(
                f"S3 bucket '{bucket}' does not exist.\n\n"
                f"Verify the bucket name in your configuration."
            ) from e

        elif error_code == "AccessDenied" or error_code == "Forbidden":
            raise S3AccessError(
                f"Access denied to S3 bucket '{bucket}'.\n\n"
                f"Verify that:\n"
                f"  1. AWS profile '{aws_profile}' has ListBucket permission\n"
                f"  2. Bucket policy allows your IAM user/role access\n\n"
                f"Error: {e.response.get('Error', {}).get('Message', str(e))}"
            ) from e

        else:
            raise S3AccessError(
                f"AWS error accessing bucket '{bucket}':\n"
                f"Error code: {error_code}\n"
                f"Message: {e.response.get('Error', {}).get('Message', str(e))}"
            ) from e

    except EndpointConnectionError as e:
        raise S3AccessError(
            "Network error: Could not connect to AWS.\n\n"
            "Check your internet connection and try again.\n\n"
            f"Details: {e}"
        ) from e

    except BotoCoreError as e:
        raise S3AccessError(
            f"AWS SDK error: {e}\n\nThis may be a configuration issue. Check your AWS setup."
        ) from e

    except Exception as e:
        raise S3AccessError(
            f"Unexpected error accessing S3: {e}\n\nPlease check your AWS configuration."
        ) from e


def list_s3_folders(bucket: str, aws_profile: str | None, prefix: str = "") -> list[str]:
    """List folders (CommonPrefixes) at a given S3 prefix level.

    Args:
        bucket: S3 bucket name
        aws_profile: AWS profile name, or None to let boto3 resolve credentials
            from the environment (e.g. AWS_ACCESS_KEY_ID)
        prefix: S3 prefix to list (e.g., "japan/" or "")

    Returns:
        List of folder names (without full prefix path)

    Raises:
        S3AccessError: If S3 access fails
    """
    try:
        session = boto3.Session(profile_name=aws_profile) if aws_profile else boto3.Session()
        s3_client = session.client("s3")

        # Use delimiter='/' to get folder-like structure
        response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix, Delimiter="/")

        # Extract CommonPrefixes (folders)
        folders = []
        for common_prefix in response.get("CommonPrefixes", []):
            full_prefix = common_prefix["Prefix"]

            # Extract just the folder name (last segment before trailing /)
            # e.g., "japan/tokyo/" -> "tokyo"
            folder_name = full_prefix.rstrip("/").split("/")[-1]
            folders.append(folder_name)

        return sorted(folders)

    except Exception as e:
        raise S3AccessError(f"Error listing S3 folders: {e}") from e


class S3FolderLister:
    """The boto3 implementation of the browser's folder-listing port."""

    def __init__(self, bucket: str, aws_profile: str | None):
        self.bucket = bucket
        self.aws_profile = aws_profile

    def list_folders(self, prefix: str) -> list[str]:
        """The folder names directly under ``prefix``, sorted."""
        return list_s3_folders(self.bucket, self.aws_profile, prefix)


def browse_s3_folders(
    bucket: str, aws_profile: str | None, initial_prefix: str | None = None
) -> str:
    """Browse S3 folders and select upload target.

    If initial_prefix is provided, skip browser and return it directly.
    Otherwise, show interactive folder browser.

    Args:
        bucket: S3 bucket name
        aws_profile: AWS profile name, or None to let boto3 resolve credentials
            from the environment (e.g. AWS_ACCESS_KEY_ID)
        initial_prefix: Optional prefix from CLI args (skip browser if provided)

    Returns:
        Selected S3 prefix (e.g., "japan/tokyo/" or "" for root)

    Raises:
        SystemExit: If S3 access fails or user cancels
    """
    # Test S3 access first (fail-fast)
    try:
        validate_s3_access(bucket, aws_profile)
    except S3AccessError as e:
        print(f"Error: Cannot access S3 bucket '{bucket}'")
        print()
        print(str(e))
        raise SystemExit(1) from None

    # If prefix provided via CLI, skip browser
    if initial_prefix is not None:
        # Ensure prefix ends with / if not empty
        if initial_prefix and not initial_prefix.endswith("/"):
            initial_prefix = initial_prefix + "/"
        return initial_prefix

    # Run interactive browser
    print()
    print("Select S3 upload folder:")
    print()

    browser = S3FolderBrowser(S3FolderLister(bucket, aws_profile))

    try:
        selected_prefix = browser.run()
        return selected_prefix

    except KeyboardInterrupt:
        print("\n\nCancelled by user")
        raise SystemExit(1) from None

"""S3 upload with fail-fast error handling.

Uploads are reported through a :class:`~photo_terminal.domain.progress.ProgressReporter`
rather than drawn here: the spinner this module used to animate straight to
``sys.stdout`` now lives in :mod:`photo_terminal.app.reporter`, which is the
only place that decides what progress looks like.

The key scheme is not this module's to own either. ``_normalize_prefix`` and
``_construct_s3_key`` lived here and were imported by their underscored names
from ``dry_run``; they are now :mod:`photo_terminal.domain.naming`, which both
callers share as a rule rather than as a private detail of one of them.
"""

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from photo_terminal.domain.errors import UploadFailed
from photo_terminal.domain.models import ProcessedImage
from photo_terminal.domain.naming import construct_s3_key, normalize_prefix
from photo_terminal.domain.progress import ProgressReporter, reporter_or_null

__all__ = ["upload_images"]


def upload_images(
    processed_images: list[ProcessedImage],
    bucket: str,
    prefix: str,
    aws_profile: str | None,
    reporter: ProgressReporter | None = None,
) -> list[str]:
    """Upload processed images to S3 with minimal progress feedback.

    Uploads each processed image from temp directory to S3 bucket with the
    specified prefix. Shows a simple spinner with count during upload.
    Fails immediately on any upload error without retry.

    Args:
        processed_images: List of ProcessedImage objects from processor
        bucket: S3 bucket name
        prefix: S3 key prefix (folder path)
        aws_profile: AWS CLI profile name to use, or None to let boto3 resolve
            credentials from the environment (e.g. AWS_ACCESS_KEY_ID)
        reporter: Where per-file progress goes. Discarded when omitted.

    Returns:
        List of S3 keys for successfully uploaded images

    Raises:
        ValueError: If processed_images list is empty
        UploadFailed: If any upload fails (includes AWS error details)
    """
    # Fail-fast: Empty images list
    if not processed_images:
        raise ValueError("Processed images list cannot be empty")

    report = reporter_or_null(reporter)

    # Normalize prefix (handle empty string, trailing slashes)
    normalized_prefix = normalize_prefix(prefix)

    # Create boto3 S3 client with specified profile (or from environment)
    try:
        session = boto3.Session(profile_name=aws_profile) if aws_profile else boto3.Session()
        s3_client = session.client("s3")
    except Exception as e:
        error_msg = f"Failed to create AWS session: {e}"
        error_msg += (
            f"\nTry: aws configure --profile {aws_profile}"
            if aws_profile
            else "\nSet AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in .env (see .env.example)"
        )
        raise UploadFailed(error_msg) from e

    # Upload each image with progress feedback
    uploaded_keys = []
    total_count = len(processed_images)

    try:
        for idx, processed_img in enumerate(processed_images, start=1):
            # Construct S3 key - use upload_filename if set (for reordering), otherwise use original name
            filename = processed_img.target_filename
            s3_key = construct_s3_key(normalized_prefix, filename)

            # Progress is the pipeline's to present; we only report it.
            report.step(idx, total_count, filename)

            # Upload to S3
            try:
                s3_client.upload_file(
                    Filename=str(processed_img.temp_path), Bucket=bucket, Key=s3_key
                )
                uploaded_keys.append(s3_key)

            except ClientError as e:
                # Extract error details
                error_code = e.response.get("Error", {}).get("Code", "Unknown")
                error_msg = e.response.get("Error", {}).get("Message", str(e))

                # Fail-fast with detailed error message
                raise UploadFailed(
                    f"Failed to upload '{processed_img.original_path.name}' "
                    f"to s3://{bucket}/{s3_key}\n"
                    f"AWS Error [{error_code}]: {error_msg}"
                ) from e

            except (BotoCoreError, Exception) as e:
                # Fail-fast on any other error
                raise UploadFailed(
                    f"Failed to upload '{processed_img.original_path.name}' "
                    f"to s3://{bucket}/{s3_key}\n"
                    f"Error: {e}"
                ) from e

        return uploaded_keys

    finally:
        # End the progress run either way, so an error message cannot land
        # beside a live spinner.
        report.done()

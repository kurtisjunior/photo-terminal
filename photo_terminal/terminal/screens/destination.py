"""Stage 4: enter the S3 upload location."""

from __future__ import annotations

from photo_terminal.domain.naming import normalize_prefix

__all__ = ["enter_upload_location"]


def enter_upload_location(bucket: str) -> str | None:
    """Ask for an S3 prefix, with Enter completing the stage.

    A blank location deliberately means the bucket root. EOF cancels the run;
    Ctrl-C is allowed to propagate to the pipeline's shared cancellation path.
    """
    print("Upload Location")
    print("=" * 50)
    print()
    print(f"Bucket: s3://{bucket}/")
    print("Examples: japan/tokyo, newyork/summer-23")
    print("Leave blank to upload to the bucket root.")
    print()

    try:
        location = input("Location (Enter to continue): ")
    except EOFError:
        print()
        print("Upload cancelled.")
        return None

    print()
    return normalize_prefix(location)

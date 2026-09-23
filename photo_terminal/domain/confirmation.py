"""The text of the upload confirmation.

The prompt itself is terminal I/O and lives in
:mod:`photo_terminal.terminal.screens.confirm`. What is left here is the pure
part: the summary the user reads before answering, and the question they answer.
Both are strings, so a test reads them directly instead of capturing stdout.
"""

from pathlib import Path

__all__ = [
    "MAX_DISPLAY",
    "build_confirmation_prompt",
    "build_confirmation_summary",
    "format_s3_target",
]

# Beyond this many files the list is truncated with an "... and N more" line.
MAX_DISPLAY = 10


def format_s3_target(bucket: str, prefix: str) -> str:
    """The ``s3://`` URL for a bucket and prefix, with an empty prefix meaning root."""
    if prefix:
        return f"s3://{bucket}/{prefix}"
    return f"s3://{bucket}/"


def build_confirmation_summary(images: list[Path], bucket: str, prefix: str) -> str:
    """The upload summary shown before the confirmation prompt.

    Args:
        images: List of image paths to upload
        bucket: S3 bucket name
        prefix: S3 prefix/folder path (may be empty string for root)

    Returns:
        The summary block, without a trailing newline.
    """
    s3_target = format_s3_target(bucket, prefix)

    lines = [
        "Upload Confirmation",
        "=" * 50,
        "",
        f"Images to upload: {len(images)}",
        f"Target location:  {s3_target}",
        "",
    ]

    if len(images) <= MAX_DISPLAY:
        lines.append("Files:")
        lines.extend(f"  - {img.name}" for img in images)
    else:
        lines.append(f"Files (showing first {MAX_DISPLAY}):")
        lines.extend(f"  - {img.name}" for img in images[:MAX_DISPLAY])
        lines.append(f"  ... and {len(images) - MAX_DISPLAY} more")

    return "\n".join(lines)


def build_confirmation_prompt(images: list[Path], bucket: str, prefix: str) -> str:
    """The question put to the user, including its trailing space."""
    return f"Upload {len(images)} image(s) to {format_s3_target(bucket, prefix)}? [y/n]: "

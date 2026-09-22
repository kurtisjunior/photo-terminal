"""The typed error hierarchy the library raises instead of ``SystemExit``.

Before this module, nineteen call sites across ``config``, ``scanner``,
``confirmation``, ``dry_run`` and ``duplicate_checker`` printed guidance and
raised ``SystemExit`` from inside library functions. That made the exit code a
decision taken in the middle of a head-object loop, and it made every caller -
including the tests - wrap the call in ``pytest.raises(SystemExit)`` and scrape
stdout to find out what had gone wrong.

Library code now raises one of these instead. The message is user-facing and
carries no ``Error:`` prefix: the presentation layer adds the framing, so the
same exception can be printed by the CLI, shown inside a screen, or asserted on
in a test without any of them agreeing on punctuation.

(Phase 6 moves this module to ``photo_terminal/domain/errors.py``.)
"""

from __future__ import annotations

__all__ = [
    "ConfigError",
    "DuplicateKeyError",
    "InsufficientDiskSpaceError",
    "NoImagesFound",
    "PhotoTerminalError",
    "ProcessingError",
    "S3AccessError",
    "UploadFailed",
]


class PhotoTerminalError(Exception):
    """Base for every failure the user is meant to read.

    Attributes:
        message: The user-facing text, without an ``Error:`` prefix. May span
            several lines when the failure has remediation guidance to offer.
        exit_code: The process exit status the CLI should use for this failure.
    """

    exit_code: int = 1

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class ConfigError(PhotoTerminalError):
    """The configuration file is missing, unreadable, or invalid."""


class NoImagesFound(PhotoTerminalError):
    """The source folder holds no image this tool can process."""


class S3AccessError(PhotoTerminalError):
    """S3 could not be reached, or refused the credentials we presented."""


class DuplicateKeyError(PhotoTerminalError):
    """Uploading would overwrite keys that already exist in the target prefix.

    Attributes:
        duplicates: The filenames that already exist in S3.
        bucket: The S3 bucket that was checked.
        prefix: The prefix within that bucket, with a trailing slash when set.
    """

    def __init__(self, duplicates: list[str], bucket: str, prefix: str):
        self.duplicates = duplicates
        self.bucket = bucket
        self.prefix = prefix

        files_list = "\n  - ".join(duplicates)
        s3_path = f"s3://{bucket}/{prefix}" if prefix else f"s3://{bucket}/"

        super().__init__(
            f"The following files already exist in {s3_path}:\n"
            f"  - {files_list}\n\n"
            f"Aborting to prevent overwrites. No files were uploaded."
        )


class UploadFailed(PhotoTerminalError):
    """An upload to S3 did not complete. No retry is attempted."""


class ProcessingError(PhotoTerminalError):
    """An image could not be optimized."""


class InsufficientDiskSpaceError(PhotoTerminalError):
    """There is not enough room on disk to hold the processed images."""

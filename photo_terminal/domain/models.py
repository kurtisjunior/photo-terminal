"""The values the pipeline threads between its steps.

These are the nouns every layer shares. They live in ``domain`` so that
``imaging`` can produce a :class:`ProcessedImage`, ``storage`` can upload one
and ``reporting`` can summarise one without any of the three importing each
other.

``ProcessingOptions`` and ``S3Destination`` replace the untyped dictionary and
the bare string the configuration screen and the S3 browser used to hand back.
A ``dict[str, Any]`` that five call sites index by literal key is a type, just
an unchecked one.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

__all__ = [
    "OUTPUT_FORMATS",
    "Config",
    "ProcessedImage",
    "ProcessingOptions",
    "S3Destination",
]

#: The formats the optimizer can write, in the order the configuration screen
#: cycles through them.
OUTPUT_FORMATS = ("JPEG", "PNG", "WEBP")


@dataclass
class Config:
    """Settings read from ``photo-uploader.yaml``.

    Attributes:
        bucket: S3 bucket name for uploads.
        aws_profile: AWS CLI profile name, or ``None`` to let boto3 resolve
            credentials from the environment (e.g. ``AWS_ACCESS_KEY_ID``).
        target_size_kb: Target file size in kilobytes for JPEG optimization.
    """

    bucket: str
    aws_profile: str | None
    target_size_kb: int

    def with_target_size(self, target_size_kb: int | None) -> Config:
        """A copy with ``target_size_kb`` overridden, or ``self`` if it is ``None``.

        The CLI's ``--target-size`` used to be applied by assigning to the
        loaded config in the middle of ``main()``. Overriding by copy keeps the
        loaded configuration and the effective configuration distinguishable.
        """
        if target_size_kb is None:
            return self
        return replace(self, target_size_kb=target_size_kb)


@dataclass(frozen=True)
class ProcessingOptions:
    """How the selected images are to be processed, as chosen on stage 3."""

    resize: bool
    target_size_kb: int
    preserve_exif: bool
    output_format: str

    @property
    def effective_target_size_kb(self) -> int:
        """The size the optimizer is asked for.

        With resizing switched off the optimizer is still given a target - it
        is the configured default rather than the one chosen on the screen.
        """
        return self.target_size_kb


@dataclass(frozen=True)
class S3Destination:
    """Where an upload is going.

    ``prefix`` is empty for the bucket root, which is a real destination. The
    absence of a destination is expressed by ``None`` in place of the whole
    object, never by an empty prefix.
    """

    bucket: str
    prefix: str

    @property
    def url(self) -> str:
        """The ``s3://`` URL for this destination, with a trailing slash."""
        if self.prefix:
            return f"s3://{self.bucket}/{self.prefix.strip('/')}/"
        return f"s3://{self.bucket}/"


@dataclass
class ProcessedImage:
    """One optimized image, waiting in a temp directory to be uploaded.

    Attributes:
        original_path: Path to the original image file.
        temp_path: Path to the processed image in the temp directory.
        original_size: Original file size in bytes.
        final_size: Final file size in bytes after optimization.
        quality_used: JPEG quality level used (60-95).
        warnings: Warning messages raised during optimization.
        upload_filename: Filename to upload as, when reordering renamed it.
    """

    original_path: Path
    temp_path: Path
    original_size: int
    final_size: int
    quality_used: int
    warnings: list[str]
    upload_filename: str | None = None

    @property
    def target_filename(self) -> str:
        """The name this image is uploaded under."""
        return self.upload_filename or self.original_path.name

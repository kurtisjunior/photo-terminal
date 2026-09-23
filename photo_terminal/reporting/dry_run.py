"""Dry-run mode: what an upload would do, without doing it.

This module used to print its own report and then raise ``SystemExit(0)`` at
the end of what is otherwise a reporting function - a library call that ended
the process. It now processes the images, measures them, and returns a
:class:`DryRunReport`. Turning that report into text is two pure functions, and
printing it is the pipeline's job.
"""

from dataclasses import dataclass
from pathlib import Path

from photo_terminal.domain.errors import PhotoTerminalError
from photo_terminal.domain.naming import construct_s3_key, normalize_prefix
from photo_terminal.domain.progress import ProgressReporter
from photo_terminal.imaging.processor import process_images

__all__ = [
    "DryRunFile",
    "DryRunReport",
    "dry_run_upload",
    "render_header",
    "render_report",
]


@dataclass(frozen=True)
class DryRunFile:
    """One image's measured before/after, and where it would land."""

    name: str
    original_size: int
    final_size: int
    warnings: tuple[str, ...]
    s3_key: str

    @property
    def reduction_percent(self) -> float:
        """How much smaller the processed file is, as a percentage."""
        if self.original_size == 0:
            return 0.0
        return (1 - (self.final_size / self.original_size)) * 100


@dataclass(frozen=True)
class DryRunReport:
    """Everything a dry run found out, with nothing rendered yet."""

    bucket: str
    prefix: str
    target_size_kb: int
    output_format: str
    files: tuple[DryRunFile, ...]

    @property
    def total_original(self) -> int:
        return sum(f.original_size for f in self.files)

    @property
    def total_processed(self) -> int:
        return sum(f.final_size for f in self.files)

    @property
    def total_reduction_percent(self) -> float:
        if self.total_original == 0:
            return 0.0
        return (1 - (self.total_processed / self.total_original)) * 100


def dry_run_upload(
    images: list[Path],
    bucket: str,
    prefix: str,
    target_size_kb: int,
    aws_profile: str | None,
    output_format: str = "JPEG",
    reporter: ProgressReporter | None = None,
) -> DryRunReport:
    """Measure what would be uploaded, without uploading anything.

    Processes the images into a temporary directory to get accurate sizes,
    cleans that directory up, and returns the measurements.

    Args:
        images: List of image paths to process
        bucket: S3 bucket name
        prefix: S3 prefix/folder path (may be empty string for root)
        target_size_kb: Target file size in kilobytes
        aws_profile: AWS CLI profile name (not used in dry-run)
        output_format: Output format - 'JPEG', 'PNG', or 'WEBP' (default: 'JPEG')
        reporter: Where per-image processing progress goes.

    Returns:
        The report. Nothing is printed and nothing is uploaded.

    Raises:
        PhotoTerminalError: If the images could not be processed.
    """
    try:
        temp_dir, processed_images = process_images(
            images, target_size_kb, output_format, reporter=reporter
        )
    except PhotoTerminalError:
        raise
    except Exception as e:
        raise PhotoTerminalError(f"Image processing failed: {e}") from None

    normalized_prefix = normalize_prefix(prefix)

    try:
        files = tuple(
            DryRunFile(
                name=proc_img.original_path.name,
                original_size=proc_img.original_size,
                final_size=proc_img.final_size,
                warnings=tuple(proc_img.warnings),
                s3_key=construct_s3_key(normalized_prefix, proc_img.original_path.name),
            )
            for proc_img in processed_images
        )
    finally:
        # Always cleanup temp files
        temp_dir.cleanup()

    return DryRunReport(
        bucket=bucket,
        prefix=prefix,
        target_size_kb=target_size_kb,
        output_format=output_format,
        files=files,
    )


def render_header(
    bucket: str, prefix: str, target_size_kb: int, output_format: str = "JPEG"
) -> str:
    """The banner shown before processing starts.

    Kept separate from :func:`render_report` so the pipeline can show it while
    the images are still being measured, which is when it is useful.
    """
    # The prefix arrives with a trailing slash from the S3 browser and without
    # one from --prefix, and this line used to print "japan/tokyo//" for the
    # first of those.
    normalized = prefix.strip("/")
    s3_target = f"s3://{bucket}/{normalized}/" if normalized else f"s3://{bucket}/"

    return "\n".join(
        [
            "",
            "DRY RUN MODE - No files will be uploaded",
            "═" * 50,
            "",
            f"Target location: {s3_target}",
            f"Target size:     {target_size_kb} KB",
            f"Output format:   {output_format}",
            "",
        ]
    )


def render_report(report: DryRunReport) -> str:
    """The full dry-run report: per file, in summary, and as S3 keys."""
    lines: list[str] = ["Files to process:", ""]

    for file in report.files:
        lines.append(f"File: {file.name}")
        lines.append(f"  Original:  {file.original_size / (1024 * 1024):.1f} MB")
        lines.append(f"  Processed: {file.final_size / 1024:.0f} KB")
        lines.append(f"  Reduction: {file.reduction_percent:.1f}%")
        lines.extend(f"  Warning: {warning}" for warning in file.warnings)
        lines.append("")

    lines.append("SUMMARY")
    lines.append("─" * 50)
    lines.append(f"Total files:      {len(report.files)}")
    lines.append(f"Original size:    {report.total_original / (1024 * 1024):.1f} MB")
    lines.append(f"Processed size:   {report.total_processed / (1024 * 1024):.1f} MB")
    lines.append(f"Total reduction:  {report.total_reduction_percent:.1f}%")
    lines.append("")

    lines.append("S3 keys that would be created:")
    lines.extend(f"  - {file.s3_key}" for file in report.files)
    lines.append("")

    lines.append("")
    lines.append("DRY RUN COMPLETE - No files were uploaded")
    lines.append("")

    return "\n".join(lines)

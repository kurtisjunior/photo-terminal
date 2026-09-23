"""Image processing pipeline with temporary file management.

Handles batch image processing with automatic cleanup, disk space checking,
and progress feedback. Uses tempfile.TemporaryDirectory for processed images
with automatic cleanup on success and persistence on failure for retry.

The :class:`~photo_terminal.domain.models.ProcessedImage` this produces is a
domain model rather than something defined here: ``storage`` uploads one and
``reporting`` summarises one, and neither of those should have to import the
imaging package to name its result.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from photo_terminal.domain.errors import InsufficientDiskSpaceError, ProcessingError
from photo_terminal.domain.models import ProcessedImage
from photo_terminal.domain.progress import ProgressReporter, reporter_or_null
from photo_terminal.imaging.optimizer import optimize_image

__all__ = ["process_images"]


def process_images(
    images: list[Path],
    target_size_kb: int = 400,
    output_format: str = "JPEG",
    max_dimension: int = 1920,
    filename_map: dict[Path, str] | None = None,
    reporter: ProgressReporter | None = None,
) -> tuple[tempfile.TemporaryDirectory[str], list[ProcessedImage]]:
    """Process multiple images with optimization and save to temp directory.

    Creates a temporary directory, checks available disk space, then processes
    each image using the optimizer. Resizes images if needed, then saves optimized
    images with updated file extensions based on output format in the temp directory.
    Returns temp directory object (for lifecycle management) and list of processing results.

    The caller is responsible for managing the temp directory lifecycle:
    - On success: call temp_dir.cleanup() or let it auto-cleanup on exit
    - On failure: keep temp directory for retry without reprocessing

    Args:
        images: List of paths to image files to process
        target_size_kb: Target file size in kilobytes (default: 400)
        output_format: Output format - 'JPEG', 'PNG', or 'WEBP' (default: 'JPEG')
        max_dimension: Maximum width or height in pixels (default: 1920)
        filename_map: Optional dict mapping original Path to new filename (for reordering)
        reporter: Where per-image progress goes. Discarded when omitted.

    Returns:
        Tuple of (temp_directory, processed_images):
            - temp_directory: TemporaryDirectory object (caller manages cleanup)
            - processed_images: List of ProcessedImage dataclass instances

    Raises:
        InsufficientDiskSpaceError: If not enough disk space for processing
        ProcessingError: If optimization fails on any image
        ValueError: If images list is empty or invalid format
    """
    # Fail-fast: Empty images list
    if not images:
        raise ValueError("Images list cannot be empty")

    # Validate output format
    output_format = output_format.upper()
    if output_format not in ("JPEG", "PNG", "WEBP"):
        raise ValueError(f"Unsupported output format: {output_format}. Must be JPEG, PNG, or WEBP")

    # Determine file extension for output format
    format_extensions = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}
    output_extension = format_extensions[output_format]

    report = reporter_or_null(reporter)

    # Create temporary directory
    temp_dir = tempfile.TemporaryDirectory(prefix="photo_upload_")
    temp_dir_path = Path(temp_dir.name)

    try:
        # Check available disk space before processing
        _check_disk_space(images, temp_dir_path)

        # Process each image
        processed_images = []
        for idx, image_path in enumerate(images, start=1):
            # Progress is the pipeline's to present; we only report it.
            report.step(idx, len(images), image_path.name)

            # Create output path with updated extension for output format
            # Use custom filename from filename_map if provided (for reordering)
            if filename_map and image_path in filename_map:
                # Use the mapped filename (already has extension from reorder logic)
                upload_filename = filename_map[image_path]
                # Extract stem and replace extension with output format extension
                mapped_stem = Path(upload_filename).stem
                output_filename = mapped_stem + output_extension
            else:
                # No mapping - use original filename
                output_filename = image_path.stem + output_extension
                upload_filename = None

            output_path = temp_dir_path / output_filename

            try:
                # Optimize image (with resizing if needed)
                result = optimize_image(
                    image_path, output_path, target_size_kb, output_format, max_dimension
                )

                # Create ProcessedImage metadata
                processed = ProcessedImage(
                    original_path=image_path,
                    temp_path=output_path,
                    original_size=result["original_size"],
                    final_size=result["final_size"],
                    quality_used=result["quality_used"],
                    warnings=result["warnings"],
                    upload_filename=upload_filename,
                )
                processed_images.append(processed)

            except Exception as e:
                # Fail-fast: Include filename in error message
                raise ProcessingError(f"Failed to process image '{image_path.name}': {e}") from e

        return temp_dir, processed_images

    finally:
        # End the progress run either way - the reporter owns erasing whatever
        # it drew, and an error message must not land beside a live spinner.
        # On error the temp directory is deliberately left in place for retry.
        report.done()


def _check_disk_space(images: list[Path], temp_dir_path: Path) -> None:
    """Check if there is sufficient disk space for processing.

    Estimates needed space as sum of original file sizes * 1.5 (safety margin)
    to account for potential temporary files during processing.

    Args:
        images: List of image paths to process
        temp_dir_path: Path to temporary directory

    Raises:
        InsufficientDiskSpaceError: If available space is less than needed
    """
    # Calculate total size of input images
    total_size = sum(img.stat().st_size for img in images)

    # Estimate needed space with 1.5x safety margin
    needed_space = int(total_size * 1.5)

    # Check available disk space
    disk_usage = shutil.disk_usage(temp_dir_path)
    available_space = disk_usage.free

    # Fail-fast if insufficient space
    if available_space < needed_space:
        raise InsufficientDiskSpaceError(
            f"Insufficient disk space for processing. "
            f"Needed: {needed_space / (1024 * 1024):.1f}MB, "
            f"Available: {available_space / (1024 * 1024):.1f}MB"
        )

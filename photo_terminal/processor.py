"""Image processing pipeline with temporary file management.

Handles batch image processing with automatic cleanup, disk space checking,
and progress feedback. Uses tempfile.TemporaryDirectory for processed images
with automatic cleanup on success and persistence on failure for retry.
"""

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

from photo_terminal.optimizer import optimize_image


@dataclass
class ProcessedImage:
    """Metadata for a processed image.

    Attributes:
        original_path: Path to original image file
        temp_path: Path to processed image in temp directory
        original_size: Original file size in bytes
        final_size: Final file size in bytes after optimization
        quality_used: JPEG quality level used (60-95)
        warnings: List of warning messages from optimization
    """
    original_path: Path
    temp_path: Path
    original_size: int
    final_size: int
    quality_used: int
    warnings: List[str]


class ProcessingError(Exception):
    """Raised when image processing fails."""
    pass


class InsufficientDiskSpaceError(Exception):
    """Raised when there is not enough disk space for processing."""
    pass


def process_images(
    images: List[Path],
    target_size_kb: int = 400
) -> Tuple[tempfile.TemporaryDirectory, List[ProcessedImage]]:
    """Process multiple images with optimization and save to temp directory.

    Creates a temporary directory, checks available disk space, then processes
    each image using the optimizer. Saves optimized images with original filenames
    in the temp directory. Returns temp directory object (for lifecycle management)
    and list of processing results.

    The caller is responsible for managing the temp directory lifecycle:
    - On success: call temp_dir.cleanup() or let it auto-cleanup on exit
    - On failure: keep temp directory for retry without reprocessing

    Args:
        images: List of paths to image files to process
        target_size_kb: Target file size in kilobytes (default: 400)

    Returns:
        Tuple of (temp_directory, processed_images):
            - temp_directory: TemporaryDirectory object (caller manages cleanup)
            - processed_images: List of ProcessedImage dataclass instances

    Raises:
        InsufficientDiskSpaceError: If not enough disk space for processing
        ProcessingError: If optimization fails on any image
        ValueError: If images list is empty
    """
    # Fail-fast: Empty images list
    if not images:
        raise ValueError("Images list cannot be empty")

    # Create temporary directory
    temp_dir = tempfile.TemporaryDirectory(prefix="photo_upload_")
    temp_dir_path = Path(temp_dir.name)

    try:
        # Check available disk space before processing
        _check_disk_space(images, temp_dir_path)

        # Process each image
        processed_images = []
        for idx, image_path in enumerate(images, start=1):
            # Show minimal progress feedback
            print(f"Processing image {idx}/{len(images)}...")

            # Create output path with same filename in temp directory
            output_path = temp_dir_path / image_path.name

            try:
                # Optimize image
                result = optimize_image(image_path, output_path, target_size_kb)

                # Create ProcessedImage metadata
                processed = ProcessedImage(
                    original_path=image_path,
                    temp_path=output_path,
                    original_size=result['original_size'],
                    final_size=result['final_size'],
                    quality_used=result['quality_used'],
                    warnings=result['warnings']
                )
                processed_images.append(processed)

            except Exception as e:
                # Fail-fast: Include filename in error message
                raise ProcessingError(
                    f"Failed to process image '{image_path.name}': {e}"
                ) from e

        # Clear progress line after processing
        print("\033[2K\033[1G", end="", flush=True)  # Clear line and return to start

        return temp_dir, processed_images

    except Exception:
        # On error, don't cleanup temp directory (for retry)
        # Re-raise the exception
        raise


def _check_disk_space(images: List[Path], temp_dir_path: Path) -> None:
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

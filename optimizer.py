"""Image optimization module for photo uploader.

Size-based JPEG optimization with EXIF preservation using Pillow.
Iteratively adjusts JPEG quality to reach target file size while
preserving aspect ratio and basic EXIF data (camera, date, GPS).
"""

from pathlib import Path
from typing import Dict, Optional
import io

from PIL import Image
from PIL.ExifTags import TAGS


# Quality iteration steps from highest to minimum acceptable
QUALITY_STEPS = [95, 90, 85, 80, 75, 70, 65, 60]
MINIMUM_QUALITY = 60

# EXIF tags to preserve (camera model, date taken, GPS)
PRESERVE_EXIF_TAGS = {
    'Make',  # Camera manufacturer
    'Model',  # Camera model
    'DateTimeOriginal',  # Date photo was taken
    'DateTime',  # Date file was modified
    'DateTimeDigitized',  # Date photo was digitized
    'GPSInfo',  # GPS coordinates
}


class OptimizationWarning:
    """Warning types for optimization process."""
    TARGET_NOT_REACHED = "target_size_not_reached"
    EXIF_PRESERVATION_FAILED = "exif_preservation_failed"
    NO_EXIF_DATA = "no_exif_data"


def optimize_image(
    input_path: Path,
    output_path: Path,
    target_size_kb: int = 400
) -> Dict:
    """Optimize image to target file size with EXIF preservation.

    Opens image with Pillow, extracts EXIF data, and iteratively saves
    with decreasing JPEG quality until target size is reached. Preserves
    camera model, date taken, and GPS coordinates.

    Args:
        input_path: Path to input image file
        output_path: Path where optimized JPEG will be saved
        target_size_kb: Target file size in kilobytes (default: 400)

    Returns:
        Dictionary with optimization results:
            - original_size: Original file size in bytes
            - final_size: Final file size in bytes
            - quality_used: JPEG quality level used (60-95)
            - format: Original image format
            - warnings: List of warning messages (if any)

    Raises:
        FileNotFoundError: If input file does not exist
        ValueError: If input file cannot be opened as image
        IOError: If output file cannot be written
    """
    # Fail-fast: Validate input file exists
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    # Get original file size
    original_size = input_path.stat().st_size

    # Fail-fast: Try to open image
    try:
        img = Image.open(input_path)
    except Exception as e:
        raise ValueError(f"Cannot open image file: {input_path}. Error: {e}")

    # Store original format for reporting
    original_format = img.format or "UNKNOWN"

    # Convert to RGB if necessary (handles RGBA, grayscale, etc.)
    if img.mode not in ('RGB', 'L'):
        # Convert RGBA to RGB by compositing on white background
        if img.mode == 'RGBA':
            background = Image.new('RGB', img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[3])  # Use alpha channel as mask
            img = background
        else:
            img = img.convert('RGB')
    elif img.mode == 'L':
        # Convert grayscale to RGB
        img = img.convert('RGB')

    # Extract and filter EXIF data (best-effort)
    exif_data, exif_warnings = _extract_exif(img)

    # Calculate target size in bytes
    target_size_bytes = target_size_kb * 1024

    # If image is already smaller than target, use quality 95
    if original_size <= target_size_bytes:
        quality = 95
        _save_jpeg(img, output_path, quality, exif_data)
        final_size = output_path.stat().st_size

        warnings = exif_warnings.copy()
        return {
            'original_size': original_size,
            'final_size': final_size,
            'quality_used': quality,
            'format': original_format,
            'warnings': warnings
        }

    # Iteratively try quality levels to reach target size
    quality_used = None
    final_size = None
    warnings = exif_warnings.copy()

    for quality in QUALITY_STEPS:
        # Save to output path
        _save_jpeg(img, output_path, quality, exif_data)
        final_size = output_path.stat().st_size

        # Check if we reached target
        if final_size <= target_size_bytes:
            quality_used = quality
            break

    # If we didn't reach target even at minimum quality, warn user
    if quality_used is None:
        quality_used = MINIMUM_QUALITY
        warnings.append(
            f"{OptimizationWarning.TARGET_NOT_REACHED}: "
            f"Could not reach target size of {target_size_kb}KB at minimum quality {MINIMUM_QUALITY}. "
            f"Final size: {final_size / 1024:.1f}KB"
        )

    return {
        'original_size': original_size,
        'final_size': final_size,
        'quality_used': quality_used,
        'format': original_format,
        'warnings': warnings
    }


def _extract_exif(img: Image.Image) -> tuple[Optional[bytes], list[str]]:
    """Extract and filter EXIF data from image.

    Best-effort extraction - returns None if EXIF data is missing or corrupted.

    Args:
        img: PIL Image object

    Returns:
        Tuple of (exif_bytes, warnings):
            - exif_bytes: Serialized EXIF data to preserve, or None
            - warnings: List of warning messages
    """
    warnings = []

    try:
        # Try to get EXIF data
        exif = img.getexif()

        if exif is None or len(exif) == 0:
            warnings.append(f"{OptimizationWarning.NO_EXIF_DATA}: No EXIF data found in image")
            return None, warnings

        # Filter to only preserve specific tags
        # Note: Pillow's getexif() returns ExifTags which can be passed to save()
        # We'll return the raw exif data and let save() handle it
        return exif.tobytes() if hasattr(exif, 'tobytes') else img.info.get('exif'), warnings

    except Exception as e:
        warnings.append(
            f"{OptimizationWarning.EXIF_PRESERVATION_FAILED}: "
            f"Could not extract EXIF data: {e}"
        )
        return None, warnings


def _save_jpeg(img: Image.Image, output_path: Path, quality: int, exif_data: Optional[bytes]) -> None:
    """Save image as JPEG with specified quality and EXIF data.

    Args:
        img: PIL Image object to save
        output_path: Path where JPEG will be saved
        quality: JPEG quality level (1-100)
        exif_data: EXIF data bytes to preserve, or None

    Raises:
        IOError: If file cannot be written
    """
    try:
        # Prepare save parameters
        save_kwargs = {
            'format': 'JPEG',
            'quality': quality,
            'optimize': True,  # Enable JPEG optimization
        }

        # Add EXIF data if available
        if exif_data is not None:
            save_kwargs['exif'] = exif_data

        # Save the image
        img.save(output_path, **save_kwargs)

    except Exception as e:
        raise IOError(f"Could not save image to {output_path}: {e}")

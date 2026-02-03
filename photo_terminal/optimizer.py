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
    target_size_kb: int = 400,
    output_format: str = 'JPEG',
    max_dimension: int = 1920
) -> Dict:
    """Optimize image to target file size with EXIF preservation and resizing.

    Opens image with Pillow, resizes if needed, extracts EXIF data, and iteratively
    saves with decreasing quality until target size is reached. Preserves aspect ratio,
    camera model, date taken, and GPS coordinates.

    Args:
        input_path: Path to input image file
        output_path: Path where optimized image will be saved
        target_size_kb: Target file size in kilobytes (default: 400)
        output_format: Output format - 'JPEG', 'PNG', or 'WEBP' (default: 'JPEG')
        max_dimension: Maximum width or height in pixels (default: 1920).
                      Images larger than this will be resized proportionally.

    Returns:
        Dictionary with optimization results:
            - original_size: Original file size in bytes
            - final_size: Final file size in bytes
            - quality_used: Quality/compression level used (format-dependent)
            - format: Original image format
            - output_format: Output format used
            - resized: Boolean indicating if image was resized
            - original_dimensions: Tuple of (width, height) before resize
            - final_dimensions: Tuple of (width, height) after resize
            - warnings: List of warning messages (if any)

    Raises:
        FileNotFoundError: If input file does not exist
        ValueError: If input file cannot be opened as image or invalid format
        IOError: If output file cannot be written
    """
    # Validate output format
    output_format = output_format.upper()
    if output_format not in ('JPEG', 'PNG', 'WEBP'):
        raise ValueError(f"Unsupported output format: {output_format}. Must be JPEG, PNG, or WEBP")

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

    # Store original format and dimensions for reporting
    original_format = img.format or "UNKNOWN"
    original_dimensions = (img.width, img.height)

    # Resize if image exceeds max dimension
    resized = False
    if img.width > max_dimension or img.height > max_dimension:
        # Calculate new dimensions preserving aspect ratio
        if img.width > img.height:
            new_width = max_dimension
            new_height = int((max_dimension / img.width) * img.height)
        else:
            new_height = max_dimension
            new_width = int((max_dimension / img.height) * img.width)

        # Resize using high-quality Lanczos resampling
        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        resized = True

    final_dimensions = (img.width, img.height)

    # Convert to appropriate mode for output format
    if output_format == 'PNG':
        # PNG supports RGBA, so preserve transparency if present
        if img.mode in ('RGBA', 'LA', 'PA'):
            img = img.convert('RGBA')
        elif img.mode not in ('RGB', 'L', 'RGBA'):
            img = img.convert('RGB')
    else:
        # JPEG and WEBP don't support transparency
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

    # Handle PNG differently (lossless format)
    if output_format == 'PNG':
        # PNG is lossless, so we can't optimize to target size
        # Just use maximum compression
        _save_image(img, output_path, output_format, compress_level=9, exif_data=exif_data)
        final_size = output_path.stat().st_size

        warnings = exif_warnings.copy()
        if final_size > target_size_bytes:
            warnings.append(
                f"{OptimizationWarning.TARGET_NOT_REACHED}: "
                f"PNG is lossless and cannot be optimized to target size. "
                f"Final size: {final_size / 1024:.1f}KB (target: {target_size_kb}KB)"
            )

        return {
            'original_size': original_size,
            'final_size': final_size,
            'quality_used': 9,  # compression level
            'format': original_format,
            'output_format': output_format,
            'resized': resized,
            'original_dimensions': original_dimensions,
            'final_dimensions': final_dimensions,
            'warnings': warnings
        }

    # For JPEG and WEBP, use quality iteration to reach target size
    quality_used = None
    final_size = None
    warnings = exif_warnings.copy()

    for quality in QUALITY_STEPS:
        # Save to output path
        _save_image(img, output_path, output_format, quality=quality, exif_data=exif_data)
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
        'output_format': output_format,
        'resized': resized,
        'original_dimensions': original_dimensions,
        'final_dimensions': final_dimensions,
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


def _save_image(
    img: Image.Image,
    output_path: Path,
    output_format: str,
    quality: int = None,
    compress_level: int = None,
    exif_data: Optional[bytes] = None
) -> None:
    """Save image with specified format, quality/compression, and EXIF data.

    Args:
        img: PIL Image object to save
        output_path: Path where image will be saved
        output_format: Output format - 'JPEG', 'PNG', or 'WEBP'
        quality: Quality level for JPEG/WEBP (1-100), ignored for PNG
        compress_level: Compression level for PNG (0-9), ignored for JPEG/WEBP
        exif_data: EXIF data bytes to preserve, or None

    Raises:
        IOError: If file cannot be written
    """
    try:
        # Prepare save parameters based on format
        save_kwargs = {
            'format': output_format,
        }

        if output_format == 'JPEG':
            save_kwargs['quality'] = quality if quality is not None else 95
            save_kwargs['optimize'] = True
            # Add EXIF data if available
            if exif_data is not None:
                save_kwargs['exif'] = exif_data

        elif output_format == 'PNG':
            save_kwargs['compress_level'] = compress_level if compress_level is not None else 9
            save_kwargs['optimize'] = True
            # PNG can store EXIF in metadata, but it's less common
            # Pillow doesn't directly support EXIF in PNG via 'exif' parameter

        elif output_format == 'WEBP':
            save_kwargs['quality'] = quality if quality is not None else 95
            # WEBP supports EXIF
            if exif_data is not None:
                save_kwargs['exif'] = exif_data

        # Save the image
        img.save(output_path, **save_kwargs)

    except Exception as e:
        raise IOError(f"Could not save image to {output_path}: {e}")

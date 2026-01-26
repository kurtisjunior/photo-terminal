"""Folder scanner with image format validation.

Scans a folder for valid image files and validates formats using Pillow.
Supports JPEG, PNG, WEBP, TIFF, BMP, GIF. No RAW format support.
"""

from pathlib import Path
from typing import List

from PIL import Image


# Supported image formats
SUPPORTED_FORMATS = {'JPEG', 'PNG', 'WEBP', 'TIFF', 'BMP', 'GIF'}

# Common image file extensions
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.tiff', '.tif', '.bmp', '.gif'}


def is_valid_image(file_path: Path) -> bool:
    """Check if file is a valid image with supported format.

    Uses Pillow to verify the file can be opened and has a supported format.
    Uses magic bytes detection via Pillow, not just extension checking.

    Args:
        file_path: Path to file to validate

    Returns:
        True if file is a valid image with supported format, False otherwise
    """
    # Quick extension check first (optimization)
    if file_path.suffix.lower() not in IMAGE_EXTENSIONS:
        return False

    # Verify with Pillow (magic bytes detection)
    try:
        with Image.open(file_path) as img:
            # Check if format is supported
            if img.format in SUPPORTED_FORMATS:
                return True
    except (IOError, OSError):
        # Not a valid image file
        pass

    return False


def scan_folder(folder_path: str) -> List[Path]:
    """Scan folder for valid image files.

    Args:
        folder_path: Path to folder to scan

    Returns:
        List of Path objects for valid image files, sorted by name

    Raises:
        SystemExit: If folder is empty or contains no valid images
    """
    path = Path(folder_path).resolve()

    # Get all files in folder (non-recursive, exclude hidden files)
    all_files = [
        f for f in path.iterdir()
        if f.is_file() and not f.name.startswith('.')
    ]

    # Filter to valid images
    valid_images = [
        f for f in all_files
        if is_valid_image(f)
    ]

    # Fail-fast if no valid images found
    if not valid_images:
        if not all_files:
            print(f"Error: Folder is empty: {folder_path}")
        else:
            print(f"Error: No valid images found in folder: {folder_path}")
            print(f"Supported formats: {', '.join(sorted(SUPPORTED_FORMATS))}")
        raise SystemExit(1)

    # Sort by filename for consistent ordering
    valid_images.sort()

    # Print summary
    print(f"Found {len(valid_images)} valid image(s)")
    print()

    return valid_images

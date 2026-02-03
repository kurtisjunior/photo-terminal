"""Image reordering module for photo uploader.

Provides logic for interactively reordering images before upload.
Supports grab-and-drop interaction with real-time state management.
"""

from pathlib import Path
from typing import List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class ReorderState:
    """State for image reordering interface.

    Attributes:
        images: List of image paths in current order
        current_index: Currently selected image index (0-based)
        grabbed_index: Index of grabbed image, None if nothing grabbed
        original_order: Original image order for reset functionality
    """
    images: List[Path]
    current_index: int = 0
    grabbed_index: Optional[int] = None
    original_order: List[Path] = None

    def __post_init__(self):
        """Store original order for reset functionality."""
        if self.original_order is None:
            self.original_order = self.images.copy()


class ImageReorderer:
    """Manages image reordering logic with grab-and-drop functionality.

    Provides methods to move images up/down, grab/drop, and reset to original order.
    Maintains state for current selection and grabbed item.

    Example:
        reorderer = ImageReorderer(image_paths)
        reorderer.move_down()  # Navigate down
        reorderer.grab()       # Grab current image
        reorderer.move_down()  # Move with grabbed image
        reorderer.drop()       # Drop in new position
        ordered_paths = reorderer.get_ordered_images()
    """

    def __init__(self, images: List[Path]):
        """Initialize reorderer with list of image paths.

        Args:
            images: List of Path objects for images to reorder

        Raises:
            ValueError: If images list is empty
        """
        if not images:
            raise ValueError("Images list cannot be empty")

        self.state = ReorderState(images=images.copy())

    def move_up(self) -> bool:
        """Move selection or grabbed item up one position.

        If an item is grabbed, it swaps with the item above it.
        If nothing is grabbed, just moves the selection cursor up.

        Returns:
            True if move was successful, False if at top boundary
        """
        if self.state.grabbed_index is not None:
            # Move grabbed item up
            if self.state.grabbed_index == 0:
                return False  # Can't move up from top

            # Swap with item above
            idx = self.state.grabbed_index
            self.state.images[idx], self.state.images[idx - 1] = \
                self.state.images[idx - 1], self.state.images[idx]

            # Update indices
            self.state.grabbed_index -= 1
            self.state.current_index -= 1
            return True
        else:
            # Just move cursor up
            if self.state.current_index == 0:
                return False  # Already at top

            self.state.current_index -= 1
            return True

    def move_down(self) -> bool:
        """Move selection or grabbed item down one position.

        If an item is grabbed, it swaps with the item below it.
        If nothing is grabbed, just moves the selection cursor down.

        Returns:
            True if move was successful, False if at bottom boundary
        """
        if self.state.grabbed_index is not None:
            # Move grabbed item down
            if self.state.grabbed_index >= len(self.state.images) - 1:
                return False  # Can't move down from bottom

            # Swap with item below
            idx = self.state.grabbed_index
            self.state.images[idx], self.state.images[idx + 1] = \
                self.state.images[idx + 1], self.state.images[idx]

            # Update indices
            self.state.grabbed_index += 1
            self.state.current_index += 1
            return True
        else:
            # Just move cursor down
            if self.state.current_index >= len(self.state.images) - 1:
                return False  # Already at bottom

            self.state.current_index += 1
            return True

    def grab(self) -> bool:
        """Grab the currently selected image.

        Returns:
            True if grab was successful, False if already grabbed
        """
        if self.state.grabbed_index is not None:
            return False  # Already grabbed

        self.state.grabbed_index = self.state.current_index
        return True

    def drop(self) -> bool:
        """Drop the currently grabbed image.

        Returns:
            True if drop was successful, False if nothing was grabbed
        """
        if self.state.grabbed_index is None:
            return False  # Nothing to drop

        self.state.grabbed_index = None
        return True

    def toggle_grab(self) -> bool:
        """Toggle between grab and drop states.

        Convenience method that grabs if nothing is grabbed, drops if grabbed.

        Returns:
            True if state changed (grabbed or dropped), False otherwise
        """
        if self.state.grabbed_index is not None:
            return self.drop()
        else:
            return self.grab()

    def reset(self):
        """Reset to original image order."""
        self.state.images = self.state.original_order.copy()
        self.state.current_index = 0
        self.state.grabbed_index = None

    def get_ordered_images(self) -> List[Path]:
        """Get current image order.

        Returns:
            List of Path objects in current order
        """
        return self.state.images.copy()

    def get_current_index(self) -> int:
        """Get current selection index.

        Returns:
            Current selection index (0-based)
        """
        return self.state.current_index

    def is_grabbed(self) -> bool:
        """Check if an image is currently grabbed.

        Returns:
            True if an image is grabbed, False otherwise
        """
        return self.state.grabbed_index is not None

    def get_grabbed_index(self) -> Optional[int]:
        """Get index of grabbed image.

        Returns:
            Index of grabbed image, or None if nothing grabbed
        """
        return self.state.grabbed_index


def generate_prefixed_filenames(images: List[Path]) -> List[Tuple[Path, str]]:
    """Generate prefixed filenames for ordered upload.

    Creates numeric prefixes (01_, 02_, 03_, etc.) to maintain order on S3.
    Uses zero-padding appropriate for the total number of images.

    Args:
        images: List of image paths in desired order

    Returns:
        List of tuples: (original_path, prefixed_filename)

    Example:
        >>> images = [Path("photo1.jpg"), Path("photo2.jpg")]
        >>> generate_prefixed_filenames(images)
        [(Path("photo1.jpg"), "01_photo1.jpg"), (Path("photo2.jpg"), "02_photo2.jpg")]
    """
    # Determine padding width based on total count
    total = len(images)
    width = len(str(total))

    result = []
    for idx, img_path in enumerate(images, start=1):
        prefix = str(idx).zfill(width)
        new_filename = f"{prefix}_{img_path.name}"
        result.append((img_path, new_filename))

    return result


def get_final_filenames_preview(images: List[Path]) -> str:
    """Generate a preview string of final upload filenames.

    Args:
        images: List of image paths in desired order

    Returns:
        String showing arrow-separated list of prefixed filenames

    Example:
        "01_photo1.jpg → 02_photo2.jpg → 03_photo3.jpg"
    """
    prefixed = generate_prefixed_filenames(images)
    filenames = [filename for _, filename in prefixed]

    # Limit to first 3 and last 1 if more than 4 images
    if len(filenames) > 4:
        preview = filenames[:3] + ['...'] + [filenames[-1]]
    else:
        preview = filenames

    return ' → '.join(preview)

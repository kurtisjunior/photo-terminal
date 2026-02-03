"""Unit tests for image reordering logic."""

import pytest
from pathlib import Path

from photo_terminal.reorder import (
    ImageReorderer,
    ReorderState,
    generate_prefixed_filenames,
    get_final_filenames_preview
)


@pytest.fixture
def sample_images():
    """Create sample image paths for testing."""
    return [
        Path("/tmp/image1.jpg"),
        Path("/tmp/image2.jpg"),
        Path("/tmp/image3.jpg"),
        Path("/tmp/image4.jpg")
    ]


class TestImageReorderer:
    """Test ImageReorderer class functionality."""

    def test_init(self, sample_images):
        """Test reorderer initialization."""
        reorderer = ImageReorderer(sample_images)

        assert reorderer.get_ordered_images() == sample_images
        assert reorderer.get_current_index() == 0
        assert not reorderer.is_grabbed()

    def test_init_empty_images_fails(self):
        """Test that empty images list raises ValueError."""
        with pytest.raises(ValueError, match="Images list cannot be empty"):
            ImageReorderer([])

    def test_move_down(self, sample_images):
        """Test moving selection down."""
        reorderer = ImageReorderer(sample_images)

        # Move down once
        assert reorderer.move_down()
        assert reorderer.get_current_index() == 1

        # Move down again
        assert reorderer.move_down()
        assert reorderer.get_current_index() == 2

    def test_move_down_at_bottom(self, sample_images):
        """Test that move_down at bottom returns False."""
        reorderer = ImageReorderer(sample_images)

        # Move to bottom
        for _ in range(3):
            reorderer.move_down()

        # Try to move past bottom
        assert not reorderer.move_down()
        assert reorderer.get_current_index() == 3

    def test_move_up(self, sample_images):
        """Test moving selection up."""
        reorderer = ImageReorderer(sample_images)

        # Move down to position 2
        reorderer.move_down()
        reorderer.move_down()

        # Move up
        assert reorderer.move_up()
        assert reorderer.get_current_index() == 1

    def test_move_up_at_top(self, sample_images):
        """Test that move_up at top returns False."""
        reorderer = ImageReorderer(sample_images)

        # Try to move up from top
        assert not reorderer.move_up()
        assert reorderer.get_current_index() == 0

    def test_grab_and_drop(self, sample_images):
        """Test grabbing and dropping an image."""
        reorderer = ImageReorderer(sample_images)

        # Grab first image
        assert reorderer.grab()
        assert reorderer.is_grabbed()
        assert reorderer.get_grabbed_index() == 0

        # Drop image
        assert reorderer.drop()
        assert not reorderer.is_grabbed()
        assert reorderer.get_grabbed_index() is None

    def test_grab_when_already_grabbed(self, sample_images):
        """Test that grabbing when already grabbed returns False."""
        reorderer = ImageReorderer(sample_images)

        assert reorderer.grab()
        assert not reorderer.grab()  # Already grabbed

    def test_drop_when_nothing_grabbed(self, sample_images):
        """Test that dropping when nothing grabbed returns False."""
        reorderer = ImageReorderer(sample_images)

        assert not reorderer.drop()  # Nothing to drop

    def test_toggle_grab(self, sample_images):
        """Test toggle_grab functionality."""
        reorderer = ImageReorderer(sample_images)

        # Toggle to grab
        assert reorderer.toggle_grab()
        assert reorderer.is_grabbed()

        # Toggle to drop
        assert reorderer.toggle_grab()
        assert not reorderer.is_grabbed()

    def test_move_grabbed_item_down(self, sample_images):
        """Test moving grabbed item down swaps positions."""
        reorderer = ImageReorderer(sample_images)

        # Grab first item
        reorderer.grab()

        # Move down - should swap with second item
        assert reorderer.move_down()

        images = reorderer.get_ordered_images()
        assert images[0] == sample_images[1]
        assert images[1] == sample_images[0]
        assert reorderer.get_current_index() == 1
        assert reorderer.get_grabbed_index() == 1

    def test_move_grabbed_item_up(self, sample_images):
        """Test moving grabbed item up swaps positions."""
        reorderer = ImageReorderer(sample_images)

        # Move to position 1
        reorderer.move_down()

        # Grab item at position 1
        reorderer.grab()

        # Move up - should swap with first item
        assert reorderer.move_up()

        images = reorderer.get_ordered_images()
        assert images[0] == sample_images[1]
        assert images[1] == sample_images[0]
        assert reorderer.get_current_index() == 0
        assert reorderer.get_grabbed_index() == 0

    def test_move_grabbed_item_at_boundary(self, sample_images):
        """Test that grabbed item can't move past boundaries."""
        reorderer = ImageReorderer(sample_images)

        # Grab first item and try to move up
        reorderer.grab()
        assert not reorderer.move_up()

        # Move to bottom
        for _ in range(3):
            reorderer.move_down()

        # Try to move past bottom
        assert not reorderer.move_down()

    def test_reset_to_original_order(self, sample_images):
        """Test reset functionality."""
        reorderer = ImageReorderer(sample_images)

        # Reorder images
        reorderer.grab()
        reorderer.move_down()
        reorderer.move_down()
        reorderer.drop()

        # Reset should restore original order
        reorderer.reset()

        assert reorderer.get_ordered_images() == sample_images
        assert reorderer.get_current_index() == 0
        assert not reorderer.is_grabbed()

    def test_complex_reordering_sequence(self, sample_images):
        """Test a complex sequence of reordering operations."""
        reorderer = ImageReorderer(sample_images)

        # Move image1 (index 0) to position 2
        reorderer.grab()  # Grab image1
        reorderer.move_down()  # Swap with image2
        reorderer.move_down()  # Swap with image3
        reorderer.drop()

        images = reorderer.get_ordered_images()
        assert images[0] == sample_images[1]  # image2
        assert images[1] == sample_images[2]  # image3
        assert images[2] == sample_images[0]  # image1
        assert images[3] == sample_images[3]  # image4


class TestPrefixGeneration:
    """Test filename prefix generation."""

    def test_generate_prefixed_filenames(self, sample_images):
        """Test basic prefix generation."""
        result = generate_prefixed_filenames(sample_images)

        assert len(result) == 4
        assert result[0] == (sample_images[0], "1_image1.jpg")
        assert result[1] == (sample_images[1], "2_image2.jpg")
        assert result[2] == (sample_images[2], "3_image3.jpg")
        assert result[3] == (sample_images[3], "4_image4.jpg")

    def test_prefix_padding_for_many_images(self):
        """Test that prefix padding adjusts for total count."""
        images = [Path(f"/tmp/image{i}.jpg") for i in range(1, 101)]  # 100 images

        result = generate_prefixed_filenames(images)

        # Should use 3-digit padding (001, 002, ..., 100)
        assert result[0][1] == "001_image1.jpg"
        assert result[9][1] == "010_image10.jpg"
        assert result[99][1] == "100_image100.jpg"

    def test_prefix_no_padding_for_single_digit(self):
        """Test that single digit padding is used for < 10 images."""
        images = [Path(f"/tmp/image{i}.jpg") for i in range(1, 6)]  # 5 images

        result = generate_prefixed_filenames(images)

        assert result[0][1] == "1_image1.jpg"
        assert result[4][1] == "5_image5.jpg"

    def test_prefix_preserves_original_path(self, sample_images):
        """Test that original paths are preserved in tuples."""
        result = generate_prefixed_filenames(sample_images)

        for i, (orig_path, _) in enumerate(result):
            assert orig_path == sample_images[i]


class TestFilenamePreview:
    """Test filename preview generation."""

    def test_preview_few_images(self):
        """Test preview with few images."""
        images = [Path(f"/tmp/image{i}.jpg") for i in range(1, 4)]

        preview = get_final_filenames_preview(images)

        assert preview == "1_image1.jpg → 2_image2.jpg → 3_image3.jpg"

    def test_preview_many_images(self):
        """Test preview truncation for many images."""
        images = [Path(f"/tmp/image{i}.jpg") for i in range(1, 11)]  # 10 images

        preview = get_final_filenames_preview(images)

        # Should show first 3 and last 1 with ellipsis
        assert "1_image1.jpg" in preview
        assert "2_image2.jpg" in preview
        assert "3_image3.jpg" in preview
        assert "..." in preview
        assert "10_image10.jpg" in preview

    def test_preview_exactly_four_images(self):
        """Test preview with exactly 4 images (no truncation)."""
        images = [Path(f"/tmp/image{i}.jpg") for i in range(1, 5)]

        preview = get_final_filenames_preview(images)

        assert "..." not in preview
        assert all(f"{i}_image{i}.jpg" in preview for i in range(1, 5))

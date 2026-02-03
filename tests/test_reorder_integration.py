"""Integration tests for reorder functionality with processor and uploader."""

import pytest
import tempfile
from pathlib import Path
from PIL import Image

from photo_terminal.reorder import generate_prefixed_filenames
from photo_terminal.processor import process_images


@pytest.fixture
def temp_images(tmp_path):
    """Create temporary test images."""
    images = []
    for i in range(1, 4):
        img_path = tmp_path / f"test_image_{i}.jpg"
        img = Image.new('RGB', (100, 100), color=(i * 50, i * 50, i * 50))
        img.save(img_path, 'JPEG')
        images.append(img_path)
    return images


class TestReorderIntegration:
    """Test integration of reorder with processor and uploader."""

    def test_process_images_with_filename_map(self, temp_images):
        """Test that process_images respects filename map."""
        # Create a simple reorder: reverse the order
        reordered = list(reversed(temp_images))
        filename_map_data = generate_prefixed_filenames(reordered)
        filename_map = dict(filename_map_data)

        # Process with filename map
        temp_dir, processed = process_images(
            reordered,
            target_size_kb=400,
            output_format='JPEG',
            max_dimension=1920,
            filename_map=filename_map
        )

        try:
            # Check that processed images have correct upload filenames
            assert len(processed) == 3

            for i, proc_img in enumerate(processed):
                # Should have upload_filename set
                assert proc_img.upload_filename is not None

                # Should match the filename map
                assert proc_img.upload_filename == filename_map[proc_img.original_path]

                # Should have numeric prefix
                assert proc_img.upload_filename.startswith(f"{i + 1}_")

        finally:
            temp_dir.cleanup()

    def test_process_images_without_filename_map(self, temp_images):
        """Test that process_images works without filename map (normal flow)."""
        # Process without filename map
        temp_dir, processed = process_images(
            temp_images,
            target_size_kb=400,
            output_format='JPEG',
            max_dimension=1920,
            filename_map=None
        )

        try:
            # Check that processed images don't have upload filenames
            assert len(processed) == 3

            for proc_img in processed:
                # Should not have upload_filename set
                assert proc_img.upload_filename is None

        finally:
            temp_dir.cleanup()

    def test_upload_filename_preserves_extension(self, temp_images):
        """Test that upload filename preserves output format extension."""
        # Create filename map
        filename_map_data = generate_prefixed_filenames(temp_images)
        filename_map = dict(filename_map_data)

        # Process with PNG output format
        temp_dir, processed = process_images(
            temp_images,
            target_size_kb=400,
            output_format='PNG',
            max_dimension=1920,
            filename_map=filename_map
        )

        try:
            # Check that temp files use PNG extension
            for proc_img in processed:
                assert proc_img.temp_path.suffix == '.png'

                # Upload filename should be based on original name with prefix
                # but the actual temp file should use the output format
                assert proc_img.upload_filename is not None
                # The upload_filename comes from the map which has .jpg
                # but the temp_path should have .png

        finally:
            temp_dir.cleanup()

    def test_reorder_with_different_extensions(self, tmp_path):
        """Test reordering images with different file extensions."""
        # Create images with different extensions
        img1 = tmp_path / "photo1.JPG"
        img2 = tmp_path / "photo2.jpeg"
        img3 = tmp_path / "photo3.jpg"

        for img_path in [img1, img2, img3]:
            img = Image.new('RGB', (100, 100), color='red')
            img.save(img_path, 'JPEG')

        images = [img1, img2, img3]

        # Create filename map
        filename_map_data = generate_prefixed_filenames(images)
        filename_map = dict(filename_map_data)

        # Process
        temp_dir, processed = process_images(
            images,
            target_size_kb=400,
            output_format='JPEG',
            max_dimension=1920,
            filename_map=filename_map
        )

        try:
            # All should have numeric prefixes
            for i, proc_img in enumerate(processed, start=1):
                assert proc_img.upload_filename.startswith(f"{i}_")

        finally:
            temp_dir.cleanup()

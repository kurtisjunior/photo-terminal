"""Tests for image optimizer module.

Tests cover:
- Optimization with different input sizes
- Quality iteration (verify decreasing quality)
- EXIF preservation (camera, date, GPS)
- Images already under target size
- Various input formats (PNG, WEBP, GIF, etc. -> JPEG)
- Minimum quality threshold
- Missing EXIF data (should not fail)
- Corrupted images (should fail-fast)
- RGB conversion (e.g., RGBA, Grayscale)
"""

import pytest
from pathlib import Path
import tempfile
import shutil
from PIL import Image
from PIL.ExifTags import TAGS
import io

from photo_terminal.optimizer import (
    optimize_image,
    OptimizationWarning,
    QUALITY_STEPS,
    MINIMUM_QUALITY
)


@pytest.fixture
def temp_dir():
    """Create temporary directory for test files."""
    temp = tempfile.mkdtemp()
    yield Path(temp)
    shutil.rmtree(temp)


@pytest.fixture
def sample_image_rgb(temp_dir):
    """Create a sample RGB image for testing."""
    img_path = temp_dir / "sample_rgb.jpg"
    img = Image.new('RGB', (800, 600), color='blue')
    img.save(img_path, 'JPEG', quality=95)
    return img_path


@pytest.fixture
def sample_image_rgba(temp_dir):
    """Create a sample RGBA image for testing."""
    img_path = temp_dir / "sample_rgba.png"
    img = Image.new('RGBA', (800, 600), color=(255, 0, 0, 128))
    img.save(img_path, 'PNG')
    return img_path


@pytest.fixture
def sample_image_grayscale(temp_dir):
    """Create a sample grayscale image for testing."""
    img_path = temp_dir / "sample_gray.jpg"
    img = Image.new('L', (800, 600), color=128)
    img.save(img_path, 'JPEG', quality=95)
    return img_path


@pytest.fixture
def large_image_with_exif(temp_dir):
    """Create a large image with EXIF data."""
    img_path = temp_dir / "large_with_exif.jpg"

    # Create a large image with complex pattern (will be > 400KB)
    # Using a gradient pattern to make it less compressible
    img = Image.new('RGB', (3000, 2000))
    pixels = img.load()
    for i in range(img.size[0]):
        for j in range(img.size[1]):
            pixels[i, j] = (i % 256, j % 256, (i + j) % 256)

    # Create EXIF data
    exif = Image.Exif()
    # Add camera model
    exif[0x010f] = "Canon"  # Make
    exif[0x0110] = "Canon EOS 5D Mark IV"  # Model
    exif[0x9003] = "2026:01:26 10:30:00"  # DateTimeOriginal

    img.save(img_path, 'JPEG', quality=95, exif=exif.tobytes())
    return img_path


@pytest.fixture
def small_image(temp_dir):
    """Create a small image (< 400KB) for testing."""
    img_path = temp_dir / "small.jpg"
    img = Image.new('RGB', (200, 150), color='green')
    img.save(img_path, 'JPEG', quality=95)
    return img_path


@pytest.fixture
def webp_image(temp_dir):
    """Create a WEBP image for format conversion testing."""
    img_path = temp_dir / "sample.webp"
    img = Image.new('RGB', (800, 600), color='yellow')
    img.save(img_path, 'WEBP', quality=90)
    return img_path


@pytest.fixture
def png_image(temp_dir):
    """Create a PNG image for format conversion testing."""
    img_path = temp_dir / "sample.png"
    img = Image.new('RGB', (800, 600), color='purple')
    img.save(img_path, 'PNG')
    return img_path


@pytest.fixture
def gif_image(temp_dir):
    """Create a GIF image for format conversion testing."""
    img_path = temp_dir / "sample.gif"
    img = Image.new('RGB', (400, 300), color='orange')
    img.save(img_path, 'GIF')
    return img_path


class TestBasicOptimization:
    """Test basic optimization functionality."""

    def test_optimize_large_image(self, large_image_with_exif, temp_dir):
        """Test optimization of image larger than target size."""
        output_path = temp_dir / "output.jpg"

        result = optimize_image(
            large_image_with_exif,
            output_path,
            target_size_kb=400
        )

        # Check that output file was created
        assert output_path.exists()

        # Check that result contains expected keys
        assert 'original_size' in result
        assert 'final_size' in result
        assert 'quality_used' in result
        assert 'format' in result
        assert 'warnings' in result

        # Check that final size is less than target
        assert result['final_size'] <= 400 * 1024

        # Check that quality is within expected range
        assert result['quality_used'] in QUALITY_STEPS

        # Check that format was detected
        assert result['format'] == 'JPEG'

    def test_optimize_small_image(self, small_image, temp_dir):
        """Test optimization of image already smaller than target."""
        output_path = temp_dir / "output.jpg"
        original_size = small_image.stat().st_size

        result = optimize_image(
            small_image,
            output_path,
            target_size_kb=400
        )

        # Should use quality 95 for images already under target
        assert result['quality_used'] == 95
        assert result['final_size'] <= result['original_size'] or result['final_size'] <= 400 * 1024

    def test_quality_iteration(self, large_image_with_exif, temp_dir):
        """Test that quality decreases to reach target size."""
        output_path = temp_dir / "output.jpg"

        # Use a small target to force quality reduction
        result = optimize_image(
            large_image_with_exif,
            output_path,
            target_size_kb=100
        )

        # Should use a lower quality setting
        assert result['quality_used'] < 95
        assert result['quality_used'] >= MINIMUM_QUALITY


class TestExifPreservation:
    """Test EXIF data preservation."""

    def test_preserve_exif_data(self, large_image_with_exif, temp_dir):
        """Test that EXIF data is preserved during optimization."""
        output_path = temp_dir / "output.jpg"

        result = optimize_image(
            large_image_with_exif,
            output_path,
            target_size_kb=400
        )

        # Open output image and check for EXIF
        output_img = Image.open(output_path)
        exif = output_img.getexif()

        # Should have some EXIF data
        assert exif is not None
        assert len(exif) > 0

    def test_missing_exif_no_failure(self, sample_image_rgb, temp_dir):
        """Test that missing EXIF data doesn't cause failure."""
        output_path = temp_dir / "output.jpg"

        # Should not raise exception
        result = optimize_image(
            sample_image_rgb,
            output_path,
            target_size_kb=400
        )

        # Should have warning about no EXIF data
        warning_types = [w.split(':')[0] for w in result['warnings']]
        assert OptimizationWarning.NO_EXIF_DATA in warning_types


class TestFormatConversion:
    """Test conversion from various formats to JPEG."""

    def test_png_to_jpeg(self, png_image, temp_dir):
        """Test PNG to JPEG conversion."""
        output_path = temp_dir / "output.jpg"

        result = optimize_image(
            png_image,
            output_path,
            target_size_kb=400
        )

        assert output_path.exists()
        assert result['format'] == 'PNG'

        # Verify output is JPEG
        output_img = Image.open(output_path)
        assert output_img.format == 'JPEG'

    def test_webp_to_jpeg(self, webp_image, temp_dir):
        """Test WEBP to JPEG conversion."""
        output_path = temp_dir / "output.jpg"

        result = optimize_image(
            webp_image,
            output_path,
            target_size_kb=400
        )

        assert output_path.exists()
        assert result['format'] == 'WEBP'

        # Verify output is JPEG
        output_img = Image.open(output_path)
        assert output_img.format == 'JPEG'

    def test_gif_to_jpeg(self, gif_image, temp_dir):
        """Test GIF to JPEG conversion."""
        output_path = temp_dir / "output.jpg"

        result = optimize_image(
            gif_image,
            output_path,
            target_size_kb=400
        )

        assert output_path.exists()
        assert result['format'] == 'GIF'

        # Verify output is JPEG
        output_img = Image.open(output_path)
        assert output_img.format == 'JPEG'


class TestColorSpaceConversion:
    """Test RGB conversion for different color spaces."""

    def test_rgba_to_rgb(self, sample_image_rgba, temp_dir):
        """Test RGBA to RGB conversion (composites on white)."""
        output_path = temp_dir / "output.jpg"

        result = optimize_image(
            sample_image_rgba,
            output_path,
            target_size_kb=400
        )

        assert output_path.exists()

        # Verify output is RGB
        output_img = Image.open(output_path)
        assert output_img.mode == 'RGB'

    def test_grayscale_to_rgb(self, sample_image_grayscale, temp_dir):
        """Test grayscale to RGB conversion."""
        output_path = temp_dir / "output.jpg"

        result = optimize_image(
            sample_image_grayscale,
            output_path,
            target_size_kb=400
        )

        assert output_path.exists()

        # Verify output is RGB
        output_img = Image.open(output_path)
        assert output_img.mode == 'RGB'


class TestMinimumQuality:
    """Test minimum quality threshold behavior."""

    def test_minimum_quality_threshold(self, large_image_with_exif, temp_dir):
        """Test that quality doesn't go below minimum threshold."""
        output_path = temp_dir / "output.jpg"

        # Use unrealistically small target to force minimum quality
        result = optimize_image(
            large_image_with_exif,
            output_path,
            target_size_kb=10
        )

        # Should use minimum quality
        assert result['quality_used'] == MINIMUM_QUALITY

        # Should have warning about not reaching target
        warning_types = [w.split(':')[0] for w in result['warnings']]
        assert OptimizationWarning.TARGET_NOT_REACHED in warning_types

    def test_target_not_reached_warning(self, large_image_with_exif, temp_dir):
        """Test warning when target size cannot be reached."""
        output_path = temp_dir / "output.jpg"

        result = optimize_image(
            large_image_with_exif,
            output_path,
            target_size_kb=10
        )

        # Should have target not reached warning
        assert any(OptimizationWarning.TARGET_NOT_REACHED in w for w in result['warnings'])

        # Warning should include size information
        warning_text = next(w for w in result['warnings'] if OptimizationWarning.TARGET_NOT_REACHED in w)
        assert 'KB' in warning_text
        assert str(MINIMUM_QUALITY) in warning_text


class TestErrorHandling:
    """Test error handling and fail-fast behavior."""

    def test_input_file_not_found(self, temp_dir):
        """Test error when input file doesn't exist."""
        input_path = temp_dir / "nonexistent.jpg"
        output_path = temp_dir / "output.jpg"

        with pytest.raises(FileNotFoundError):
            optimize_image(input_path, output_path)

    def test_corrupted_image_fails_fast(self, temp_dir):
        """Test that corrupted images cause immediate failure."""
        # Create a corrupted image file
        corrupted_path = temp_dir / "corrupted.jpg"
        with open(corrupted_path, 'wb') as f:
            f.write(b'Not a valid image file')

        output_path = temp_dir / "output.jpg"

        with pytest.raises(ValueError) as exc_info:
            optimize_image(corrupted_path, output_path)

        assert "Cannot open image file" in str(exc_info.value)

    def test_invalid_output_directory(self, sample_image_rgb, temp_dir):
        """Test error when output directory doesn't exist."""
        output_path = temp_dir / "nonexistent_dir" / "output.jpg"

        with pytest.raises(IOError):
            optimize_image(sample_image_rgb, output_path)


class TestTargetSizeConfiguration:
    """Test different target size configurations."""

    def test_custom_target_size(self, large_image_with_exif, temp_dir):
        """Test optimization with custom target size."""
        output_path = temp_dir / "output.jpg"

        result = optimize_image(
            large_image_with_exif,
            output_path,
            target_size_kb=200
        )

        # Should be under 200KB (or close if minimum quality reached)
        if OptimizationWarning.TARGET_NOT_REACHED not in [w.split(':')[0] for w in result['warnings']]:
            assert result['final_size'] <= 200 * 1024

    def test_large_target_size(self, sample_image_rgb, temp_dir):
        """Test with target size larger than original."""
        output_path = temp_dir / "output.jpg"

        result = optimize_image(
            sample_image_rgb,
            output_path,
            target_size_kb=5000  # 5MB
        )

        # Should use quality 95 since image is smaller than target
        assert result['quality_used'] == 95


class TestAspectRatioPreservation:
    """Test that aspect ratio is preserved."""

    def test_dimensions_preserved(self, large_image_with_exif, temp_dir):
        """Test that image dimensions are not changed."""
        output_path = temp_dir / "output.jpg"

        # Get original dimensions
        with Image.open(large_image_with_exif) as img:
            original_size = img.size

        optimize_image(
            large_image_with_exif,
            output_path,
            target_size_kb=400
        )

        # Check output dimensions
        with Image.open(output_path) as img:
            output_size = img.size

        # Dimensions should be exactly the same
        assert original_size == output_size


class TestReturnedMetadata:
    """Test the metadata returned by optimize_image."""

    def test_return_dict_structure(self, sample_image_rgb, temp_dir):
        """Test that return dictionary has expected structure."""
        output_path = temp_dir / "output.jpg"

        result = optimize_image(
            sample_image_rgb,
            output_path,
            target_size_kb=400
        )

        # Check all required keys present
        assert 'original_size' in result
        assert 'final_size' in result
        assert 'quality_used' in result
        assert 'format' in result
        assert 'warnings' in result

        # Check types
        assert isinstance(result['original_size'], int)
        assert isinstance(result['final_size'], int)
        assert isinstance(result['quality_used'], int)
        assert isinstance(result['format'], str)
        assert isinstance(result['warnings'], list)

    def test_size_reporting(self, large_image_with_exif, temp_dir):
        """Test that sizes are reported correctly."""
        output_path = temp_dir / "output.jpg"
        original_size = large_image_with_exif.stat().st_size

        result = optimize_image(
            large_image_with_exif,
            output_path,
            target_size_kb=400
        )

        # Original size should match file size
        assert result['original_size'] == original_size

        # Final size should match output file size
        assert result['final_size'] == output_path.stat().st_size

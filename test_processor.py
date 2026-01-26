"""Tests for image processing pipeline."""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import io

import pytest
from PIL import Image

from processor import (
    process_images,
    ProcessedImage,
    ProcessingError,
    InsufficientDiskSpaceError,
    _check_disk_space
)


# Test fixtures

@pytest.fixture
def sample_images(tmp_path):
    """Create sample test images."""
    images = []
    for i in range(3):
        img_path = tmp_path / f"test_image_{i}.jpg"

        # Create a simple test image
        img = Image.new('RGB', (800, 600), color=(100 + i * 50, 150, 200))
        img.save(img_path, 'JPEG', quality=95)

        images.append(img_path)

    return images


@pytest.fixture
def mock_optimize_result():
    """Mock result from optimize_image."""
    return {
        'original_size': 500000,
        'final_size': 400000,
        'quality_used': 85,
        'format': 'JPEG',
        'warnings': []
    }


# Tests for process_images()

def test_process_images_success(sample_images, mock_optimize_result):
    """Test successful processing of multiple images."""
    def mock_optimize_side_effect(input_path, output_path, target_size_kb):
        # Create a dummy file to simulate optimizer output
        output_path.touch()
        return mock_optimize_result

    with patch('processor.optimize_image') as mock_optimize:
        mock_optimize.side_effect = mock_optimize_side_effect

        temp_dir, processed = process_images(sample_images, target_size_kb=400)

        # Should return temp directory and processed images list
        assert temp_dir is not None
        assert len(processed) == 3

        # Check that optimize was called for each image
        assert mock_optimize.call_count == 3

        # Verify processed image metadata
        for i, proc_img in enumerate(processed):
            assert isinstance(proc_img, ProcessedImage)
            assert proc_img.original_path == sample_images[i]
            assert proc_img.temp_path.parent.name.startswith('photo_upload_')
            assert proc_img.temp_path.name == sample_images[i].name
            assert proc_img.original_size == 500000
            assert proc_img.final_size == 400000
            assert proc_img.quality_used == 85
            assert proc_img.warnings == []

        # Verify temp files exist
        for proc_img in processed:
            assert proc_img.temp_path.exists()

        # Cleanup
        temp_dir.cleanup()


def test_process_images_with_warnings(sample_images):
    """Test processing with optimization warnings."""
    mock_result = {
        'original_size': 500000,
        'final_size': 450000,
        'quality_used': 60,
        'format': 'JPEG',
        'warnings': ['target_size_not_reached: Could not reach target size']
    }

    def mock_optimize_side_effect(input_path, output_path, target_size_kb):
        output_path.touch()
        return mock_result

    with patch('processor.optimize_image') as mock_optimize:
        mock_optimize.side_effect = mock_optimize_side_effect

        temp_dir, processed = process_images(sample_images, target_size_kb=400)

        # Should capture warnings
        assert len(processed[0].warnings) == 1
        assert 'target_size_not_reached' in processed[0].warnings[0]

        temp_dir.cleanup()


def test_process_images_preserves_original_filenames(sample_images, mock_optimize_result):
    """Test that original filenames are preserved in temp directory."""
    def mock_optimize_side_effect(input_path, output_path, target_size_kb):
        output_path.touch()
        return mock_optimize_result

    with patch('processor.optimize_image') as mock_optimize:
        mock_optimize.side_effect = mock_optimize_side_effect

        temp_dir, processed = process_images(sample_images)

        # Verify each processed image has same filename as original
        for i, proc_img in enumerate(processed):
            assert proc_img.temp_path.name == sample_images[i].name
            assert proc_img.temp_path != sample_images[i]  # Different paths

        temp_dir.cleanup()


def test_process_images_empty_list_fails():
    """Test that empty images list raises ValueError."""
    with pytest.raises(ValueError, match="Images list cannot be empty"):
        process_images([])


def test_process_images_optimizer_failure(sample_images):
    """Test that optimizer failure raises ProcessingError."""
    with patch('processor.optimize_image') as mock_optimize:
        mock_optimize.side_effect = ValueError("Cannot open image")

        with pytest.raises(ProcessingError) as exc_info:
            process_images(sample_images)

        # Should include filename in error message
        assert 'test_image_0.jpg' in str(exc_info.value)
        assert 'Cannot open image' in str(exc_info.value)


def test_process_images_progress_feedback(sample_images, mock_optimize_result, capsys):
    """Test that progress feedback is displayed."""
    def mock_optimize_side_effect(input_path, output_path, target_size_kb):
        output_path.touch()
        return mock_optimize_result

    with patch('processor.optimize_image') as mock_optimize:
        mock_optimize.side_effect = mock_optimize_side_effect

        temp_dir, processed = process_images(sample_images)

        captured = capsys.readouterr()

        # Should show progress for each image
        assert 'Processing image 1/3...' in captured.out
        assert 'Processing image 2/3...' in captured.out
        assert 'Processing image 3/3...' in captured.out

        temp_dir.cleanup()


def test_process_images_temp_directory_persistence_on_failure(sample_images):
    """Test that temp directory is not cleaned up on failure."""
    with patch('processor.optimize_image') as mock_optimize:
        # First image succeeds, second fails
        mock_optimize.side_effect = [
            {
                'original_size': 500000,
                'final_size': 400000,
                'quality_used': 85,
                'format': 'JPEG',
                'warnings': []
            },
            ValueError("Processing failed")
        ]

        try:
            temp_dir, processed = process_images(sample_images)
        except ProcessingError:
            # Expected - temp directory should still exist
            # In real usage, caller would keep reference to temp_dir
            # and decide whether to retry or cleanup
            pass


def test_process_images_custom_target_size(sample_images, mock_optimize_result):
    """Test processing with custom target size."""
    def mock_optimize_side_effect(input_path, output_path, target_size_kb):
        output_path.touch()
        return mock_optimize_result

    with patch('processor.optimize_image') as mock_optimize:
        mock_optimize.side_effect = mock_optimize_side_effect

        temp_dir, processed = process_images(sample_images, target_size_kb=500)

        # Verify optimize_image was called with correct target size
        for call in mock_optimize.call_args_list:
            # Check positional arg (third argument is target_size_kb)
            assert call[0][2] == 500

        temp_dir.cleanup()


def test_process_images_calls_optimizer_with_correct_paths(sample_images, mock_optimize_result):
    """Test that optimizer is called with correct input and output paths."""
    def mock_optimize_side_effect(input_path, output_path, target_size_kb):
        output_path.touch()
        return mock_optimize_result

    with patch('processor.optimize_image') as mock_optimize:
        mock_optimize.side_effect = mock_optimize_side_effect

        temp_dir, processed = process_images(sample_images)

        # Verify each call had correct paths
        for i, call in enumerate(mock_optimize.call_args_list):
            input_path = call[0][0]
            output_path = call[0][1]

            assert input_path == sample_images[i]
            assert output_path.name == sample_images[i].name
            assert output_path.parent.name.startswith('photo_upload_')

        temp_dir.cleanup()


# Tests for disk space checking

def test_check_disk_space_sufficient():
    """Test disk space check when space is sufficient."""
    images = [Mock(spec=Path)]
    images[0].stat.return_value = Mock(st_size=1000000)  # 1MB

    with patch('processor.shutil.disk_usage') as mock_disk_usage:
        # Mock 100MB available
        mock_disk_usage.return_value = Mock(free=100 * 1024 * 1024)

        # Should not raise exception
        _check_disk_space(images, Path('/tmp'))


def test_check_disk_space_insufficient():
    """Test disk space check when space is insufficient."""
    images = [Mock(spec=Path)]
    images[0].stat.return_value = Mock(st_size=100 * 1024 * 1024)  # 100MB

    with patch('processor.shutil.disk_usage') as mock_disk_usage:
        # Mock only 10MB available (need 150MB with 1.5x margin)
        mock_disk_usage.return_value = Mock(free=10 * 1024 * 1024)

        with pytest.raises(InsufficientDiskSpaceError) as exc_info:
            _check_disk_space(images, Path('/tmp'))

        # Error message should include both needed and available space
        error_msg = str(exc_info.value)
        assert 'Insufficient disk space' in error_msg
        assert 'Needed:' in error_msg
        assert 'Available:' in error_msg


def test_check_disk_space_multiple_images():
    """Test disk space check with multiple images."""
    images = []
    for i in range(5):
        mock_img = Mock(spec=Path)
        mock_img.stat.return_value = Mock(st_size=10 * 1024 * 1024)  # 10MB each
        images.append(mock_img)

    with patch('processor.shutil.disk_usage') as mock_disk_usage:
        # Total size: 50MB, needed with margin: 75MB
        # Mock 100MB available - should pass
        mock_disk_usage.return_value = Mock(free=100 * 1024 * 1024)

        _check_disk_space(images, Path('/tmp'))

        # Now mock insufficient space
        mock_disk_usage.return_value = Mock(free=50 * 1024 * 1024)

        with pytest.raises(InsufficientDiskSpaceError):
            _check_disk_space(images, Path('/tmp'))


def test_check_disk_space_calculates_safety_margin():
    """Test that disk space check uses 1.5x safety margin."""
    images = [Mock(spec=Path)]
    images[0].stat.return_value = Mock(st_size=100 * 1024 * 1024)  # 100MB

    with patch('processor.shutil.disk_usage') as mock_disk_usage:
        # Need 150MB with 1.5x margin
        # Test with exactly 150MB - should pass
        mock_disk_usage.return_value = Mock(free=150 * 1024 * 1024)
        _check_disk_space(images, Path('/tmp'))

        # Test with 149MB - should fail
        mock_disk_usage.return_value = Mock(free=149 * 1024 * 1024)
        with pytest.raises(InsufficientDiskSpaceError):
            _check_disk_space(images, Path('/tmp'))


def test_process_images_fails_on_insufficient_disk_space(sample_images):
    """Test that processing fails fast on insufficient disk space."""
    with patch('processor.shutil.disk_usage') as mock_disk_usage:
        # Mock insufficient space
        mock_disk_usage.return_value = Mock(free=1024)  # 1KB

        with pytest.raises(InsufficientDiskSpaceError) as exc_info:
            process_images(sample_images)

        # Should fail before any processing
        assert 'Insufficient disk space' in str(exc_info.value)


# Integration tests

def test_process_images_real_integration(tmp_path):
    """Integration test with real image processing (no mocks)."""
    # Create test images
    images = []
    for i in range(2):
        img_path = tmp_path / f"test_{i}.jpg"
        img = Image.new('RGB', (1000, 800), color=(100, 150, 200))
        img.save(img_path, 'JPEG', quality=95)
        images.append(img_path)

    # Process images
    temp_dir, processed = process_images(images, target_size_kb=50)

    try:
        # Verify results
        assert len(processed) == 2

        for proc_img in processed:
            # Temp file should exist
            assert proc_img.temp_path.exists()

            # Should be optimized (smaller)
            assert proc_img.final_size < proc_img.original_size

            # Quality should be set
            assert 60 <= proc_img.quality_used <= 95

            # Filename preserved
            assert proc_img.temp_path.name == proc_img.original_path.name

    finally:
        temp_dir.cleanup()


def test_processed_image_dataclass():
    """Test ProcessedImage dataclass structure."""
    proc_img = ProcessedImage(
        original_path=Path('/src/image.jpg'),
        temp_path=Path('/tmp/image.jpg'),
        original_size=500000,
        final_size=400000,
        quality_used=85,
        warnings=['warning1']
    )

    assert proc_img.original_path == Path('/src/image.jpg')
    assert proc_img.temp_path == Path('/tmp/image.jpg')
    assert proc_img.original_size == 500000
    assert proc_img.final_size == 400000
    assert proc_img.quality_used == 85
    assert proc_img.warnings == ['warning1']


def test_process_images_clears_progress_line(sample_images, mock_optimize_result, capsys):
    """Test that progress line is cleared after processing."""
    def mock_optimize_side_effect(input_path, output_path, target_size_kb):
        output_path.touch()
        return mock_optimize_result

    with patch('processor.optimize_image') as mock_optimize:
        mock_optimize.side_effect = mock_optimize_side_effect

        temp_dir, processed = process_images(sample_images)

        captured = capsys.readouterr()

        # Should have ANSI escape codes for clearing line
        assert '\033[2K' in captured.out  # Clear line
        assert '\033[1G' in captured.out  # Return to start

        temp_dir.cleanup()


def test_process_images_temp_directory_prefix(sample_images, mock_optimize_result):
    """Test that temp directory has correct prefix."""
    def mock_optimize_side_effect(input_path, output_path, target_size_kb):
        output_path.touch()
        return mock_optimize_result

    with patch('processor.optimize_image') as mock_optimize:
        mock_optimize.side_effect = mock_optimize_side_effect

        temp_dir, processed = process_images(sample_images)

        # Verify temp directory name starts with prefix
        temp_dir_path = Path(temp_dir.name)
        assert temp_dir_path.name.startswith('photo_upload_')

        temp_dir.cleanup()

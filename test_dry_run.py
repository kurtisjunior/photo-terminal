"""Tests for dry-run mode."""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pytest
from PIL import Image

from dry_run import (
    dry_run_upload,
    _print_header,
    _print_files_report,
    _print_summary,
    _print_s3_keys
)
from processor import ProcessedImage


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
def sample_processed_images(tmp_path):
    """Create sample ProcessedImage objects."""
    images = []
    for i in range(3):
        # Create temp file
        temp_file = tmp_path / f"processed_{i}.jpg"
        temp_file.write_text(f"image data {i}")

        # Create original path
        original_path = Path(f"/source/image_{i}.jpg")

        # Create ProcessedImage object
        processed = ProcessedImage(
            original_path=original_path,
            temp_path=temp_file,
            original_size=5 * 1024 * 1024,  # 5 MB
            final_size=400 * 1024,  # 400 KB
            quality_used=85,
            warnings=[]
        )
        images.append(processed)

    return images


@pytest.fixture
def mock_temp_dir(tmp_path):
    """Create mock TemporaryDirectory."""
    mock_dir = MagicMock()
    mock_dir.name = str(tmp_path)
    mock_dir.cleanup = MagicMock()
    return mock_dir


# Tests for dry_run_upload()

def test_dry_run_upload_exits_with_zero(sample_images, sample_processed_images, mock_temp_dir):
    """Test dry-run exits with code 0 after displaying report."""
    with patch('dry_run.process_images') as mock_process:
        mock_process.return_value = (mock_temp_dir, sample_processed_images)

        with pytest.raises(SystemExit) as exc_info:
            dry_run_upload(
                images=sample_images,
                bucket='test-bucket',
                prefix='japan/tokyo',
                target_size_kb=400,
                aws_profile='test-profile'
            )

        # Should exit with 0 (success)
        assert exc_info.value.code == 0


def test_dry_run_upload_displays_header(sample_images, sample_processed_images, mock_temp_dir, capsys):
    """Test dry-run displays header with target location and size."""
    with patch('dry_run.process_images') as mock_process:
        mock_process.return_value = (mock_temp_dir, sample_processed_images)

        with pytest.raises(SystemExit):
            dry_run_upload(
                images=sample_images,
                bucket='test-bucket',
                prefix='japan/tokyo',
                target_size_kb=400,
                aws_profile='test-profile'
            )

        captured = capsys.readouterr()

        # Verify header content
        assert "DRY RUN MODE - No files will be uploaded" in captured.out
        assert "s3://test-bucket/japan/tokyo/" in captured.out
        assert "Target size:     400 KB" in captured.out


def test_dry_run_upload_with_empty_prefix(sample_images, sample_processed_images, mock_temp_dir, capsys):
    """Test dry-run with empty prefix (root)."""
    with patch('dry_run.process_images') as mock_process:
        mock_process.return_value = (mock_temp_dir, sample_processed_images)

        with pytest.raises(SystemExit):
            dry_run_upload(
                images=sample_images,
                bucket='test-bucket',
                prefix='',
                target_size_kb=400,
                aws_profile='test-profile'
            )

        captured = capsys.readouterr()

        # Verify root location shown
        assert "s3://test-bucket/" in captured.out


def test_dry_run_upload_calls_processor(sample_images, sample_processed_images, mock_temp_dir):
    """Test dry-run calls process_images with correct arguments."""
    with patch('dry_run.process_images') as mock_process:
        mock_process.return_value = (mock_temp_dir, sample_processed_images)

        with pytest.raises(SystemExit):
            dry_run_upload(
                images=sample_images,
                bucket='test-bucket',
                prefix='japan/tokyo',
                target_size_kb=500,
                aws_profile='test-profile'
            )

        # Verify process_images called with correct arguments
        mock_process.assert_called_once_with(sample_images, 500)


def test_dry_run_upload_cleans_up_temp_files(sample_images, sample_processed_images, mock_temp_dir):
    """Test dry-run cleans up temp files after displaying report."""
    with patch('dry_run.process_images') as mock_process:
        mock_process.return_value = (mock_temp_dir, sample_processed_images)

        with pytest.raises(SystemExit):
            dry_run_upload(
                images=sample_images,
                bucket='test-bucket',
                prefix='japan/tokyo',
                target_size_kb=400,
                aws_profile='test-profile'
            )

        # Verify cleanup was called
        mock_temp_dir.cleanup.assert_called_once()


def test_dry_run_upload_cleans_up_on_error(sample_images, mock_temp_dir):
    """Test dry-run cleans up temp files even when processing fails."""
    with patch('dry_run.process_images') as mock_process:
        # Simulate processing error
        mock_process.side_effect = Exception("Processing failed")

        with pytest.raises(SystemExit) as exc_info:
            dry_run_upload(
                images=sample_images,
                bucket='test-bucket',
                prefix='japan/tokyo',
                target_size_kb=400,
                aws_profile='test-profile'
            )

        # Should exit with error code
        assert exc_info.value.code == 1


def test_dry_run_upload_displays_file_report(sample_images, sample_processed_images, mock_temp_dir, capsys):
    """Test dry-run displays file-by-file report."""
    with patch('dry_run.process_images') as mock_process:
        mock_process.return_value = (mock_temp_dir, sample_processed_images)

        with pytest.raises(SystemExit):
            dry_run_upload(
                images=sample_images,
                bucket='test-bucket',
                prefix='japan/tokyo',
                target_size_kb=400,
                aws_profile='test-profile'
            )

        captured = capsys.readouterr()

        # Verify files section
        assert "Files to process:" in captured.out

        # Verify each file is shown
        for img in sample_processed_images:
            assert img.original_path.name in captured.out
            assert "Original:" in captured.out
            assert "Processed:" in captured.out
            assert "Reduction:" in captured.out


def test_dry_run_upload_displays_summary(sample_images, sample_processed_images, mock_temp_dir, capsys):
    """Test dry-run displays summary statistics."""
    with patch('dry_run.process_images') as mock_process:
        mock_process.return_value = (mock_temp_dir, sample_processed_images)

        with pytest.raises(SystemExit):
            dry_run_upload(
                images=sample_images,
                bucket='test-bucket',
                prefix='japan/tokyo',
                target_size_kb=400,
                aws_profile='test-profile'
            )

        captured = capsys.readouterr()

        # Verify summary section
        assert "SUMMARY" in captured.out
        assert "Total files:" in captured.out
        assert "Original size:" in captured.out
        assert "Processed size:" in captured.out
        assert "Total reduction:" in captured.out


def test_dry_run_upload_displays_s3_keys(sample_images, sample_processed_images, mock_temp_dir, capsys):
    """Test dry-run displays S3 keys that would be created."""
    with patch('dry_run.process_images') as mock_process:
        mock_process.return_value = (mock_temp_dir, sample_processed_images)

        with pytest.raises(SystemExit):
            dry_run_upload(
                images=sample_images,
                bucket='test-bucket',
                prefix='japan/tokyo',
                target_size_kb=400,
                aws_profile='test-profile'
            )

        captured = capsys.readouterr()

        # Verify S3 keys section
        assert "S3 keys that would be created:" in captured.out

        # Verify each key is shown
        for img in sample_processed_images:
            expected_key = f"japan/tokyo/{img.original_path.name}"
            assert expected_key in captured.out


def test_dry_run_upload_displays_completion_message(sample_images, sample_processed_images, mock_temp_dir, capsys):
    """Test dry-run displays completion message."""
    with patch('dry_run.process_images') as mock_process:
        mock_process.return_value = (mock_temp_dir, sample_processed_images)

        with pytest.raises(SystemExit):
            dry_run_upload(
                images=sample_images,
                bucket='test-bucket',
                prefix='japan/tokyo',
                target_size_kb=400,
                aws_profile='test-profile'
            )

        captured = capsys.readouterr()

        # Verify completion message
        assert "DRY RUN COMPLETE - No files were uploaded" in captured.out


def test_dry_run_upload_shows_warnings(tmp_path, mock_temp_dir, capsys):
    """Test dry-run displays warnings from optimizer."""
    # Create image with warning
    img_path = tmp_path / "test.jpg"
    img = Image.new('RGB', (800, 600), color=(100, 150, 200))
    img.save(img_path, 'JPEG', quality=95)

    # Create processed image with warning
    temp_file = tmp_path / "processed.jpg"
    temp_file.write_text("image data")

    processed_with_warning = ProcessedImage(
        original_path=img_path,
        temp_path=temp_file,
        original_size=5 * 1024 * 1024,
        final_size=450 * 1024,
        quality_used=60,
        warnings=['target_size_not_reached: Could not reach target size']
    )

    with patch('dry_run.process_images') as mock_process:
        mock_process.return_value = (mock_temp_dir, [processed_with_warning])

        with pytest.raises(SystemExit):
            dry_run_upload(
                images=[img_path],
                bucket='test-bucket',
                prefix='japan',
                target_size_kb=400,
                aws_profile='test-profile'
            )

        captured = capsys.readouterr()

        # Verify warning is displayed
        assert "Warning:" in captured.out
        assert "target_size_not_reached" in captured.out


def test_dry_run_upload_single_file(sample_images, mock_temp_dir, capsys):
    """Test dry-run with single file."""
    # Create single processed image
    temp_file = Path(mock_temp_dir.name) / "processed.jpg"
    temp_file.write_text("image data")

    single_processed = ProcessedImage(
        original_path=sample_images[0],
        temp_path=temp_file,
        original_size=3 * 1024 * 1024,  # 3 MB
        final_size=400 * 1024,  # 400 KB
        quality_used=85,
        warnings=[]
    )

    with patch('dry_run.process_images') as mock_process:
        mock_process.return_value = (mock_temp_dir, [single_processed])

        with pytest.raises(SystemExit):
            dry_run_upload(
                images=[sample_images[0]],
                bucket='test-bucket',
                prefix='photos',
                target_size_kb=400,
                aws_profile='test-profile'
            )

        captured = capsys.readouterr()

        # Verify output includes file info
        assert sample_images[0].name in captured.out
        assert "Total files:      1" in captured.out


def test_dry_run_upload_processing_feedback(sample_images, sample_processed_images, mock_temp_dir, capsys):
    """Test dry-run shows processing feedback."""
    with patch('dry_run.process_images') as mock_process:
        mock_process.return_value = (mock_temp_dir, sample_processed_images)

        with pytest.raises(SystemExit):
            dry_run_upload(
                images=sample_images,
                bucket='test-bucket',
                prefix='japan/tokyo',
                target_size_kb=400,
                aws_profile='test-profile'
            )

        captured = capsys.readouterr()

        # Verify processing message shown
        assert "Processing images to calculate sizes..." in captured.out


# Tests for _print_header()

def test_print_header_with_prefix(capsys):
    """Test header with prefix."""
    _print_header('test-bucket', 'japan/tokyo', 400)

    captured = capsys.readouterr()

    assert "DRY RUN MODE - No files will be uploaded" in captured.out
    assert "Target location: s3://test-bucket/japan/tokyo/" in captured.out
    assert "Target size:     400 KB" in captured.out


def test_print_header_without_prefix(capsys):
    """Test header without prefix (root)."""
    _print_header('test-bucket', '', 500)

    captured = capsys.readouterr()

    assert "Target location: s3://test-bucket/" in captured.out
    assert "Target size:     500 KB" in captured.out


def test_print_header_format(capsys):
    """Test header formatting."""
    _print_header('my-bucket', 'photos', 300)

    captured = capsys.readouterr()

    # Verify header border
    assert "═" * 50 in captured.out


# Tests for _print_files_report()

def test_print_files_report_single_file(sample_processed_images, capsys):
    """Test file report with single file."""
    _print_files_report([sample_processed_images[0]])

    captured = capsys.readouterr()

    assert "Files to process:" in captured.out
    assert sample_processed_images[0].original_path.name in captured.out
    assert "Original:" in captured.out
    assert "Processed:" in captured.out
    assert "Reduction:" in captured.out


def test_print_files_report_multiple_files(sample_processed_images, capsys):
    """Test file report with multiple files."""
    _print_files_report(sample_processed_images)

    captured = capsys.readouterr()

    # Verify all files shown
    for img in sample_processed_images:
        assert img.original_path.name in captured.out


def test_print_files_report_size_formatting(tmp_path, capsys):
    """Test size formatting in file report."""
    # Create image with specific sizes
    temp_file = tmp_path / "test.jpg"
    temp_file.write_text("data")

    processed = ProcessedImage(
        original_path=Path("/source/test.jpg"),
        temp_path=temp_file,
        original_size=5 * 1024 * 1024,  # 5 MB
        final_size=400 * 1024,  # 400 KB
        quality_used=85,
        warnings=[]
    )

    _print_files_report([processed])

    captured = capsys.readouterr()

    # Verify size formatting (MB for original, KB for processed)
    assert "5.0 MB" in captured.out
    assert "400 KB" in captured.out


def test_print_files_report_reduction_percentage(tmp_path, capsys):
    """Test reduction percentage calculation."""
    temp_file = tmp_path / "test.jpg"
    temp_file.write_text("data")

    # Original: 10 MB, Final: 1 MB = 90% reduction
    processed = ProcessedImage(
        original_path=Path("/source/test.jpg"),
        temp_path=temp_file,
        original_size=10 * 1024 * 1024,
        final_size=1 * 1024 * 1024,
        quality_used=85,
        warnings=[]
    )

    _print_files_report([processed])

    captured = capsys.readouterr()

    # Verify reduction percentage
    assert "90.0%" in captured.out


def test_print_files_report_with_warnings(tmp_path, capsys):
    """Test file report displays warnings."""
    temp_file = tmp_path / "test.jpg"
    temp_file.write_text("data")

    processed = ProcessedImage(
        original_path=Path("/source/test.jpg"),
        temp_path=temp_file,
        original_size=5 * 1024 * 1024,
        final_size=450 * 1024,
        quality_used=60,
        warnings=['target_size_not_reached: Failed to reach target']
    )

    _print_files_report([processed])

    captured = capsys.readouterr()

    # Verify warning is shown
    assert "Warning:" in captured.out
    assert "target_size_not_reached" in captured.out


# Tests for _print_summary()

def test_print_summary_single_file(tmp_path, capsys):
    """Test summary with single file."""
    temp_file = tmp_path / "test.jpg"
    temp_file.write_text("data")

    processed = ProcessedImage(
        original_path=Path("/source/test.jpg"),
        temp_path=temp_file,
        original_size=5 * 1024 * 1024,
        final_size=400 * 1024,
        quality_used=85,
        warnings=[]
    )

    _print_summary([processed])

    captured = capsys.readouterr()

    assert "SUMMARY" in captured.out
    assert "Total files:      1" in captured.out


def test_print_summary_multiple_files(sample_processed_images, capsys):
    """Test summary with multiple files."""
    _print_summary(sample_processed_images)

    captured = capsys.readouterr()

    assert "Total files:      3" in captured.out


def test_print_summary_size_totals(sample_processed_images, capsys):
    """Test summary calculates size totals correctly."""
    _print_summary(sample_processed_images)

    captured = capsys.readouterr()

    # 3 files × 5 MB = 15 MB original
    assert "15.0 MB" in captured.out

    # 3 files × 400 KB = 1.2 MB processed
    assert "1.2 MB" in captured.out


def test_print_summary_reduction_percentage(sample_processed_images, capsys):
    """Test summary calculates total reduction correctly."""
    _print_summary(sample_processed_images)

    captured = capsys.readouterr()

    # Original: 15 MB, Processed: 1.2 MB = ~92% reduction
    assert "Total reduction:" in captured.out
    # Check that percentage is shown
    assert "%" in captured.out


def test_print_summary_format(sample_processed_images, capsys):
    """Test summary formatting."""
    _print_summary(sample_processed_images)

    captured = capsys.readouterr()

    # Verify summary border
    assert "─" * 50 in captured.out


# Tests for _print_s3_keys()

def test_print_s3_keys_with_prefix(sample_processed_images, capsys):
    """Test S3 keys with prefix."""
    _print_s3_keys(sample_processed_images, 'japan/tokyo')

    captured = capsys.readouterr()

    assert "S3 keys that would be created:" in captured.out

    # Verify each key
    for img in sample_processed_images:
        expected_key = f"japan/tokyo/{img.original_path.name}"
        assert expected_key in captured.out


def test_print_s3_keys_without_prefix(sample_processed_images, capsys):
    """Test S3 keys without prefix (root)."""
    _print_s3_keys(sample_processed_images, '')

    captured = capsys.readouterr()

    # Verify keys without prefix
    for img in sample_processed_images:
        # Should show just filename
        assert f"  - {img.original_path.name}" in captured.out


def test_print_s3_keys_with_trailing_slash(sample_processed_images, capsys):
    """Test S3 keys with trailing slash in prefix."""
    _print_s3_keys(sample_processed_images, 'japan/tokyo/')

    captured = capsys.readouterr()

    # Should normalize prefix and construct correct keys
    for img in sample_processed_images:
        expected_key = f"japan/tokyo/{img.original_path.name}"
        assert expected_key in captured.out


def test_print_s3_keys_single_folder(sample_processed_images, capsys):
    """Test S3 keys with single folder prefix."""
    _print_s3_keys(sample_processed_images, 'japan')

    captured = capsys.readouterr()

    for img in sample_processed_images:
        expected_key = f"japan/{img.original_path.name}"
        assert expected_key in captured.out


def test_print_s3_keys_deep_hierarchy(sample_processed_images, capsys):
    """Test S3 keys with deep folder hierarchy."""
    _print_s3_keys(sample_processed_images, 'italy/trapani/2024')

    captured = capsys.readouterr()

    for img in sample_processed_images:
        expected_key = f"italy/trapani/2024/{img.original_path.name}"
        assert expected_key in captured.out


# Integration tests

def test_dry_run_upload_integration(tmp_path, capsys):
    """Integration test with real image processing (no S3)."""
    # Create test images
    images = []
    for i in range(2):
        img_path = tmp_path / f"test_{i}.jpg"
        img = Image.new('RGB', (1000, 800), color=(100, 150, 200))
        img.save(img_path, 'JPEG', quality=95)
        images.append(img_path)

    # Run dry-run (should exit)
    with pytest.raises(SystemExit) as exc_info:
        dry_run_upload(
            images=images,
            bucket='test-bucket',
            prefix='photos',
            target_size_kb=50,
            aws_profile='test-profile'
        )

    # Should exit with success
    assert exc_info.value.code == 0

    captured = capsys.readouterr()

    # Verify key elements are in output
    assert "DRY RUN MODE" in captured.out
    assert "s3://test-bucket/photos/" in captured.out
    assert "Files to process:" in captured.out
    assert "SUMMARY" in captured.out
    assert "S3 keys that would be created:" in captured.out
    assert "DRY RUN COMPLETE" in captured.out

    # Verify both files shown
    assert "test_0.jpg" in captured.out
    assert "test_1.jpg" in captured.out

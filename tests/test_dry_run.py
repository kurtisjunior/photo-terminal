"""Tests for dry-run mode.

``dry_run_upload`` used to print its report and then raise ``SystemExit(0)``,
so every test here was a ``pytest.raises(SystemExit)`` block wrapped around a
``capsys`` scrape. It returns a report now, and the two render functions turn
that report into text, so the measurements and the presentation are asserted
separately.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from photo_terminal.dry_run import dry_run_upload, render_header, render_report
from photo_terminal.errors import PhotoTerminalError, ProcessingError
from photo_terminal.processor import ProcessedImage

# Test fixtures


@pytest.fixture
def sample_images(tmp_path):
    """Create sample test images."""
    images = []
    for i in range(3):
        img_path = tmp_path / f"test_image_{i}.jpg"

        # Create a simple test image
        img = Image.new("RGB", (800, 600), color=(100 + i * 50, 150, 200))
        img.save(img_path, "JPEG", quality=95)

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
            warnings=[],
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


def _report_for(processed_images, temp_dir, **overrides):
    """Run a dry run whose processing step is stubbed out."""
    kwargs = {
        "images": [],
        "bucket": "test-bucket",
        "prefix": "japan/tokyo",
        "target_size_kb": 400,
        "aws_profile": "test-profile",
    }
    kwargs.update(overrides)

    with patch("photo_terminal.dry_run.process_images") as mock_process:
        mock_process.return_value = (temp_dir, processed_images)
        return dry_run_upload(**kwargs)


# Tests for dry_run_upload()


def test_dry_run_upload_returns_a_report(sample_images, sample_processed_images, mock_temp_dir):
    """A dry run measures and returns. It no longer ends the process."""
    report = _report_for(sample_processed_images, mock_temp_dir, images=sample_images)

    assert report.bucket == "test-bucket"
    assert report.prefix == "japan/tokyo"
    assert report.target_size_kb == 400
    assert report.output_format == "JPEG"
    assert len(report.files) == 3


def test_dry_run_upload_measures_each_file(sample_images, sample_processed_images, mock_temp_dir):
    """Every processed image becomes one measured entry, in order."""
    report = _report_for(sample_processed_images, mock_temp_dir, images=sample_images)

    assert [f.name for f in report.files] == [
        "image_0.jpg",
        "image_1.jpg",
        "image_2.jpg",
    ]
    assert all(f.original_size == 5 * 1024 * 1024 for f in report.files)
    assert all(f.final_size == 400 * 1024 for f in report.files)


def test_dry_run_upload_records_the_s3_key_each_file_would_take(
    sample_images, sample_processed_images, mock_temp_dir
):
    report = _report_for(sample_processed_images, mock_temp_dir, images=sample_images)

    assert [f.s3_key for f in report.files] == [
        "japan/tokyo/image_0.jpg",
        "japan/tokyo/image_1.jpg",
        "japan/tokyo/image_2.jpg",
    ]


@pytest.mark.parametrize(
    ("prefix", "expected"),
    [
        ("japan/tokyo", "japan/tokyo/image_0.jpg"),
        ("japan/tokyo/", "japan/tokyo/image_0.jpg"),
        ("japan", "japan/image_0.jpg"),
        ("italy/trapani/2024", "italy/trapani/2024/image_0.jpg"),
        ("", "image_0.jpg"),
    ],
)
def test_dry_run_upload_normalises_the_prefix(
    sample_processed_images, mock_temp_dir, prefix, expected
):
    report = _report_for(sample_processed_images[:1], mock_temp_dir, prefix=prefix)

    assert report.files[0].s3_key == expected


def test_dry_run_upload_totals_the_measurements(
    sample_images, sample_processed_images, mock_temp_dir
):
    """3 x 5 MB in, 3 x 400 KB out."""
    report = _report_for(sample_processed_images, mock_temp_dir, images=sample_images)

    assert report.total_original == 15 * 1024 * 1024
    assert report.total_processed == 3 * 400 * 1024
    assert report.total_reduction_percent == pytest.approx(92.2, abs=0.1)


def test_dry_run_upload_calls_processor(sample_images, sample_processed_images, mock_temp_dir):
    """Test dry-run calls process_images with correct arguments."""
    with patch("photo_terminal.dry_run.process_images") as mock_process:
        mock_process.return_value = (mock_temp_dir, sample_processed_images)

        dry_run_upload(
            images=sample_images,
            bucket="test-bucket",
            prefix="japan/tokyo",
            target_size_kb=500,
            aws_profile="test-profile",
        )

        mock_process.assert_called_once_with(sample_images, 500, "JPEG", reporter=None)


def test_dry_run_upload_passes_the_reporter_through(
    sample_images, sample_processed_images, mock_temp_dir, reporter
):
    """Processing progress reaches the pipeline's reporter."""
    with patch("photo_terminal.dry_run.process_images") as mock_process:
        mock_process.return_value = (mock_temp_dir, sample_processed_images)

        dry_run_upload(
            images=sample_images,
            bucket="test-bucket",
            prefix="japan/tokyo",
            target_size_kb=400,
            aws_profile="test-profile",
            reporter=reporter,
        )

        assert mock_process.call_args.kwargs["reporter"] is reporter


def test_dry_run_upload_cleans_up_temp_files(sample_images, sample_processed_images, mock_temp_dir):
    """Test dry-run cleans up temp files after measuring."""
    _report_for(sample_processed_images, mock_temp_dir, images=sample_images)

    mock_temp_dir.cleanup.assert_called_once()


def test_dry_run_upload_wraps_an_untyped_processing_failure(sample_images, mock_temp_dir):
    """An unexpected failure becomes a typed error with an exit code."""
    with patch("photo_terminal.dry_run.process_images") as mock_process:
        mock_process.side_effect = Exception("Processing failed")

        with pytest.raises(PhotoTerminalError) as exc_info:
            dry_run_upload(
                images=sample_images,
                bucket="test-bucket",
                prefix="japan/tokyo",
                target_size_kb=400,
                aws_profile="test-profile",
            )

    assert "Processing failed" in exc_info.value.message
    assert exc_info.value.exit_code == 1


def test_dry_run_upload_lets_a_typed_processing_failure_through(sample_images, mock_temp_dir):
    """A ProcessingError keeps its type rather than being flattened."""
    with patch("photo_terminal.dry_run.process_images") as mock_process:
        mock_process.side_effect = ProcessingError("Failed to process image 'a.jpg'")

        with pytest.raises(ProcessingError):
            dry_run_upload(
                images=sample_images,
                bucket="test-bucket",
                prefix="japan/tokyo",
                target_size_kb=400,
                aws_profile="test-profile",
            )


def test_dry_run_upload_prints_nothing(
    sample_images, sample_processed_images, mock_temp_dir, capsys
):
    """Rendering is the pipeline's decision, so nothing is written here."""
    _report_for(sample_processed_images, mock_temp_dir, images=sample_images)

    assert capsys.readouterr().out == ""


def test_dry_run_upload_keeps_optimizer_warnings(tmp_path, mock_temp_dir):
    """Warnings travel with the file they belong to."""
    temp_file = tmp_path / "processed.jpg"
    temp_file.write_text("image data")

    processed_with_warning = ProcessedImage(
        original_path=tmp_path / "test.jpg",
        temp_path=temp_file,
        original_size=5 * 1024 * 1024,
        final_size=450 * 1024,
        quality_used=60,
        warnings=["target_size_not_reached: Could not reach target size"],
    )

    report = _report_for([processed_with_warning], mock_temp_dir, prefix="japan")

    assert report.files[0].warnings == ("target_size_not_reached: Could not reach target size",)


# Tests for render_header()


def test_render_header_with_prefix():
    """Test header with prefix."""
    header = render_header("test-bucket", "japan/tokyo", 400)

    assert "DRY RUN MODE - No files will be uploaded" in header
    assert "Target location: s3://test-bucket/japan/tokyo/" in header
    assert "Target size:     400 KB" in header
    assert "Output format:   JPEG" in header


def test_render_header_without_prefix():
    """Test header without prefix (root)."""
    header = render_header("test-bucket", "", 500)

    assert "Target location: s3://test-bucket/" in header
    assert "Target size:     500 KB" in header


@pytest.mark.parametrize("prefix", ["japan/tokyo", "japan/tokyo/", "/japan/tokyo/"])
def test_render_header_prints_one_slash_between_prefix_and_root(prefix):
    """The browser hands back a trailing slash; --prefix does not."""
    assert "Target location: s3://test-bucket/japan/tokyo/\n" in render_header(
        "test-bucket", prefix, 400
    )


def test_render_header_format():
    """Test header formatting."""
    assert "═" * 50 in render_header("my-bucket", "photos", 300)


# Tests for render_report()


def test_render_report_names_every_file(sample_processed_images, mock_temp_dir):
    report = _report_for(sample_processed_images, mock_temp_dir)
    text = render_report(report)

    assert "Files to process:" in text
    for processed in sample_processed_images:
        assert processed.original_path.name in text
    assert "Original:" in text
    assert "Processed:" in text
    assert "Reduction:" in text


def test_render_report_formats_sizes_in_mb_and_kb(tmp_path, mock_temp_dir):
    """5 MB in, 400 KB out - the units differ by column, as they always have."""
    temp_file = tmp_path / "test.jpg"
    temp_file.write_text("data")

    processed = ProcessedImage(
        original_path=Path("/source/test.jpg"),
        temp_path=temp_file,
        original_size=5 * 1024 * 1024,
        final_size=400 * 1024,
        quality_used=85,
        warnings=[],
    )

    text = render_report(_report_for([processed], mock_temp_dir))

    assert "5.0 MB" in text
    assert "400 KB" in text


def test_render_report_shows_the_reduction_percentage(tmp_path, mock_temp_dir):
    """10 MB down to 1 MB is 90%."""
    temp_file = tmp_path / "test.jpg"
    temp_file.write_text("data")

    processed = ProcessedImage(
        original_path=Path("/source/test.jpg"),
        temp_path=temp_file,
        original_size=10 * 1024 * 1024,
        final_size=1 * 1024 * 1024,
        quality_used=85,
        warnings=[],
    )

    assert "90.0%" in render_report(_report_for([processed], mock_temp_dir))


def test_render_report_shows_warnings(tmp_path, mock_temp_dir):
    temp_file = tmp_path / "test.jpg"
    temp_file.write_text("data")

    processed = ProcessedImage(
        original_path=Path("/source/test.jpg"),
        temp_path=temp_file,
        original_size=5 * 1024 * 1024,
        final_size=450 * 1024,
        quality_used=60,
        warnings=["target_size_not_reached: Failed to reach target"],
    )

    text = render_report(_report_for([processed], mock_temp_dir))

    assert "  Warning: target_size_not_reached: Failed to reach target" in text


def test_render_report_summarises_the_totals(sample_processed_images, mock_temp_dir):
    text = render_report(_report_for(sample_processed_images, mock_temp_dir))

    assert "SUMMARY" in text
    assert "─" * 50 in text
    assert "Total files:      3" in text
    assert "Original size:    15.0 MB" in text
    assert "Processed size:   1.2 MB" in text
    assert "Total reduction:  92.2%" in text


def test_render_report_summarises_a_single_file(tmp_path, mock_temp_dir):
    temp_file = tmp_path / "test.jpg"
    temp_file.write_text("data")

    processed = ProcessedImage(
        original_path=Path("/source/test.jpg"),
        temp_path=temp_file,
        original_size=5 * 1024 * 1024,
        final_size=400 * 1024,
        quality_used=85,
        warnings=[],
    )

    assert "Total files:      1" in render_report(_report_for([processed], mock_temp_dir))


def test_render_report_lists_the_s3_keys(sample_processed_images, mock_temp_dir):
    text = render_report(_report_for(sample_processed_images, mock_temp_dir))

    assert "S3 keys that would be created:" in text
    for processed in sample_processed_images:
        assert f"  - japan/tokyo/{processed.original_path.name}" in text


def test_render_report_lists_bare_filenames_at_the_root(sample_processed_images, mock_temp_dir):
    text = render_report(_report_for(sample_processed_images, mock_temp_dir, prefix=""))

    for processed in sample_processed_images:
        assert f"  - {processed.original_path.name}" in text


def test_render_report_ends_with_the_completion_line(sample_processed_images, mock_temp_dir):
    text = render_report(_report_for(sample_processed_images, mock_temp_dir))

    assert text.endswith("DRY RUN COMPLETE - No files were uploaded\n")


# Integration tests


def test_dry_run_upload_integration(tmp_path):
    """Integration test with real image processing (no S3)."""
    images = []
    for i in range(2):
        img_path = tmp_path / f"test_{i}.jpg"
        img = Image.new("RGB", (1000, 800), color=(100, 150, 200))
        img.save(img_path, "JPEG", quality=95)
        images.append(img_path)

    report = dry_run_upload(
        images=images,
        bucket="test-bucket",
        prefix="photos",
        target_size_kb=50,
        aws_profile="test-profile",
    )

    text = render_header("test-bucket", "photos", 50) + render_report(report)

    assert "DRY RUN MODE" in text
    assert "s3://test-bucket/photos/" in text
    assert "Files to process:" in text
    assert "SUMMARY" in text
    assert "S3 keys that would be created:" in text
    assert "DRY RUN COMPLETE" in text

    assert "test_0.jpg" in text
    assert "test_1.jpg" in text
    assert [f.s3_key for f in report.files] == ["photos/test_0.jpg", "photos/test_1.jpg"]

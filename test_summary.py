"""Tests for completion summary module."""

import pytest
from pathlib import Path
from io import StringIO
import sys

from summary import show_completion_summary, _format_size
from processor import ProcessedImage


@pytest.fixture
def sample_processed_images():
    """Create sample ProcessedImage objects for testing."""
    return [
        ProcessedImage(
            original_path=Path("/source/image1.jpg"),
            temp_path=Path("/tmp/image1.jpg"),
            original_size=5_000_000,  # 5 MB
            final_size=400_000,  # 400 KB
            quality_used=85,
            warnings=[]
        ),
        ProcessedImage(
            original_path=Path("/source/image2.jpg"),
            temp_path=Path("/tmp/image2.jpg"),
            original_size=8_000_000,  # 8 MB
            final_size=450_000,  # 450 KB
            quality_used=80,
            warnings=[]
        ),
        ProcessedImage(
            original_path=Path("/source/photo.png"),
            temp_path=Path("/tmp/photo.png"),
            original_size=12_000_000,  # 12 MB
            final_size=380_000,  # 380 KB
            quality_used=90,
            warnings=[]
        ),
    ]


def test_show_completion_summary_with_prefix(sample_processed_images, capsys):
    """Test completion summary with S3 prefix."""
    uploaded_keys = [
        "japan/tokyo/image1.jpg",
        "japan/tokyo/image2.jpg",
        "japan/tokyo/photo.png"
    ]

    show_completion_summary(
        processed_images=sample_processed_images,
        uploaded_keys=uploaded_keys,
        bucket="two-touch",
        prefix="japan/tokyo"
    )

    captured = capsys.readouterr()
    output = captured.out

    # Check header
    assert "UPLOAD COMPLETE" in output
    assert "═" * 50 in output

    # Check statistics
    assert "Files uploaded:    3" in output
    assert "Original size:     23.8 MB" in output
    assert "Processed size:    1.2 MB" in output or "Processed size:    1230 KB" in output
    assert "Total savings:" in output
    assert "95.1%" in output or "95.0%" in output

    # Check S3 location
    assert "Location: s3://two-touch/japan/tokyo/" in output

    # Check uploaded files list
    assert "Uploaded files:" in output
    assert "image1.jpg → japan/tokyo/image1.jpg" in output
    assert "image2.jpg → japan/tokyo/image2.jpg" in output
    assert "photo.png → japan/tokyo/photo.png" in output


def test_show_completion_summary_without_prefix(sample_processed_images, capsys):
    """Test completion summary with empty prefix (bucket root)."""
    uploaded_keys = [
        "image1.jpg",
        "image2.jpg",
        "photo.png"
    ]

    show_completion_summary(
        processed_images=sample_processed_images,
        uploaded_keys=uploaded_keys,
        bucket="two-touch",
        prefix=""
    )

    captured = capsys.readouterr()
    output = captured.out

    # Check S3 location for root
    assert "Location: s3://two-touch/" in output

    # Check uploaded files list shows simple keys
    assert "image1.jpg → image1.jpg" in output
    assert "image2.jpg → image2.jpg" in output
    assert "photo.png → photo.png" in output


def test_show_completion_summary_mismatch_lengths(sample_processed_images):
    """Test error when processed_images and uploaded_keys lengths don't match."""
    uploaded_keys = [
        "japan/tokyo/image1.jpg",
        "japan/tokyo/image2.jpg"
        # Missing third key
    ]

    with pytest.raises(ValueError) as exc_info:
        show_completion_summary(
            processed_images=sample_processed_images,
            uploaded_keys=uploaded_keys,
            bucket="two-touch",
            prefix="japan/tokyo"
        )

    assert "Mismatch" in str(exc_info.value)
    assert "3 processed images" in str(exc_info.value)
    assert "2 uploaded keys" in str(exc_info.value)


def test_show_completion_summary_single_file(capsys):
    """Test completion summary with single file."""
    processed_images = [
        ProcessedImage(
            original_path=Path("/source/single.jpg"),
            temp_path=Path("/tmp/single.jpg"),
            original_size=3_000_000,  # 3 MB
            final_size=350_000,  # 350 KB
            quality_used=85,
            warnings=[]
        )
    ]
    uploaded_keys = ["photos/single.jpg"]

    show_completion_summary(
        processed_images=processed_images,
        uploaded_keys=uploaded_keys,
        bucket="my-bucket",
        prefix="photos"
    )

    captured = capsys.readouterr()
    output = captured.out

    # Check statistics for single file
    assert "Files uploaded:    1" in output
    assert "Original size:     2.9 MB" in output or "Original size:     3.0 MB" in output
    assert "Processed size:    342 KB" in output or "Processed size:    350 KB" in output


def test_show_completion_summary_large_savings(capsys):
    """Test completion summary with large file size savings."""
    processed_images = [
        ProcessedImage(
            original_path=Path("/source/huge.jpg"),
            temp_path=Path("/tmp/huge.jpg"),
            original_size=100_000_000,  # 100 MB
            final_size=500_000,  # 500 KB
            quality_used=70,
            warnings=[]
        )
    ]
    uploaded_keys = ["huge.jpg"]

    show_completion_summary(
        processed_images=processed_images,
        uploaded_keys=uploaded_keys,
        bucket="my-bucket",
        prefix=""
    )

    captured = capsys.readouterr()
    output = captured.out

    # Check large file size
    assert "Original size:     95.4 MB" in output or "Original size:     100" in output
    assert "Total savings:" in output
    # Should show high percentage savings
    assert "99.5%" in output or "99.4%" in output


def test_format_size_bytes():
    """Test _format_size with bytes."""
    assert _format_size(500) == "500 bytes"
    assert _format_size(1000) == "1000 bytes"


def test_format_size_kilobytes():
    """Test _format_size with kilobytes."""
    assert _format_size(1024) == "1 KB"
    assert _format_size(1536) == "2 KB"
    assert _format_size(400_000) == "391 KB"
    assert _format_size(500_000) == "488 KB"


def test_format_size_megabytes():
    """Test _format_size with megabytes."""
    assert _format_size(1024 * 1024) == "1.0 MB"
    assert _format_size(5_000_000) == "4.8 MB"
    assert _format_size(10_500_000) == "10.0 MB"


def test_format_size_gigabytes():
    """Test _format_size with gigabytes."""
    assert _format_size(1024 * 1024 * 1024) == "1.0 GB"
    assert _format_size(2_500_000_000) == "2.3 GB"
    assert _format_size(5_368_709_120) == "5.0 GB"


def test_format_size_edge_cases():
    """Test _format_size edge cases."""
    # Zero bytes
    assert _format_size(0) == "0 bytes"

    # Exactly at boundaries
    assert _format_size(1023) == "1023 bytes"
    assert _format_size(1024) == "1 KB"
    assert _format_size(1024 * 1024 - 1) == "1024 KB"
    assert _format_size(1024 * 1024) == "1.0 MB"


def test_show_completion_summary_nested_prefix(capsys):
    """Test completion summary with nested prefix path."""
    processed_images = [
        ProcessedImage(
            original_path=Path("/source/pic.jpg"),
            temp_path=Path("/tmp/pic.jpg"),
            original_size=2_000_000,
            final_size=400_000,
            quality_used=85,
            warnings=[]
        )
    ]
    uploaded_keys = ["italy/trapani/beaches/pic.jpg"]

    show_completion_summary(
        processed_images=processed_images,
        uploaded_keys=uploaded_keys,
        bucket="photos",
        prefix="italy/trapani/beaches"
    )

    captured = capsys.readouterr()
    output = captured.out

    # Check nested prefix in location
    assert "Location: s3://photos/italy/trapani/beaches/" in output

    # Check full S3 key
    assert "pic.jpg → italy/trapani/beaches/pic.jpg" in output


def test_show_completion_summary_output_format(capsys):
    """Test that output format matches spec."""
    processed_images = [
        ProcessedImage(
            original_path=Path("/source/test.jpg"),
            temp_path=Path("/tmp/test.jpg"),
            original_size=1_000_000,
            final_size=400_000,
            quality_used=85,
            warnings=[]
        )
    ]
    uploaded_keys = ["test.jpg"]

    show_completion_summary(
        processed_images=processed_images,
        uploaded_keys=uploaded_keys,
        bucket="bucket",
        prefix=""
    )

    captured = capsys.readouterr()
    output = captured.out

    # Check structure matches spec format
    lines = output.strip().split('\n')

    # Should have:
    # - Empty line
    # - "UPLOAD COMPLETE"
    # - Separator line
    # - Empty line
    # - Statistics (4 lines)
    # - Empty line
    # - Location
    # - Empty line
    # - "Uploaded files:"
    # - File entries
    # - Empty line

    assert "UPLOAD COMPLETE" in lines
    assert any("═" in line for line in lines)
    assert "Files uploaded:" in output
    assert "Original size:" in output
    assert "Processed size:" in output
    assert "Total savings:" in output
    assert "Location:" in output
    assert "Uploaded files:" in output

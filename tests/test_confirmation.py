"""Tests for the confirmation text.

The summary is a string now, so these read it directly. What the user types,
and what the screen does about it, is :mod:`tests.test_confirm_screen`.
"""

import pytest

from photo_terminal.confirmation import (
    build_confirmation_prompt,
    build_confirmation_summary,
    format_s3_target,
)


@pytest.fixture
def sample_images(tmp_path):
    """Create sample image paths for testing."""
    images = []
    for i in range(3):
        img_path = tmp_path / f"test{i}.jpg"
        img_path.touch()
        images.append(img_path)
    return images


@pytest.fixture
def many_images(tmp_path):
    """Create many image paths for testing truncation."""
    images = []
    for i in range(15):
        img_path = tmp_path / f"test{i:02d}.jpg"
        img_path.touch()
        images.append(img_path)
    return images


def test_target_is_the_s3_url_for_bucket_and_prefix():
    assert format_s3_target("test-bucket", "japan/tokyo/") == "s3://test-bucket/japan/tokyo/"


def test_an_empty_prefix_targets_the_bucket_root():
    assert format_s3_target("test-bucket", "") == "s3://test-bucket/"


def test_summary_names_the_count_the_target_and_every_file(sample_images):
    summary = build_confirmation_summary(sample_images, "test-bucket", "japan/tokyo/")

    assert "Upload Confirmation" in summary
    assert "Images to upload: 3" in summary
    assert "Target location:  s3://test-bucket/japan/tokyo/" in summary
    assert "test0.jpg" in summary
    assert "test1.jpg" in summary
    assert "test2.jpg" in summary


def test_summary_shows_the_root_target_for_an_empty_prefix(sample_images):
    summary = build_confirmation_summary(sample_images, "test-bucket", "")

    assert "Target location:  s3://test-bucket/" in summary


def test_summary_truncates_past_ten_files(many_images):
    summary = build_confirmation_summary(many_images, "test-bucket", "photos/")

    assert "Images to upload: 15" in summary
    assert "Files (showing first 10):" in summary
    assert "test00.jpg" in summary
    assert "test09.jpg" in summary
    assert "... and 5 more" in summary
    assert "test14.jpg" not in summary


def test_summary_shows_exactly_ten_files_in_full(tmp_path):
    images = []
    for i in range(10):
        img_path = tmp_path / f"test{i}.jpg"
        img_path.touch()
        images.append(img_path)

    summary = build_confirmation_summary(images, "test-bucket", "photos/")

    assert "Images to upload: 10" in summary
    assert "Files:" in summary
    assert "Files (showing first 10):" not in summary
    assert "... and" not in summary
    assert "test9.jpg" in summary


def test_summary_handles_a_single_file(tmp_path):
    img_path = tmp_path / "single.jpg"
    img_path.touch()

    summary = build_confirmation_summary([img_path], "test-bucket", "photos/")

    assert "Images to upload: 1" in summary
    assert "single.jpg" in summary


def test_summary_preserves_the_order_it_was_given(tmp_path):
    images = []
    for name in ["zebra.jpg", "apple.jpg", "banana.jpg"]:
        img_path = tmp_path / name
        img_path.touch()
        images.append(img_path)

    summary = build_confirmation_summary(images, "test-bucket", "photos/")
    file_lines = [line for line in summary.split("\n") if line.strip().startswith("- ")]

    assert len(file_lines) == 3
    assert "zebra.jpg" in file_lines[0]
    assert "apple.jpg" in file_lines[1]
    assert "banana.jpg" in file_lines[2]


def test_summary_is_separated_into_sections(sample_images):
    summary = build_confirmation_summary(sample_images, "test-bucket", "japan/tokyo/")

    assert "=" * 50 in summary
    assert summary.count("\n\n") >= 2


def test_prompt_asks_about_the_count_and_the_target(sample_images):
    prompt = build_confirmation_prompt(sample_images, "test-bucket", "japan/tokyo/")

    assert prompt == "Upload 3 image(s) to s3://test-bucket/japan/tokyo/? [y/n]: "

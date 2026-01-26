"""Tests for confirmation module."""

from pathlib import Path
from unittest.mock import patch
import io

import pytest

from confirmation import confirm_upload


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


def test_confirm_upload_with_yes(sample_images, capsys):
    """Test confirmation with 'y' response."""
    with patch('builtins.input', return_value='y'):
        result = confirm_upload(sample_images, 'test-bucket', 'japan/tokyo/')

    assert result is True

    # Check output
    captured = capsys.readouterr()
    assert "Upload Confirmation" in captured.out
    assert "Images to upload: 3" in captured.out
    assert "Target location:  s3://test-bucket/japan/tokyo/" in captured.out
    assert "test0.jpg" in captured.out
    assert "test1.jpg" in captured.out
    assert "test2.jpg" in captured.out


def test_confirm_upload_with_yes_full_word(sample_images):
    """Test confirmation with 'yes' response."""
    with patch('builtins.input', return_value='yes'):
        result = confirm_upload(sample_images, 'test-bucket', 'japan/tokyo/')

    assert result is True


def test_confirm_upload_with_yes_uppercase(sample_images):
    """Test confirmation with 'Y' response (case-insensitive)."""
    with patch('builtins.input', return_value='Y'):
        result = confirm_upload(sample_images, 'test-bucket', 'japan/tokyo/')

    assert result is True


def test_confirm_upload_with_yes_mixed_case(sample_images):
    """Test confirmation with 'Yes' response (case-insensitive)."""
    with patch('builtins.input', return_value='Yes'):
        result = confirm_upload(sample_images, 'test-bucket', 'japan/tokyo/')

    assert result is True


def test_confirm_upload_with_no(sample_images, capsys):
    """Test cancellation with 'n' response."""
    with patch('builtins.input', return_value='n'):
        with pytest.raises(SystemExit) as exc_info:
            confirm_upload(sample_images, 'test-bucket', 'japan/tokyo/')

    assert exc_info.value.code == 1

    # Check output
    captured = capsys.readouterr()
    assert "Upload cancelled." in captured.out


def test_confirm_upload_with_no_full_word(sample_images):
    """Test cancellation with 'no' response."""
    with patch('builtins.input', return_value='no'):
        with pytest.raises(SystemExit) as exc_info:
            confirm_upload(sample_images, 'test-bucket', 'japan/tokyo/')

    assert exc_info.value.code == 1


def test_confirm_upload_with_no_uppercase(sample_images):
    """Test cancellation with 'N' response (case-insensitive)."""
    with patch('builtins.input', return_value='N'):
        with pytest.raises(SystemExit) as exc_info:
            confirm_upload(sample_images, 'test-bucket', 'japan/tokyo/')

    assert exc_info.value.code == 1


def test_confirm_upload_with_no_mixed_case(sample_images):
    """Test cancellation with 'No' response (case-insensitive)."""
    with patch('builtins.input', return_value='No'):
        with pytest.raises(SystemExit) as exc_info:
            confirm_upload(sample_images, 'test-bucket', 'japan/tokyo/')

    assert exc_info.value.code == 1


def test_confirm_upload_with_invalid_then_yes(sample_images, capsys):
    """Test invalid input followed by valid confirmation."""
    with patch('builtins.input', side_effect=['invalid', 'y']):
        result = confirm_upload(sample_images, 'test-bucket', 'japan/tokyo/')

    assert result is True

    # Check that invalid input message was shown
    captured = capsys.readouterr()
    assert "Invalid input" in captured.out


def test_confirm_upload_with_invalid_then_no(sample_images, capsys):
    """Test invalid input followed by cancellation."""
    with patch('builtins.input', side_effect=['maybe', 'x', 'n']):
        with pytest.raises(SystemExit) as exc_info:
            confirm_upload(sample_images, 'test-bucket', 'japan/tokyo/')

    assert exc_info.value.code == 1

    # Check that invalid input messages were shown
    captured = capsys.readouterr()
    assert captured.out.count("Invalid input") == 2


def test_confirm_upload_with_empty_input(sample_images, capsys):
    """Test empty input followed by valid response."""
    with patch('builtins.input', side_effect=['', 'y']):
        result = confirm_upload(sample_images, 'test-bucket', 'japan/tokyo/')

    assert result is True

    # Check that invalid input message was shown
    captured = capsys.readouterr()
    assert "Invalid input" in captured.out


def test_confirm_upload_with_whitespace(sample_images):
    """Test input with surrounding whitespace is handled correctly."""
    with patch('builtins.input', return_value='  y  '):
        result = confirm_upload(sample_images, 'test-bucket', 'japan/tokyo/')

    assert result is True


def test_confirm_upload_with_root_prefix(sample_images, capsys):
    """Test confirmation with empty prefix (root upload)."""
    with patch('builtins.input', return_value='y'):
        result = confirm_upload(sample_images, 'test-bucket', '')

    assert result is True

    # Check that root location is shown correctly
    captured = capsys.readouterr()
    assert "Target location:  s3://test-bucket/" in captured.out


def test_confirm_upload_with_many_files(many_images, capsys):
    """Test confirmation with many files shows truncated list."""
    with patch('builtins.input', return_value='y'):
        result = confirm_upload(many_images, 'test-bucket', 'photos/')

    assert result is True

    # Check output shows truncation
    captured = capsys.readouterr()
    assert "Images to upload: 15" in captured.out
    assert "Files (showing first 10):" in captured.out
    assert "test00.jpg" in captured.out
    assert "test09.jpg" in captured.out
    assert "... and 5 more" in captured.out
    # Files after first 10 should not be shown
    assert "test14.jpg" not in captured.out


def test_confirm_upload_with_exactly_10_files(tmp_path, capsys):
    """Test confirmation with exactly 10 files shows all without truncation."""
    images = []
    for i in range(10):
        img_path = tmp_path / f"test{i}.jpg"
        img_path.touch()
        images.append(img_path)

    with patch('builtins.input', return_value='y'):
        result = confirm_upload(images, 'test-bucket', 'photos/')

    assert result is True

    # Check output shows all files without truncation message
    captured = capsys.readouterr()
    assert "Images to upload: 10" in captured.out
    assert "Files:" in captured.out
    assert "Files (showing first 10):" not in captured.out
    assert "... and" not in captured.out
    assert "test9.jpg" in captured.out


def test_confirm_upload_with_single_file(tmp_path, capsys):
    """Test confirmation with a single file."""
    img_path = tmp_path / "single.jpg"
    img_path.touch()

    with patch('builtins.input', return_value='y'):
        result = confirm_upload([img_path], 'test-bucket', 'photos/')

    assert result is True

    # Check output
    captured = capsys.readouterr()
    assert "Images to upload: 1" in captured.out
    assert "single.jpg" in captured.out


def test_confirm_upload_with_eof(sample_images, capsys):
    """Test that EOF (Ctrl+D) is handled as cancellation."""
    with patch('builtins.input', side_effect=EOFError):
        with pytest.raises(SystemExit) as exc_info:
            confirm_upload(sample_images, 'test-bucket', 'japan/tokyo/')

    assert exc_info.value.code == 1

    # Check output
    captured = capsys.readouterr()
    assert "Upload cancelled." in captured.out


def test_confirm_upload_preserves_image_order(tmp_path, capsys):
    """Test that image order is preserved in display."""
    images = []
    names = ['zebra.jpg', 'apple.jpg', 'banana.jpg']
    for name in names:
        img_path = tmp_path / name
        img_path.touch()
        images.append(img_path)

    with patch('builtins.input', return_value='y'):
        result = confirm_upload(images, 'test-bucket', 'photos/')

    assert result is True

    # Check that files are shown in the order provided, not sorted
    captured = capsys.readouterr()
    output_lines = captured.out.split('\n')
    file_lines = [line for line in output_lines if line.strip().startswith('- ')]

    assert len(file_lines) == 3
    assert 'zebra.jpg' in file_lines[0]
    assert 'apple.jpg' in file_lines[1]
    assert 'banana.jpg' in file_lines[2]


def test_confirm_upload_displays_separator_lines(sample_images, capsys):
    """Test that confirmation displays proper formatting."""
    with patch('builtins.input', return_value='y'):
        confirm_upload(sample_images, 'test-bucket', 'japan/tokyo/')

    captured = capsys.readouterr()

    # Check for header separator
    assert "=" * 50 in captured.out
    # Check for proper section spacing
    assert captured.out.count('\n\n') >= 2

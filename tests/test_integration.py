"""Integration tests for config and CLI interaction."""

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from photo_terminal.config import load_config, Config
from photo_terminal.__main__ import main


@pytest.fixture
def folder_with_images(tmp_path):
    """Create a folder with test images."""
    img = Image.new('RGB', (100, 100), color='red')
    img.save(tmp_path / 'test1.jpg', 'JPEG')

    img2 = Image.new('RGB', (100, 100), color='blue')
    img2.save(tmp_path / 'test2.png', 'PNG')

    return tmp_path


@patch('photo_terminal.__main__.upload_images')
@patch('photo_terminal.__main__.process_images')
@patch('photo_terminal.__main__.check_for_duplicates')
@patch('photo_terminal.__main__.confirm_upload', return_value=True)
@patch('photo_terminal.__main__.browse_s3_folders', return_value='test/prefix/')
@patch('photo_terminal.tui.check_viu_availability', return_value=True)
@patch('photo_terminal.tui.ImageSelector.run')
def test_cli_integrates_with_config(mock_run, mock_viu_check, mock_browse_s3, mock_confirm, mock_check_duplicates, mock_process, mock_upload, folder_with_images, capsys):
    """Test that CLI properly integrates with config module."""
    from photo_terminal.processor import ProcessedImage
    import tempfile

    # Mock TUI to return selected images
    mock_run.return_value = [folder_with_images / 'test1.jpg']

    # Mock process_images
    mock_temp_dir = tempfile.TemporaryDirectory()
    processed_images = [
        ProcessedImage(
            original_path=folder_with_images / 'test1.jpg',
            temp_path=Path(mock_temp_dir.name) / 'test1.jpg',
            original_size=5_000_000,
            final_size=400_000,
            quality_used=85,
            warnings=[]
        )
    ]
    mock_process.return_value = (mock_temp_dir, processed_images)

    # Mock upload_images
    mock_upload.return_value = ['test/prefix/test1.jpg']

    # Mock load_config to use test config
    test_cfg = Config(
        bucket='test-bucket',
        aws_profile='test-profile',
        target_size_kb=300
    )

    test_args = ['photo_upload.py', str(folder_with_images), '--prefix', 'test/prefix']

    with patch('photo_terminal.__main__.load_config', return_value=test_cfg):
        with patch.object(sys, 'argv', test_args):
            result = main()

    assert result == 0

    # Verify config values were used
    captured = capsys.readouterr()
    assert "test-bucket" in captured.out
    assert "test-profile" in captured.out
    assert "300 KB" in captured.out
    assert "test/prefix" in captured.out

    # Cleanup
    mock_temp_dir.cleanup()


@patch('photo_terminal.__main__.upload_images')
@patch('photo_terminal.__main__.process_images')
@patch('photo_terminal.__main__.check_for_duplicates')
@patch('photo_terminal.__main__.confirm_upload', return_value=True)
@patch('photo_terminal.__main__.browse_s3_folders', return_value='test/')
@patch('photo_terminal.tui.check_viu_availability', return_value=True)
@patch('photo_terminal.tui.ImageSelector.run')
def test_cli_overrides_config_values(mock_run, mock_viu_check, mock_browse_s3, mock_confirm, mock_check_duplicates, mock_process, mock_upload, folder_with_images, capsys):
    """Test that CLI arguments override config file values."""
    from photo_terminal.processor import ProcessedImage
    import tempfile

    # Mock TUI to return selected images
    mock_run.return_value = [folder_with_images / 'test1.jpg']

    # Mock process_images
    mock_temp_dir = tempfile.TemporaryDirectory()
    processed_images = [
        ProcessedImage(
            original_path=folder_with_images / 'test1.jpg',
            temp_path=Path(mock_temp_dir.name) / 'test1.jpg',
            original_size=5_000_000,
            final_size=400_000,
            quality_used=85,
            warnings=[]
        )
    ]
    mock_process.return_value = (mock_temp_dir, processed_images)

    # Mock upload_images
    mock_upload.return_value = ['test/test1.jpg']

    test_cfg = Config(
        bucket='default-bucket',
        aws_profile='default-profile',
        target_size_kb=400
    )

    # Override target-size with CLI argument
    test_args = [
        'photo_upload.py',
        str(folder_with_images),
        '--prefix', 'test',
        '--target-size', '600'
    ]

    with patch('photo_terminal.__main__.load_config', return_value=test_cfg):
        with patch.object(sys, 'argv', test_args):
            result = main()

    assert result == 0

    # Verify CLI override was applied
    captured = capsys.readouterr()
    assert "600 KB" in captured.out  # Overridden value
    assert "400 KB" not in captured.out  # Original config value should not appear

    # Verify process_images was called with overridden target size
    mock_process.assert_called_once_with([folder_with_images / 'test1.jpg'], 600)

    # Cleanup
    mock_temp_dir.cleanup()


@patch('photo_terminal.__main__.confirm_upload', return_value=True)
@patch('photo_terminal.__main__.browse_s3_folders', return_value='test/')
@patch('photo_terminal.tui.check_viu_availability', return_value=True)
@patch('photo_terminal.tui.ImageSelector.run')
def test_dry_run_flag_integration(mock_run, mock_viu_check, mock_browse_s3, mock_confirm, folder_with_images, capsys):
    """Test that dry-run flag is properly handled."""
    # Mock TUI to return selected images
    mock_run.return_value = [folder_with_images / 'test1.jpg']

    test_cfg = Config(
        bucket='test-bucket',
        aws_profile='test-profile',
        target_size_kb=400
    )

    test_args = [
        'photo_upload.py',
        str(folder_with_images),
        '--prefix', 'test',
        '--dry-run'
    ]

    with patch('photo_terminal.__main__.load_config', return_value=test_cfg):
        with patch.object(sys, 'argv', test_args):
            result = main()

    assert result == 0

    # Verify dry-run mode is shown
    captured = capsys.readouterr()
    assert "Dry-run mode:   Yes" in captured.out

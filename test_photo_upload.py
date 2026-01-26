"""Tests for photo_upload CLI module."""

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from photo_upload import validate_folder_path, main


@pytest.fixture
def folder_with_images(tmp_path):
    """Create a folder with test images."""
    img = Image.new('RGB', (100, 100), color='red')
    img.save(tmp_path / 'test1.jpg', 'JPEG')

    img2 = Image.new('RGB', (100, 100), color='blue')
    img2.save(tmp_path / 'test2.png', 'PNG')

    return tmp_path


def test_validate_folder_path_with_valid_directory(tmp_path):
    """Test validate_folder_path with a valid directory."""
    result = validate_folder_path(str(tmp_path))
    assert result.is_dir()
    assert result.exists()


def test_validate_folder_path_with_nonexistent_path():
    """Test validate_folder_path with non-existent path."""
    with pytest.raises(SystemExit) as exc_info:
        validate_folder_path("/nonexistent/folder")
    assert exc_info.value.code == 1


def test_validate_folder_path_with_file(tmp_path):
    """Test validate_folder_path with a file instead of directory."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("test")

    with pytest.raises(SystemExit) as exc_info:
        validate_folder_path(str(test_file))
    assert exc_info.value.code == 1


@patch('photo_upload.check_for_duplicates')
@patch('photo_upload.confirm_upload', return_value=True)
@patch('s3_browser.validate_s3_access')
@patch('tui.check_viu_availability', return_value=True)
@patch('tui.ImageSelector.run')
def test_main_with_valid_folder(mock_run, mock_viu_check, mock_s3_access, mock_confirm, mock_check_duplicates, folder_with_images, capsys):
    """Test main function with valid folder."""
    # Mock TUI to return selected images
    mock_run.return_value = [folder_with_images / 'test1.jpg']

    test_args = ['photo_upload.py', str(folder_with_images), '--prefix', 'test/folder']

    with patch.object(sys, 'argv', test_args):
        result = main()

    assert result == 0

    # Check that S3 access was tested
    mock_s3_access.assert_called_once()

    # Check that configuration was printed
    captured = capsys.readouterr()
    assert "Photo Upload Manager" in captured.out
    assert "Configuration:" in captured.out
    assert str(folder_with_images) in captured.out
    assert "test/folder" in captured.out
    assert "Found 2 valid image(s)" in captured.out
    assert "Selected 1 image(s)" in captured.out
    assert "Upload target: s3://two-touch/test/folder/" in captured.out


def test_main_with_invalid_folder(capsys):
    """Test main function with invalid folder."""
    test_args = ['photo_upload.py', '/nonexistent/folder', '--prefix', 'test']

    with patch.object(sys, 'argv', test_args):
        result = main()

    assert result == 1

    # Check error message
    captured = capsys.readouterr()
    assert "Error: Folder does not exist" in captured.out


@patch('photo_upload.check_for_duplicates')
@patch('photo_upload.confirm_upload', return_value=True)
@patch('photo_upload.browse_s3_folders', return_value='')
@patch('tui.check_viu_availability', return_value=True)
@patch('tui.ImageSelector.run')
def test_main_with_target_size_override(mock_run, mock_viu_check, mock_browse_s3, mock_confirm, mock_check_duplicates, folder_with_images, capsys):
    """Test main function with target-size CLI override."""
    # Mock TUI to return selected images
    mock_run.return_value = [folder_with_images / 'test1.jpg']

    test_args = ['photo_upload.py', str(folder_with_images), '--target-size', '500']

    with patch.object(sys, 'argv', test_args):
        result = main()

    assert result == 0

    # Check that override was applied
    captured = capsys.readouterr()
    assert "Target size:    500 KB" in captured.out


@patch('photo_upload.confirm_upload', return_value=True)
@patch('s3_browser.validate_s3_access')
@patch('tui.check_viu_availability', return_value=True)
@patch('tui.ImageSelector.run')
def test_main_with_dry_run(mock_run, mock_viu_check, mock_s3_access, mock_confirm, folder_with_images, capsys):
    """Test main function with dry-run flag."""
    # Mock TUI to return selected images
    mock_run.return_value = [folder_with_images / 'test1.jpg']

    test_args = ['photo_upload.py', str(folder_with_images), '--prefix', 'test', '--dry-run']

    with patch.object(sys, 'argv', test_args):
        result = main()

    assert result == 0

    # Check that dry-run mode is shown
    captured = capsys.readouterr()
    assert "Dry-run mode:   Yes" in captured.out


@patch('photo_upload.check_for_duplicates')
@patch('photo_upload.confirm_upload', return_value=True)
@patch('photo_upload.browse_s3_folders', return_value='')
@patch('tui.check_viu_availability', return_value=True)
@patch('tui.ImageSelector.run')
def test_main_without_prefix(mock_run, mock_viu_check, mock_browse_s3, mock_confirm, mock_check_duplicates, folder_with_images, capsys):
    """Test main function without prefix argument - should trigger interactive browser."""
    # Mock TUI to return selected images
    mock_run.return_value = [folder_with_images / 'test1.jpg']

    test_args = ['photo_upload.py', str(folder_with_images)]

    with patch.object(sys, 'argv', test_args):
        result = main()

    assert result == 0

    # Check that browser was called with None (triggers interactive mode)
    mock_browse_s3.assert_called_once()
    call_args = mock_browse_s3.call_args
    assert call_args[0][2] is None  # initial_prefix should be None

    # Check that root is shown for prefix
    captured = capsys.readouterr()
    assert "S3 prefix:      (root)" in captured.out
    assert "Upload target: s3://two-touch/ (root)" in captured.out


@patch('photo_upload.check_for_duplicates')
@patch('photo_upload.confirm_upload', return_value=True)
@patch('photo_upload.browse_s3_folders', return_value='japan/tokyo/')
@patch('tui.check_viu_availability', return_value=True)
@patch('tui.ImageSelector.run')
def test_main_interactive_browser_selection(mock_run, mock_viu_check, mock_browse_s3, mock_confirm, mock_check_duplicates, folder_with_images, capsys):
    """Test main function with interactive browser returning a selected folder."""
    # Mock TUI to return selected images
    mock_run.return_value = [folder_with_images / 'test1.jpg']

    test_args = ['photo_upload.py', str(folder_with_images)]

    with patch.object(sys, 'argv', test_args):
        result = main()

    assert result == 0

    # Check that selected folder is displayed
    captured = capsys.readouterr()
    assert "Upload target: s3://two-touch/japan/tokyo/" in captured.out


@patch('photo_upload.browse_s3_folders', side_effect=SystemExit(1))
@patch('tui.check_viu_availability', return_value=True)
@patch('tui.ImageSelector.run')
def test_main_s3_access_failure(mock_run, mock_viu_check, mock_browse_s3, folder_with_images, capsys):
    """Test main function fails when S3 access test fails."""
    # Mock TUI to return selected images
    mock_run.return_value = [folder_with_images / 'test1.jpg']

    test_args = ['photo_upload.py', str(folder_with_images), '--prefix', 'test']

    with patch.object(sys, 'argv', test_args):
        result = main()

    assert result == 1


@patch('photo_upload.browse_s3_folders', side_effect=SystemExit(1))
@patch('tui.check_viu_availability', return_value=True)
@patch('tui.ImageSelector.run')
def test_main_s3_browser_cancelled(mock_run, mock_viu_check, mock_browse_s3, folder_with_images, capsys):
    """Test main function handles user cancelling S3 browser."""
    # Mock TUI to return selected images
    mock_run.return_value = [folder_with_images / 'test1.jpg']

    test_args = ['photo_upload.py', str(folder_with_images)]

    with patch.object(sys, 'argv', test_args):
        result = main()

    assert result == 1


@patch('photo_upload.check_for_duplicates')
@patch('photo_upload.confirm_upload', return_value=True)
@patch('photo_upload.browse_s3_folders', return_value='japan/tokyo/')
@patch('tui.check_viu_availability', return_value=True)
@patch('tui.ImageSelector.run')
def test_main_with_confirmation_accepted(mock_run, mock_viu_check, mock_browse_s3, mock_confirm, mock_check_duplicates, folder_with_images, capsys):
    """Test main function with user accepting confirmation."""
    # Mock TUI to return selected images
    selected_imgs = [folder_with_images / 'test1.jpg', folder_with_images / 'test2.png']
    mock_run.return_value = selected_imgs

    test_args = ['photo_upload.py', str(folder_with_images)]

    with patch.object(sys, 'argv', test_args):
        result = main()

    assert result == 0

    # Check that confirmation was called with correct arguments
    mock_confirm.assert_called_once_with(selected_imgs, 'two-touch', 'japan/tokyo/')


@patch('photo_upload.confirm_upload', side_effect=SystemExit(1))
@patch('photo_upload.browse_s3_folders', return_value='japan/tokyo/')
@patch('tui.check_viu_availability', return_value=True)
@patch('tui.ImageSelector.run')
def test_main_with_confirmation_rejected(mock_run, mock_viu_check, mock_browse_s3, mock_confirm, folder_with_images, capsys):
    """Test main function with user rejecting confirmation."""
    # Mock TUI to return selected images
    mock_run.return_value = [folder_with_images / 'test1.jpg']

    test_args = ['photo_upload.py', str(folder_with_images)]

    with patch.object(sys, 'argv', test_args):
        result = main()

    assert result == 1

    # Check that confirmation was called
    mock_confirm.assert_called_once()


@patch('photo_upload.check_for_duplicates')
@patch('photo_upload.confirm_upload', return_value=True)
@patch('photo_upload.browse_s3_folders', return_value='')
@patch('tui.check_viu_availability', return_value=True)
@patch('tui.ImageSelector.run')
def test_main_with_confirmation_root_prefix(mock_run, mock_viu_check, mock_browse_s3, mock_confirm, mock_check_duplicates, folder_with_images, capsys):
    """Test main function with confirmation for root prefix upload."""
    # Mock TUI to return selected images
    selected_imgs = [folder_with_images / 'test1.jpg']
    mock_run.return_value = selected_imgs

    test_args = ['photo_upload.py', str(folder_with_images)]

    with patch.object(sys, 'argv', test_args):
        result = main()

    assert result == 0

    # Check that confirmation was called with empty prefix
    mock_confirm.assert_called_once_with(selected_imgs, 'two-touch', '')


@patch('photo_upload.dry_run_upload')
@patch('photo_upload.confirm_upload', return_value=True)
@patch('s3_browser.validate_s3_access')
@patch('tui.check_viu_availability', return_value=True)
@patch('tui.ImageSelector.run')
def test_main_calls_dry_run_when_flag_set(mock_run, mock_viu_check, mock_s3_access, mock_confirm, mock_dry_run, folder_with_images, capsys):
    """Test main function calls dry_run_upload when --dry-run flag is set."""
    # Mock TUI to return selected images
    selected_imgs = [folder_with_images / 'test1.jpg']
    mock_run.return_value = selected_imgs

    # Mock dry_run_upload to exit with 0
    mock_dry_run.side_effect = SystemExit(0)

    test_args = ['photo_upload.py', str(folder_with_images), '--prefix', 'test/folder', '--dry-run']

    with patch.object(sys, 'argv', test_args):
        result = main()

    # dry_run_upload exits, so main should return 0
    assert result == 0

    # Verify dry_run_upload was called with correct arguments
    # Note: browse_s3_folders adds trailing slash when prefix is provided
    mock_dry_run.assert_called_once_with(
        selected_imgs,
        'two-touch',  # bucket from config
        'test/folder/',  # prefix from args (with trailing slash added by browse_s3_folders)
        400,  # default target_size_kb from config
        'kurtis-site'  # aws_profile from config
    )


@patch('photo_upload.dry_run_upload')
@patch('photo_upload.confirm_upload', return_value=True)
@patch('photo_upload.browse_s3_folders', return_value='japan/tokyo')
@patch('tui.check_viu_availability', return_value=True)
@patch('tui.ImageSelector.run')
def test_main_dry_run_with_custom_target_size(mock_run, mock_viu_check, mock_browse_s3, mock_confirm, mock_dry_run, folder_with_images, capsys):
    """Test dry-run mode respects --target-size override."""
    # Mock TUI to return selected images
    selected_imgs = [folder_with_images / 'test1.jpg']
    mock_run.return_value = selected_imgs

    # Mock dry_run_upload to exit with 0
    mock_dry_run.side_effect = SystemExit(0)

    test_args = ['photo_upload.py', str(folder_with_images), '--target-size', '500', '--dry-run']

    with patch.object(sys, 'argv', test_args):
        result = main()

    assert result == 0

    # Verify custom target size was passed to dry_run_upload
    call_args = mock_dry_run.call_args
    assert call_args[0][3] == 500  # target_size_kb parameter


@patch('photo_upload.dry_run_upload')
@patch('photo_upload.confirm_upload', return_value=True)
@patch('photo_upload.browse_s3_folders', return_value='')
@patch('tui.check_viu_availability', return_value=True)
@patch('tui.ImageSelector.run')
def test_main_dry_run_with_empty_prefix(mock_run, mock_viu_check, mock_browse_s3, mock_confirm, mock_dry_run, folder_with_images, capsys):
    """Test dry-run mode with empty prefix (root)."""
    # Mock TUI to return selected images
    selected_imgs = [folder_with_images / 'test1.jpg']
    mock_run.return_value = selected_imgs

    # Mock dry_run_upload to exit with 0
    mock_dry_run.side_effect = SystemExit(0)

    test_args = ['photo_upload.py', str(folder_with_images), '--dry-run']

    with patch.object(sys, 'argv', test_args):
        result = main()

    assert result == 0

    # Verify empty prefix was passed to dry_run_upload
    call_args = mock_dry_run.call_args
    assert call_args[0][2] == ''  # prefix parameter


@patch('photo_upload.dry_run_upload')
@patch('photo_upload.confirm_upload', return_value=True)
@patch('s3_browser.validate_s3_access')
@patch('tui.check_viu_availability', return_value=True)
@patch('tui.ImageSelector.run')
def test_main_dry_run_with_multiple_images(mock_run, mock_viu_check, mock_s3_access, mock_confirm, mock_dry_run, folder_with_images, capsys):
    """Test dry-run mode with multiple selected images."""
    # Mock TUI to return multiple images
    selected_imgs = [folder_with_images / 'test1.jpg', folder_with_images / 'test2.png']
    mock_run.return_value = selected_imgs

    # Mock dry_run_upload to exit with 0
    mock_dry_run.side_effect = SystemExit(0)

    test_args = ['photo_upload.py', str(folder_with_images), '--prefix', 'photos', '--dry-run']

    with patch.object(sys, 'argv', test_args):
        result = main()

    assert result == 0

    # Verify all images were passed to dry_run_upload
    call_args = mock_dry_run.call_args
    assert call_args[0][0] == selected_imgs
    assert len(call_args[0][0]) == 2


@patch('photo_upload.confirm_upload', return_value=True)
@patch('s3_browser.validate_s3_access')
@patch('tui.check_viu_availability', return_value=True)
@patch('tui.ImageSelector.run')
def test_main_without_dry_run_flag_does_not_call_dry_run(mock_run, mock_viu_check, mock_s3_access, mock_confirm, folder_with_images, capsys):
    """Test main function does not call dry_run_upload when flag is not set."""
    # Mock TUI to return selected images
    mock_run.return_value = [folder_with_images / 'test1.jpg']

    test_args = ['photo_upload.py', str(folder_with_images), '--prefix', 'test']

    with patch('photo_upload.dry_run_upload') as mock_dry_run:
        with patch.object(sys, 'argv', test_args):
            result = main()

        # Verify dry_run_upload was NOT called
        mock_dry_run.assert_not_called()


# Integration tests for complete workflow

@patch('photo_upload.show_completion_summary')
@patch('photo_upload.upload_images')
@patch('photo_upload.process_images')
@patch('photo_upload.check_for_duplicates')
@patch('photo_upload.confirm_upload', return_value=True)
@patch('s3_browser.validate_s3_access')
@patch('tui.check_viu_availability', return_value=True)
@patch('tui.ImageSelector.run')
def test_full_workflow_success(
    mock_run,
    mock_viu_check,
    mock_s3_access,
    mock_confirm,
    mock_check_duplicates,
    mock_process,
    mock_upload,
    mock_summary,
    folder_with_images,
    capsys
):
    """Test complete workflow from selection to upload completion."""
    from processor import ProcessedImage

    # Mock TUI to return selected images
    selected_imgs = [folder_with_images / 'test1.jpg']
    mock_run.return_value = selected_imgs

    # Mock process_images to return temp dir and processed images
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

    # Mock upload_images to return S3 keys
    uploaded_keys = ['test/test1.jpg']
    mock_upload.return_value = uploaded_keys

    test_args = ['photo_upload.py', str(folder_with_images), '--prefix', 'test']

    with patch.object(sys, 'argv', test_args):
        result = main()

    assert result == 0

    # Verify workflow order
    mock_check_duplicates.assert_called_once_with(
        selected_imgs,
        'two-touch',
        'test/',
        'kurtis-site'
    )
    mock_process.assert_called_once_with(selected_imgs, 400)
    mock_upload.assert_called_once_with(
        processed_images,
        'two-touch',
        'test/',
        'kurtis-site'
    )
    mock_summary.assert_called_once_with(
        processed_images,
        uploaded_keys,
        'two-touch',
        'test/'
    )

    # Check output messages
    captured = capsys.readouterr()
    assert "Checking for duplicate files in S3..." in captured.out
    assert "No duplicates found - proceeding with upload" in captured.out
    assert "Processing images..." in captured.out

    # Cleanup
    mock_temp_dir.cleanup()


@patch('photo_upload.check_for_duplicates')
@patch('photo_upload.confirm_upload', return_value=True)
@patch('s3_browser.validate_s3_access')
@patch('tui.check_viu_availability', return_value=True)
@patch('tui.ImageSelector.run')
def test_workflow_fails_on_duplicates(
    mock_run,
    mock_viu_check,
    mock_s3_access,
    mock_confirm,
    mock_check_duplicates,
    folder_with_images,
    capsys
):
    """Test workflow fails fast when duplicates are detected."""
    from duplicate_checker import DuplicateFilesError

    # Mock TUI to return selected images
    selected_imgs = [folder_with_images / 'test1.jpg']
    mock_run.return_value = selected_imgs

    # Mock check_for_duplicates to raise DuplicateFilesError
    mock_check_duplicates.side_effect = DuplicateFilesError(
        duplicates=['test1.jpg'],
        bucket='two-touch',
        prefix='test'
    )

    test_args = ['photo_upload.py', str(folder_with_images), '--prefix', 'test']

    with patch.object(sys, 'argv', test_args):
        result = main()

    assert result == 1

    # Verify processing and upload were NOT called
    captured = capsys.readouterr()
    assert "already exist" in captured.out
    assert "test1.jpg" in captured.out
    assert "Aborting to prevent overwrites" in captured.out


@patch('photo_upload.process_images')
@patch('photo_upload.check_for_duplicates')
@patch('photo_upload.confirm_upload', return_value=True)
@patch('s3_browser.validate_s3_access')
@patch('tui.check_viu_availability', return_value=True)
@patch('tui.ImageSelector.run')
def test_workflow_fails_on_processing_error(
    mock_run,
    mock_viu_check,
    mock_s3_access,
    mock_confirm,
    mock_check_duplicates,
    mock_process,
    folder_with_images,
    capsys
):
    """Test workflow fails when image processing encounters an error."""
    from processor import ProcessingError

    # Mock TUI to return selected images
    selected_imgs = [folder_with_images / 'test1.jpg']
    mock_run.return_value = selected_imgs

    # Mock process_images to raise ProcessingError
    mock_process.side_effect = ProcessingError("Failed to process image 'test1.jpg': Invalid format")

    test_args = ['photo_upload.py', str(folder_with_images), '--prefix', 'test']

    with patch.object(sys, 'argv', test_args):
        result = main()

    assert result == 1

    # Check error message
    captured = capsys.readouterr()
    assert "Error: Failed to process image 'test1.jpg': Invalid format" in captured.out


@patch('photo_upload.upload_images')
@patch('photo_upload.process_images')
@patch('photo_upload.check_for_duplicates')
@patch('photo_upload.confirm_upload', return_value=True)
@patch('s3_browser.validate_s3_access')
@patch('tui.check_viu_availability', return_value=True)
@patch('tui.ImageSelector.run')
def test_workflow_fails_on_upload_error(
    mock_run,
    mock_viu_check,
    mock_s3_access,
    mock_confirm,
    mock_check_duplicates,
    mock_process,
    mock_upload,
    folder_with_images,
    capsys
):
    """Test workflow fails when S3 upload encounters an error."""
    from processor import ProcessedImage
    from uploader import UploadError

    # Mock TUI to return selected images
    selected_imgs = [folder_with_images / 'test1.jpg']
    mock_run.return_value = selected_imgs

    # Mock process_images to return temp dir and processed images
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

    # Mock upload_images to raise UploadError
    mock_upload.side_effect = UploadError("Failed to upload 'test1.jpg' to s3://two-touch/test/test1.jpg")

    test_args = ['photo_upload.py', str(folder_with_images), '--prefix', 'test']

    with patch.object(sys, 'argv', test_args):
        result = main()

    assert result == 1

    # Check error message
    captured = capsys.readouterr()
    assert "Error: Failed to upload 'test1.jpg'" in captured.out
    assert "Upload failed. Temp files preserved for retry." in captured.out

    # Cleanup
    mock_temp_dir.cleanup()


@patch('photo_upload.show_completion_summary')
@patch('photo_upload.upload_images')
@patch('photo_upload.process_images')
@patch('photo_upload.check_for_duplicates')
@patch('photo_upload.confirm_upload', return_value=True)
@patch('s3_browser.validate_s3_access')
@patch('tui.check_viu_availability', return_value=True)
@patch('tui.ImageSelector.run')
def test_workflow_with_insufficient_disk_space(
    mock_run,
    mock_viu_check,
    mock_s3_access,
    mock_confirm,
    mock_check_duplicates,
    mock_process,
    mock_upload,
    mock_summary,
    folder_with_images,
    capsys
):
    """Test workflow fails when there's insufficient disk space."""
    from processor import InsufficientDiskSpaceError

    # Mock TUI to return selected images
    selected_imgs = [folder_with_images / 'test1.jpg']
    mock_run.return_value = selected_imgs

    # Mock process_images to raise InsufficientDiskSpaceError
    mock_process.side_effect = InsufficientDiskSpaceError(
        "Insufficient disk space for processing. Needed: 10.0MB, Available: 5.0MB"
    )

    test_args = ['photo_upload.py', str(folder_with_images), '--prefix', 'test']

    with patch.object(sys, 'argv', test_args):
        result = main()

    assert result == 1

    # Verify upload and summary were NOT called
    mock_upload.assert_not_called()
    mock_summary.assert_not_called()

    # Check error message
    captured = capsys.readouterr()
    assert "Insufficient disk space" in captured.out


@patch('photo_upload.show_completion_summary')
@patch('photo_upload.upload_images')
@patch('photo_upload.process_images')
@patch('photo_upload.check_for_duplicates')
@patch('photo_upload.confirm_upload', return_value=True)
@patch('photo_upload.browse_s3_folders', return_value='')
@patch('tui.check_viu_availability', return_value=True)
@patch('tui.ImageSelector.run')
def test_workflow_with_root_prefix(
    mock_run,
    mock_viu_check,
    mock_browse_s3,
    mock_confirm,
    mock_check_duplicates,
    mock_process,
    mock_upload,
    mock_summary,
    folder_with_images,
    capsys
):
    """Test complete workflow with empty prefix (bucket root)."""
    from processor import ProcessedImage

    # Mock TUI to return selected images
    selected_imgs = [folder_with_images / 'test1.jpg']
    mock_run.return_value = selected_imgs

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
    uploaded_keys = ['test1.jpg']
    mock_upload.return_value = uploaded_keys

    test_args = ['photo_upload.py', str(folder_with_images)]

    with patch.object(sys, 'argv', test_args):
        result = main()

    assert result == 0

    # Verify empty prefix was used throughout
    mock_check_duplicates.assert_called_once_with(
        selected_imgs,
        'two-touch',
        '',
        'kurtis-site'
    )
    mock_upload.assert_called_once_with(
        processed_images,
        'two-touch',
        '',
        'kurtis-site'
    )
    mock_summary.assert_called_once_with(
        processed_images,
        uploaded_keys,
        'two-touch',
        ''
    )

    # Cleanup
    mock_temp_dir.cleanup()


@patch('photo_upload.show_completion_summary')
@patch('photo_upload.upload_images')
@patch('photo_upload.process_images')
@patch('photo_upload.check_for_duplicates')
@patch('photo_upload.confirm_upload', return_value=True)
@patch('s3_browser.validate_s3_access')
@patch('tui.check_viu_availability', return_value=True)
@patch('tui.ImageSelector.run')
def test_workflow_succeeds_even_if_summary_fails(
    mock_run,
    mock_viu_check,
    mock_s3_access,
    mock_confirm,
    mock_check_duplicates,
    mock_process,
    mock_upload,
    mock_summary,
    folder_with_images,
    capsys
):
    """Test workflow succeeds even if completion summary fails."""
    from processor import ProcessedImage

    # Mock TUI to return selected images
    selected_imgs = [folder_with_images / 'test1.jpg']
    mock_run.return_value = selected_imgs

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
    uploaded_keys = ['test/test1.jpg']
    mock_upload.return_value = uploaded_keys

    # Mock summary to raise an exception
    mock_summary.side_effect = Exception("Summary display failed")

    test_args = ['photo_upload.py', str(folder_with_images), '--prefix', 'test']

    with patch.object(sys, 'argv', test_args):
        result = main()

    # Should still return success
    assert result == 0

    # Check warning message
    captured = capsys.readouterr()
    assert "Warning: Failed to display completion summary" in captured.out
    assert "Upload completed successfully: 1 files" in captured.out

    # Cleanup
    mock_temp_dir.cleanup()

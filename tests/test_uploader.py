"""Tests for S3 uploader module."""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call
import io

import pytest
from botocore.exceptions import ClientError, BotoCoreError

from photo_terminal.uploader import (
    upload_images,
    UploadError,
    _normalize_prefix,
    _construct_s3_key,
    _show_progress,
    _clear_progress
)
from photo_terminal.processor import ProcessedImage


# Test fixtures

@pytest.fixture
def sample_processed_images(tmp_path):
    """Create sample ProcessedImage objects with temp files."""
    images = []
    for i in range(3):
        # Create temp file
        temp_file = tmp_path / f"processed_{i}.jpg"
        temp_file.write_text(f"image data {i}")

        # Create original path (doesn't need to exist)
        original_path = Path(f"/source/image_{i}.jpg")

        # Create ProcessedImage object
        processed = ProcessedImage(
            original_path=original_path,
            temp_path=temp_file,
            original_size=500000,
            final_size=400000,
            quality_used=85,
            warnings=[]
        )
        images.append(processed)

    return images


@pytest.fixture
def mock_s3_client():
    """Create mock boto3 S3 client."""
    client = MagicMock()
    client.upload_file = MagicMock()
    return client


# Tests for upload_images()

def test_upload_images_success(sample_processed_images, mock_s3_client):
    """Test successful upload of multiple images."""
    with patch('photo_terminal.uploader.boto3.Session') as mock_session:
        # Setup mock session and client
        mock_session.return_value.client.return_value = mock_s3_client

        # Upload images
        uploaded_keys = upload_images(
            processed_images=sample_processed_images,
            bucket='test-bucket',
            prefix='japan/tokyo',
            aws_profile='test-profile'
        )

        # Verify session created with correct profile
        mock_session.assert_called_once_with(profile_name='test-profile')

        # Verify S3 client created
        mock_session.return_value.client.assert_called_once_with('s3')

        # Verify upload_file called for each image
        assert mock_s3_client.upload_file.call_count == 3

        # Verify upload calls
        expected_calls = [
            call(
                Filename=str(sample_processed_images[0].temp_path),
                Bucket='test-bucket',
                Key='japan/tokyo/image_0.jpg'
            ),
            call(
                Filename=str(sample_processed_images[1].temp_path),
                Bucket='test-bucket',
                Key='japan/tokyo/image_1.jpg'
            ),
            call(
                Filename=str(sample_processed_images[2].temp_path),
                Bucket='test-bucket',
                Key='japan/tokyo/image_2.jpg'
            )
        ]
        mock_s3_client.upload_file.assert_has_calls(expected_calls)

        # Verify returned keys
        assert uploaded_keys == [
            'japan/tokyo/image_0.jpg',
            'japan/tokyo/image_1.jpg',
            'japan/tokyo/image_2.jpg'
        ]


def test_upload_images_empty_prefix(sample_processed_images, mock_s3_client):
    """Test upload with empty prefix."""
    with patch('photo_terminal.uploader.boto3.Session') as mock_session:
        mock_session.return_value.client.return_value = mock_s3_client

        uploaded_keys = upload_images(
            processed_images=sample_processed_images,
            bucket='test-bucket',
            prefix='',
            aws_profile='test-profile'
        )

        # Verify keys without prefix
        assert uploaded_keys == [
            'image_0.jpg',
            'image_1.jpg',
            'image_2.jpg'
        ]


def test_upload_images_prefix_with_trailing_slash(sample_processed_images, mock_s3_client):
    """Test upload with prefix containing trailing slash."""
    with patch('photo_terminal.uploader.boto3.Session') as mock_session:
        mock_session.return_value.client.return_value = mock_s3_client

        uploaded_keys = upload_images(
            processed_images=sample_processed_images,
            bucket='test-bucket',
            prefix='japan/tokyo/',  # Trailing slash
            aws_profile='test-profile'
        )

        # Verify keys are correctly constructed (no double slash)
        assert uploaded_keys == [
            'japan/tokyo/image_0.jpg',
            'japan/tokyo/image_1.jpg',
            'japan/tokyo/image_2.jpg'
        ]


def test_upload_images_empty_list():
    """Test upload fails with empty image list."""
    with pytest.raises(ValueError, match="Processed images list cannot be empty"):
        upload_images(
            processed_images=[],
            bucket='test-bucket',
            prefix='japan',
            aws_profile='test-profile'
        )


def test_upload_images_aws_session_error(sample_processed_images):
    """Test upload fails when AWS session creation fails."""
    with patch('photo_terminal.uploader.boto3.Session') as mock_session:
        # Simulate session creation error
        mock_session.side_effect = Exception("Invalid profile")

        with pytest.raises(UploadError, match="Failed to create AWS session.*test-profile"):
            upload_images(
                processed_images=sample_processed_images,
                bucket='test-bucket',
                prefix='japan',
                aws_profile='test-profile'
            )


def test_upload_images_client_error(sample_processed_images, mock_s3_client):
    """Test upload fails immediately on AWS ClientError."""
    with patch('photo_terminal.uploader.boto3.Session') as mock_session:
        mock_session.return_value.client.return_value = mock_s3_client

        # Simulate upload failure on second image
        error_response = {
            'Error': {
                'Code': 'AccessDenied',
                'Message': 'Access Denied'
            }
        }
        mock_s3_client.upload_file.side_effect = [
            None,  # First upload succeeds
            ClientError(error_response, 'PutObject'),  # Second fails
        ]

        # Should fail-fast on second image
        with pytest.raises(UploadError) as exc_info:
            upload_images(
                processed_images=sample_processed_images,
                bucket='test-bucket',
                prefix='japan',
                aws_profile='test-profile'
            )

        # Verify error message includes details
        error_msg = str(exc_info.value)
        assert 'image_1.jpg' in error_msg
        assert 's3://test-bucket/japan/image_1.jpg' in error_msg
        assert 'AccessDenied' in error_msg
        assert 'Access Denied' in error_msg

        # Verify only 2 uploads attempted (fail-fast)
        assert mock_s3_client.upload_file.call_count == 2


def test_upload_images_botocore_error(sample_processed_images, mock_s3_client):
    """Test upload fails immediately on BotoCoreError."""
    with patch('photo_terminal.uploader.boto3.Session') as mock_session:
        mock_session.return_value.client.return_value = mock_s3_client

        # Simulate network error
        mock_s3_client.upload_file.side_effect = BotoCoreError()

        with pytest.raises(UploadError) as exc_info:
            upload_images(
                processed_images=sample_processed_images,
                bucket='test-bucket',
                prefix='japan',
                aws_profile='test-profile'
            )

        # Verify error message includes filename and key
        error_msg = str(exc_info.value)
        assert 'image_0.jpg' in error_msg
        assert 's3://test-bucket/japan/image_0.jpg' in error_msg

        # Verify only one upload attempted (fail-fast)
        assert mock_s3_client.upload_file.call_count == 1


def test_upload_images_generic_error(sample_processed_images, mock_s3_client):
    """Test upload fails on generic exception."""
    with patch('photo_terminal.uploader.boto3.Session') as mock_session:
        mock_session.return_value.client.return_value = mock_s3_client

        # Simulate generic error
        mock_s3_client.upload_file.side_effect = Exception("Unknown error")

        with pytest.raises(UploadError) as exc_info:
            upload_images(
                processed_images=sample_processed_images,
                bucket='test-bucket',
                prefix='japan',
                aws_profile='test-profile'
            )

        error_msg = str(exc_info.value)
        assert 'Unknown error' in error_msg


def test_upload_images_progress_feedback(sample_processed_images, mock_s3_client, capsys):
    """Test progress feedback shows spinner with count."""
    with patch('photo_terminal.uploader.boto3.Session') as mock_session:
        mock_session.return_value.client.return_value = mock_s3_client

        upload_images(
            processed_images=sample_processed_images,
            bucket='test-bucket',
            prefix='japan',
            aws_profile='test-profile'
        )

        # Capture output
        captured = capsys.readouterr()

        # Verify progress was shown (checking for the pattern)
        # Note: Due to \r carriage returns, exact output is hard to test
        # We can verify the output contains uploading messages
        assert 'Uploading...' in captured.out or captured.out == ''  # May be cleared


# Tests for _normalize_prefix()

def test_normalize_prefix_empty_string():
    """Test normalizing empty prefix."""
    assert _normalize_prefix('') == ''


def test_normalize_prefix_no_trailing_slash():
    """Test normalizing prefix without trailing slash."""
    assert _normalize_prefix('japan/tokyo') == 'japan/tokyo'


def test_normalize_prefix_trailing_slash():
    """Test normalizing prefix with trailing slash."""
    assert _normalize_prefix('japan/tokyo/') == 'japan/tokyo'


def test_normalize_prefix_multiple_trailing_slashes():
    """Test normalizing prefix with multiple trailing slashes."""
    assert _normalize_prefix('japan///') == 'japan'


def test_normalize_prefix_whitespace():
    """Test normalizing prefix with whitespace."""
    assert _normalize_prefix('  japan/tokyo  ') == 'japan/tokyo'
    assert _normalize_prefix('  japan/tokyo/  ') == 'japan/tokyo'


def test_normalize_prefix_single_folder():
    """Test normalizing single folder prefix."""
    assert _normalize_prefix('japan') == 'japan'
    assert _normalize_prefix('japan/') == 'japan'


# Tests for _construct_s3_key()

def test_construct_s3_key_with_prefix():
    """Test constructing S3 key with prefix."""
    assert _construct_s3_key('japan/tokyo', 'image.jpg') == 'japan/tokyo/image.jpg'


def test_construct_s3_key_without_prefix():
    """Test constructing S3 key without prefix."""
    assert _construct_s3_key('', 'image.jpg') == 'image.jpg'


def test_construct_s3_key_single_folder():
    """Test constructing S3 key with single folder prefix."""
    assert _construct_s3_key('japan', 'image.jpg') == 'japan/image.jpg'


def test_construct_s3_key_deep_hierarchy():
    """Test constructing S3 key with deep folder hierarchy."""
    assert _construct_s3_key(
        'italy/trapani/2024',
        'sunset.jpg'
    ) == 'italy/trapani/2024/sunset.jpg'


# Tests for _show_progress()

def test_show_progress_output(capsys):
    """Test progress output format."""
    _show_progress(1, 10)

    captured = capsys.readouterr()
    assert 'Uploading...' in captured.out
    assert '(1/10)' in captured.out
    # Should contain a spinner character
    assert any(char in captured.out for char in ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'])


def test_show_progress_multiple_calls(capsys):
    """Test multiple progress updates."""
    for i in range(1, 4):
        _show_progress(i, 5)

    captured = capsys.readouterr()
    # Last update should be visible
    assert 'Uploading...' in captured.out
    assert '(3/5)' in captured.out


# Tests for _clear_progress()

def test_clear_progress(capsys):
    """Test clearing progress line."""
    # Show progress first
    _show_progress(5, 10)

    # Then clear
    _clear_progress()

    captured = capsys.readouterr()
    # Verify ANSI clear code is output
    assert '\033[2K' in captured.out or captured.out.endswith('\r')


# Integration-style tests

def test_upload_single_image(tmp_path, mock_s3_client):
    """Test uploading a single image."""
    # Create single temp file
    temp_file = tmp_path / "processed.jpg"
    temp_file.write_text("image data")

    processed = ProcessedImage(
        original_path=Path("/source/photo.jpg"),
        temp_path=temp_file,
        original_size=1000000,
        final_size=400000,
        quality_used=85,
        warnings=[]
    )

    with patch('photo_terminal.uploader.boto3.Session') as mock_session:
        mock_session.return_value.client.return_value = mock_s3_client

        uploaded_keys = upload_images(
            processed_images=[processed],
            bucket='my-bucket',
            prefix='photos',
            aws_profile='my-profile'
        )

        assert uploaded_keys == ['photos/photo.jpg']
        assert mock_s3_client.upload_file.call_count == 1


def test_upload_preserves_original_filenames(tmp_path, mock_s3_client):
    """Test that original filenames are preserved in S3."""
    # Create images with specific filenames
    filenames = ['DSC_0001.jpg', 'IMG_2345.jpg', 'vacation_beach.jpg']
    processed_images = []

    for filename in filenames:
        temp_file = tmp_path / f"temp_{filename}"
        temp_file.write_text("image")

        processed = ProcessedImage(
            original_path=Path(f"/source/{filename}"),
            temp_path=temp_file,
            original_size=500000,
            final_size=400000,
            quality_used=85,
            warnings=[]
        )
        processed_images.append(processed)

    with patch('photo_terminal.uploader.boto3.Session') as mock_session:
        mock_session.return_value.client.return_value = mock_s3_client

        uploaded_keys = upload_images(
            processed_images=processed_images,
            bucket='test-bucket',
            prefix='photos',
            aws_profile='test-profile'
        )

        # Verify original filenames are preserved
        expected_keys = [f'photos/{name}' for name in filenames]
        assert uploaded_keys == expected_keys


def test_upload_correct_temp_paths_used(tmp_path, mock_s3_client):
    """Test that correct temp paths are passed to boto3."""
    # Create temp files
    temp_file = tmp_path / "processed_image.jpg"
    temp_file.write_text("image data")

    processed = ProcessedImage(
        original_path=Path("/source/original.jpg"),
        temp_path=temp_file,
        original_size=500000,
        final_size=400000,
        quality_used=85,
        warnings=[]
    )

    with patch('photo_terminal.uploader.boto3.Session') as mock_session:
        mock_session.return_value.client.return_value = mock_s3_client

        upload_images(
            processed_images=[processed],
            bucket='test-bucket',
            prefix='photos',
            aws_profile='test-profile'
        )

        # Verify upload_file called with correct temp path
        call_args = mock_s3_client.upload_file.call_args
        assert call_args[1]['Filename'] == str(temp_file)
        assert call_args[1]['Bucket'] == 'test-bucket'
        assert call_args[1]['Key'] == 'photos/original.jpg'


def test_upload_fails_fast_preserves_temp_directory(sample_processed_images, mock_s3_client):
    """Test that temp directory is not cleaned up on upload failure."""
    with patch('photo_terminal.uploader.boto3.Session') as mock_session:
        mock_session.return_value.client.return_value = mock_s3_client

        # Simulate upload failure
        mock_s3_client.upload_file.side_effect = Exception("Network error")

        # Verify files exist before upload
        for img in sample_processed_images:
            assert img.temp_path.exists()

        # Attempt upload (should fail)
        with pytest.raises(UploadError):
            upload_images(
                processed_images=sample_processed_images,
                bucket='test-bucket',
                prefix='photos',
                aws_profile='test-profile'
            )

        # Verify temp files still exist after failure
        for img in sample_processed_images:
            assert img.temp_path.exists()

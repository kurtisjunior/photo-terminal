"""Tests for duplicate_checker module."""

from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest
from botocore.exceptions import ClientError

from photo_terminal.duplicate_checker import (
    check_for_duplicates,
    DuplicateFilesError,
    _check_sequential,
    _check_parallel,
    _key_exists
)


class TestDuplicateFilesError:
    """Tests for DuplicateFilesError exception."""

    def test_error_message_format_with_prefix(self):
        """Test error message formatting with non-empty prefix."""
        duplicates = ['image1.jpg', 'image2.jpg', 'image3.jpg']
        error = DuplicateFilesError(duplicates, 'my-bucket', 'japan/tokyo')

        message = str(error)
        assert 's3://my-bucket/japan/tokyo' in message
        assert 'image1.jpg' in message
        assert 'image2.jpg' in message
        assert 'image3.jpg' in message
        assert 'Aborting to prevent overwrites' in message
        assert 'No files were uploaded' in message

    def test_error_message_format_empty_prefix(self):
        """Test error message formatting with empty prefix (root)."""
        duplicates = ['photo.png']
        error = DuplicateFilesError(duplicates, 'my-bucket', '')

        message = str(error)
        assert 's3://my-bucket/' in message
        assert 'photo.png' in message

    def test_error_attributes(self):
        """Test that error stores duplicates, bucket, and prefix."""
        duplicates = ['test.jpg']
        error = DuplicateFilesError(duplicates, 'bucket', 'prefix')

        assert error.duplicates == duplicates
        assert error.bucket == 'bucket'
        assert error.prefix == 'prefix'


class TestKeyExists:
    """Tests for _key_exists helper function."""

    def test_key_exists_returns_true(self):
        """Test that existing key returns True."""
        mock_client = Mock()
        mock_client.head_object.return_value = {'ResponseMetadata': {'HTTPStatusCode': 200}}

        result = _key_exists(mock_client, 'bucket', 'key.jpg')

        assert result is True
        mock_client.head_object.assert_called_once_with(Bucket='bucket', Key='key.jpg')

    def test_key_not_found_returns_false(self):
        """Test that non-existent key (404) returns False."""
        mock_client = Mock()
        error_response = {'Error': {'Code': '404'}}
        mock_client.head_object.side_effect = ClientError(error_response, 'HeadObject')

        result = _key_exists(mock_client, 'bucket', 'missing.jpg')

        assert result is False

    def test_permission_denied_raises_system_exit(self, capsys):
        """Test that 403 permission error raises SystemExit."""
        mock_client = Mock()
        error_response = {'Error': {'Code': '403', 'Message': 'Forbidden'}}
        mock_client.head_object.side_effect = ClientError(error_response, 'HeadObject')

        with pytest.raises(SystemExit) as exc_info:
            _key_exists(mock_client, 'bucket', 'file.jpg')

        assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert 'Error: Permission denied' in captured.out
        assert 's3:GetObject permission' in captured.out

    def test_other_client_error_raises_system_exit(self, capsys):
        """Test that other ClientError raises SystemExit."""
        mock_client = Mock()
        error_response = {'Error': {'Code': '500', 'Message': 'Server Error'}}
        mock_client.head_object.side_effect = ClientError(error_response, 'HeadObject')

        with pytest.raises(SystemExit) as exc_info:
            _key_exists(mock_client, 'bucket', 'file.jpg')

        assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert 'Error: Failed to check S3 key' in captured.out

    def test_network_error_raises_system_exit(self, capsys):
        """Test that network errors raise SystemExit."""
        mock_client = Mock()
        mock_client.head_object.side_effect = Exception('Connection timeout')

        with pytest.raises(SystemExit) as exc_info:
            _key_exists(mock_client, 'bucket', 'file.jpg')

        assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert 'Error: Failed to connect to S3' in captured.out


class TestCheckSequential:
    """Tests for _check_sequential helper function."""

    def test_no_duplicates_found(self):
        """Test when no duplicates exist."""
        mock_client = Mock()
        mock_client.head_object.side_effect = ClientError(
            {'Error': {'Code': '404'}}, 'HeadObject'
        )

        images = [Path('/tmp/img1.jpg'), Path('/tmp/img2.png')]
        duplicates = _check_sequential(mock_client, images, 'bucket', 'prefix/')

        assert duplicates == []
        assert mock_client.head_object.call_count == 2

    def test_single_duplicate_found(self):
        """Test when one duplicate exists."""
        mock_client = Mock()

        def head_side_effect(Bucket, Key):
            if Key == 'prefix/img1.jpg':
                return {'ResponseMetadata': {'HTTPStatusCode': 200}}
            raise ClientError({'Error': {'Code': '404'}}, 'HeadObject')

        mock_client.head_object.side_effect = head_side_effect

        images = [Path('/tmp/img1.jpg'), Path('/tmp/img2.png')]
        duplicates = _check_sequential(mock_client, images, 'bucket', 'prefix/')

        assert duplicates == ['img1.jpg']

    def test_multiple_duplicates_found(self):
        """Test when multiple duplicates exist."""
        mock_client = Mock()
        mock_client.head_object.return_value = {'ResponseMetadata': {'HTTPStatusCode': 200}}

        images = [Path('/tmp/img1.jpg'), Path('/tmp/img2.png'), Path('/tmp/img3.gif')]
        duplicates = _check_sequential(mock_client, images, 'bucket', 'prefix/')

        assert set(duplicates) == {'img1.jpg', 'img2.png', 'img3.gif'}
        assert len(duplicates) == 3

    def test_empty_prefix(self):
        """Test with empty prefix (root level)."""
        mock_client = Mock()
        mock_client.head_object.return_value = {'ResponseMetadata': {'HTTPStatusCode': 200}}

        images = [Path('/tmp/img.jpg')]
        duplicates = _check_sequential(mock_client, images, 'bucket', '')

        mock_client.head_object.assert_called_once_with(Bucket='bucket', Key='img.jpg')


class TestCheckParallel:
    """Tests for _check_parallel helper function."""

    def test_no_duplicates_parallel(self):
        """Test parallel checking with no duplicates."""
        mock_client = Mock()
        mock_client.head_object.side_effect = ClientError(
            {'Error': {'Code': '404'}}, 'HeadObject'
        )

        images = [Path(f'/tmp/img{i}.jpg') for i in range(15)]
        duplicates = _check_parallel(mock_client, images, 'bucket', 'prefix/')

        assert duplicates == []
        assert mock_client.head_object.call_count == 15

    def test_duplicates_found_parallel(self):
        """Test parallel checking with duplicates."""
        mock_client = Mock()

        def head_side_effect(Bucket, Key):
            if 'img5' in Key or 'img10' in Key:
                return {'ResponseMetadata': {'HTTPStatusCode': 200}}
            raise ClientError({'Error': {'Code': '404'}}, 'HeadObject')

        mock_client.head_object.side_effect = head_side_effect

        images = [Path(f'/tmp/img{i}.jpg') for i in range(15)]
        duplicates = _check_parallel(mock_client, images, 'bucket', 'prefix/')

        assert set(duplicates) == {'img5.jpg', 'img10.jpg'}

    def test_parallel_handles_many_files(self):
        """Test that parallel checking handles large batches efficiently."""
        mock_client = Mock()
        mock_client.head_object.side_effect = ClientError(
            {'Error': {'Code': '404'}}, 'HeadObject'
        )

        # Test with 50 files
        images = [Path(f'/tmp/img{i}.jpg') for i in range(50)]
        duplicates = _check_parallel(mock_client, images, 'bucket', 'prefix/')

        assert duplicates == []
        assert mock_client.head_object.call_count == 50


class TestCheckForDuplicates:
    """Tests for check_for_duplicates main function."""

    @patch('photo_terminal.duplicate_checker.boto3.Session')
    def test_no_duplicates_success(self, mock_session):
        """Test successful check with no duplicates."""
        mock_client = Mock()
        mock_client.head_object.side_effect = ClientError(
            {'Error': {'Code': '404'}}, 'HeadObject'
        )
        mock_session.return_value.client.return_value = mock_client

        images = [Path('/tmp/img1.jpg'), Path('/tmp/img2.png')]

        # Should not raise any exception
        check_for_duplicates(images, 'bucket', 'japan/tokyo', 'my-profile')

        mock_session.assert_called_once_with(profile_name='my-profile')
        assert mock_client.head_object.call_count == 2

    @patch('photo_terminal.duplicate_checker.boto3.Session')
    def test_single_duplicate_raises_error(self, mock_session):
        """Test that single duplicate raises DuplicateFilesError."""
        mock_client = Mock()

        def head_side_effect(Bucket, Key):
            if Key == 'japan/tokyo/photo1.jpg':
                return {'ResponseMetadata': {'HTTPStatusCode': 200}}
            raise ClientError({'Error': {'Code': '404'}}, 'HeadObject')

        mock_client.head_object.side_effect = head_side_effect
        mock_session.return_value.client.return_value = mock_client

        images = [Path('/tmp/photo1.jpg'), Path('/tmp/photo2.jpg')]

        with pytest.raises(DuplicateFilesError) as exc_info:
            check_for_duplicates(images, 'bucket', 'japan/tokyo', 'my-profile')

        assert exc_info.value.duplicates == ['photo1.jpg']
        assert 'japan/tokyo' in str(exc_info.value)

    @patch('photo_terminal.duplicate_checker.boto3.Session')
    def test_multiple_duplicates_raises_error(self, mock_session):
        """Test that multiple duplicates raises DuplicateFilesError."""
        mock_client = Mock()
        mock_client.head_object.return_value = {'ResponseMetadata': {'HTTPStatusCode': 200}}
        mock_session.return_value.client.return_value = mock_client

        images = [Path('/tmp/img1.jpg'), Path('/tmp/img2.png'), Path('/tmp/img3.gif')]

        with pytest.raises(DuplicateFilesError) as exc_info:
            check_for_duplicates(images, 'bucket', 'prefix', 'my-profile')

        assert set(exc_info.value.duplicates) == {'img1.jpg', 'img2.png', 'img3.gif'}
        assert 'img1.jpg' in str(exc_info.value)
        assert 'img2.png' in str(exc_info.value)
        assert 'img3.gif' in str(exc_info.value)

    @patch('photo_terminal.duplicate_checker.boto3.Session')
    def test_empty_prefix_root_level(self, mock_session):
        """Test checking at bucket root with empty prefix."""
        mock_client = Mock()
        mock_client.head_object.side_effect = ClientError(
            {'Error': {'Code': '404'}}, 'HeadObject'
        )
        mock_session.return_value.client.return_value = mock_client

        images = [Path('/tmp/img.jpg')]

        check_for_duplicates(images, 'bucket', '', 'my-profile')

        # Should check without prefix
        mock_client.head_object.assert_called_once_with(Bucket='bucket', Key='img.jpg')

    @patch('photo_terminal.duplicate_checker.boto3.Session')
    def test_prefix_normalization(self, mock_session):
        """Test that prefix is normalized correctly."""
        mock_client = Mock()
        mock_client.head_object.side_effect = ClientError(
            {'Error': {'Code': '404'}}, 'HeadObject'
        )
        mock_session.return_value.client.return_value = mock_client

        images = [Path('/tmp/img.jpg')]

        # Test with leading/trailing slashes
        check_for_duplicates(images, 'bucket', '/japan/tokyo/', 'my-profile')

        # Should normalize to 'japan/tokyo/'
        mock_client.head_object.assert_called_once_with(
            Bucket='bucket', Key='japan/tokyo/img.jpg'
        )

    @patch('photo_terminal.duplicate_checker.boto3.Session')
    def test_empty_image_list_returns_immediately(self, mock_session):
        """Test that empty image list returns without checking S3."""
        images = []

        # Should not raise or make any S3 calls
        check_for_duplicates(images, 'bucket', 'prefix', 'my-profile')

        # Session should not be created
        mock_session.assert_not_called()

    @patch('photo_terminal.duplicate_checker.boto3.Session')
    def test_aws_session_init_failure(self, mock_session, capsys):
        """Test AWS session initialization failure."""
        mock_session.side_effect = Exception('Invalid profile')

        images = [Path('/tmp/img.jpg')]

        with pytest.raises(SystemExit) as exc_info:
            check_for_duplicates(images, 'bucket', 'prefix', 'bad-profile')

        assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert "Error: Failed to initialize AWS session" in captured.out
        assert 'bad-profile' in captured.out
        assert 'aws configure' in captured.out

    @patch('photo_terminal.duplicate_checker.boto3.Session')
    def test_uses_sequential_check_for_small_batch(self, mock_session):
        """Test that small batches (<= 10 files) use sequential checking."""
        mock_client = Mock()
        mock_client.head_object.side_effect = ClientError(
            {'Error': {'Code': '404'}}, 'HeadObject'
        )
        mock_session.return_value.client.return_value = mock_client

        # 10 files - should use sequential
        images = [Path(f'/tmp/img{i}.jpg') for i in range(10)]

        check_for_duplicates(images, 'bucket', 'prefix', 'my-profile')

        # All checks should have been made
        assert mock_client.head_object.call_count == 10

    @patch('photo_terminal.duplicate_checker.boto3.Session')
    def test_uses_parallel_check_for_large_batch(self, mock_session):
        """Test that large batches (> 10 files) use parallel checking."""
        mock_client = Mock()
        mock_client.head_object.side_effect = ClientError(
            {'Error': {'Code': '404'}}, 'HeadObject'
        )
        mock_session.return_value.client.return_value = mock_client

        # 15 files - should use parallel
        images = [Path(f'/tmp/img{i}.jpg') for i in range(15)]

        check_for_duplicates(images, 'bucket', 'prefix', 'my-profile')

        # All checks should have been made
        assert mock_client.head_object.call_count == 15

    @patch('photo_terminal.duplicate_checker.boto3.Session')
    def test_s3_key_construction(self, mock_session):
        """Test that S3 keys are constructed correctly."""
        mock_client = Mock()
        mock_client.head_object.side_effect = ClientError(
            {'Error': {'Code': '404'}}, 'HeadObject'
        )
        mock_session.return_value.client.return_value = mock_client

        images = [
            Path('/some/path/photo.jpg'),
            Path('/another/path/image.png')
        ]

        check_for_duplicates(images, 'my-bucket', 'italy/rome', 'my-profile')

        # Verify S3 keys are prefix + filename
        calls = mock_client.head_object.call_args_list
        assert len(calls) == 2

        keys_checked = {call.kwargs['Key'] for call in calls}
        assert keys_checked == {'italy/rome/photo.jpg', 'italy/rome/image.png'}

    @patch('photo_terminal.duplicate_checker.boto3.Session')
    def test_preserves_original_filenames(self, mock_session):
        """Test that original filenames are preserved in checks."""
        mock_client = Mock()
        mock_client.head_object.side_effect = ClientError(
            {'Error': {'Code': '404'}}, 'HeadObject'
        )
        mock_session.return_value.client.return_value = mock_client

        # Files with special characters, spaces, etc.
        images = [
            Path('/tmp/My Photo (1).jpg'),
            Path('/tmp/IMG_2024-01-15.png')
        ]

        check_for_duplicates(images, 'bucket', 'prefix', 'my-profile')

        calls = mock_client.head_object.call_args_list
        keys_checked = {call.kwargs['Key'] for call in calls}

        # Filenames should be preserved exactly
        assert 'prefix/My Photo (1).jpg' in keys_checked
        assert 'prefix/IMG_2024-01-15.png' in keys_checked

    @patch('photo_terminal.duplicate_checker.boto3.Session')
    def test_all_or_nothing_check(self, mock_session):
        """Test that ALL files are checked before raising error."""
        mock_client = Mock()

        # Make multiple files duplicates
        def head_side_effect(Bucket, Key):
            if 'img1' in Key or 'img2' in Key:
                return {'ResponseMetadata': {'HTTPStatusCode': 200}}
            raise ClientError({'Error': {'Code': '404'}}, 'HeadObject')

        mock_client.head_object.side_effect = head_side_effect
        mock_session.return_value.client.return_value = mock_client

        images = [Path(f'/tmp/img{i}.jpg') for i in range(1, 6)]

        with pytest.raises(DuplicateFilesError) as exc_info:
            check_for_duplicates(images, 'bucket', 'prefix', 'my-profile')

        # Should report ALL duplicates found
        assert set(exc_info.value.duplicates) == {'img1.jpg', 'img2.jpg'}

        # Should have checked all files (not fail-fast on first duplicate)
        assert mock_client.head_object.call_count == 5

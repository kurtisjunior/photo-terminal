"""Tests for S3 access: credentials, prefix listing, and the browser wiring.

The screen half of this module moved to
``photo_terminal.terminal.screens.s3_browse`` and is covered by
``test_s3_browse_screen.py``, which drives it against a fake port instead of a
mocked boto3 session.
"""

from unittest.mock import Mock, patch

import pytest
from botocore.exceptions import (
    ClientError,
    EndpointConnectionError,
    NoCredentialsError,
    ProfileNotFound,
)

from photo_terminal.s3_browser import (
    S3AccessError,
    S3FolderLister,
    browse_s3_folders,
    list_s3_folders,
    validate_s3_access,
)
from photo_terminal.terminal.screens.s3_browse import S3FolderBrowser

# Test fixtures


@pytest.fixture
def mock_s3_client():
    """Mock boto3 S3 client."""
    return Mock()


@pytest.fixture
def mock_session(mock_s3_client):
    """Mock boto3 Session."""
    session = Mock()
    session.client.return_value = mock_s3_client
    return session


# Tests for validate_s3_access


def test_s3_access_success(mock_session, mock_s3_client):
    """Test successful S3 access validation."""
    mock_s3_client.list_objects_v2.return_value = {"Contents": []}

    with patch("photo_terminal.s3_browser.boto3.Session", return_value=mock_session):
        # Should not raise any exception
        validate_s3_access("test-bucket", "test-profile")

    mock_s3_client.list_objects_v2.assert_called_once_with(Bucket="test-bucket", MaxKeys=1)


def test_s3_access_no_profile_uses_env(mock_session, mock_s3_client):
    """Test that a None profile creates a profile-less session (env credentials)."""
    mock_s3_client.list_objects_v2.return_value = {"Contents": []}

    with patch(
        "photo_terminal.s3_browser.boto3.Session", return_value=mock_session
    ) as mock_session_ctor:
        validate_s3_access("test-bucket", None)

    # Session created with no profile_name so boto3 resolves from environment
    mock_session_ctor.assert_called_once_with()
    mock_session.client.assert_called_once_with("s3")


def test_s3_access_profile_not_found(mock_session):
    """Test error when AWS profile not found."""
    with patch(
        "photo_terminal.s3_browser.boto3.Session",
        side_effect=ProfileNotFound(profile="test-profile"),
    ):
        with pytest.raises(S3AccessError) as exc_info:
            validate_s3_access("test-bucket", "test-profile")

        error_msg = str(exc_info.value)
        assert "profile" in error_msg.lower()
        assert "test-profile" in error_msg
        assert "aws configure" in error_msg.lower()
        # Guides users toward .env as the recommended alternative
        assert ".env" in error_msg
        assert "AWS_ACCESS_KEY_ID" in error_msg


def test_s3_access_no_credentials(mock_session, mock_s3_client):
    """Test error when AWS credentials not found."""
    mock_s3_client.list_objects_v2.side_effect = NoCredentialsError()

    with patch("photo_terminal.s3_browser.boto3.Session", return_value=mock_session):
        with pytest.raises(S3AccessError) as exc_info:
            validate_s3_access("test-bucket", "test-profile")

        error_msg = str(exc_info.value)
        assert "credentials" in error_msg.lower()
        assert "aws configure" in error_msg.lower()
        # .env is the recommended first step
        assert ".env" in error_msg
        assert "AWS_ACCESS_KEY_ID" in error_msg


def test_s3_access_no_credentials_no_profile(mock_session, mock_s3_client):
    """Test error message when no profile is set and credentials are missing."""
    mock_s3_client.list_objects_v2.side_effect = NoCredentialsError()

    with patch("photo_terminal.s3_browser.boto3.Session", return_value=mock_session):
        with pytest.raises(S3AccessError) as exc_info:
            validate_s3_access("test-bucket", None)

        error_msg = str(exc_info.value)
        assert ".env" in error_msg
        assert "AWS_ACCESS_KEY_ID" in error_msg
        assert "AWS_SECRET_ACCESS_KEY" in error_msg


def test_s3_access_bucket_not_found(mock_session, mock_s3_client):
    """Test error when S3 bucket does not exist."""
    error_response = {
        "Error": {"Code": "NoSuchBucket", "Message": "The specified bucket does not exist"}
    }
    mock_s3_client.list_objects_v2.side_effect = ClientError(error_response, "ListObjectsV2")

    with patch("photo_terminal.s3_browser.boto3.Session", return_value=mock_session):
        with pytest.raises(S3AccessError) as exc_info:
            validate_s3_access("test-bucket", "test-profile")

        assert "test-bucket" in str(exc_info.value)
        assert "does not exist" in str(exc_info.value).lower()


def test_s3_access_denied(mock_session, mock_s3_client):
    """Test error when access to S3 bucket is denied."""
    error_response = {"Error": {"Code": "AccessDenied", "Message": "Access Denied"}}
    mock_s3_client.list_objects_v2.side_effect = ClientError(error_response, "ListObjectsV2")

    with patch("photo_terminal.s3_browser.boto3.Session", return_value=mock_session):
        with pytest.raises(S3AccessError) as exc_info:
            validate_s3_access("test-bucket", "test-profile")

        assert "access denied" in str(exc_info.value).lower()
        assert "permission" in str(exc_info.value).lower()


def test_s3_access_network_error(mock_session, mock_s3_client):
    """Test error when network connection fails."""
    mock_s3_client.list_objects_v2.side_effect = EndpointConnectionError(
        endpoint_url="https://s3.amazonaws.com"
    )

    with patch("photo_terminal.s3_browser.boto3.Session", return_value=mock_session):
        with pytest.raises(S3AccessError) as exc_info:
            validate_s3_access("test-bucket", "test-profile")

        assert "network" in str(exc_info.value).lower()


# Tests for list_s3_folders


def test_list_s3_folders_root(mock_session, mock_s3_client):
    """Test listing folders at root level."""
    mock_s3_client.list_objects_v2.return_value = {
        "CommonPrefixes": [
            {"Prefix": "japan/"},
            {"Prefix": "italy/"},
            {"Prefix": "spain/"},
        ]
    }

    with patch("photo_terminal.s3_browser.boto3.Session", return_value=mock_session):
        folders = list_s3_folders("test-bucket", "test-profile", "")

    assert folders == ["italy", "japan", "spain"]  # Sorted
    mock_s3_client.list_objects_v2.assert_called_once_with(
        Bucket="test-bucket", Prefix="", Delimiter="/"
    )


def test_list_s3_folders_subfolder(mock_session, mock_s3_client):
    """Test listing folders in a subfolder."""
    mock_s3_client.list_objects_v2.return_value = {
        "CommonPrefixes": [
            {"Prefix": "italy/rome/"},
            {"Prefix": "italy/trapani/"},
            {"Prefix": "italy/venice/"},
        ]
    }

    with patch("photo_terminal.s3_browser.boto3.Session", return_value=mock_session):
        folders = list_s3_folders("test-bucket", "test-profile", "italy/")

    assert folders == ["rome", "trapani", "venice"]  # Sorted
    mock_s3_client.list_objects_v2.assert_called_once_with(
        Bucket="test-bucket", Prefix="italy/", Delimiter="/"
    )


def test_list_s3_folders_empty(mock_session, mock_s3_client):
    """Test listing folders when no subfolders exist."""
    mock_s3_client.list_objects_v2.return_value = {"CommonPrefixes": []}

    with patch("photo_terminal.s3_browser.boto3.Session", return_value=mock_session):
        folders = list_s3_folders("test-bucket", "test-profile", "japan/tokyo/")

    assert folders == []


def test_list_s3_folders_error(mock_session, mock_s3_client):
    """Test error handling when listing folders fails."""
    mock_s3_client.list_objects_v2.side_effect = Exception("Network error")

    with patch("photo_terminal.s3_browser.boto3.Session", return_value=mock_session):
        with pytest.raises(S3AccessError) as exc_info:
            list_s3_folders("test-bucket", "test-profile", "")

        assert "error listing" in str(exc_info.value).lower()


# Tests for browse_s3_folders function


def test_browse_with_cli_prefix(mock_session, mock_s3_client):
    """Test browse_s3_folders with CLI prefix (skip browser)."""
    mock_s3_client.list_objects_v2.return_value = {}

    with patch("photo_terminal.s3_browser.boto3.Session", return_value=mock_session):
        result = browse_s3_folders("test-bucket", "test-profile", "japan/tokyo")

    # Should return prefix directly without showing browser
    assert result == "japan/tokyo/"


def test_browse_with_cli_prefix_already_trailing_slash(mock_session, mock_s3_client):
    """Test browse_s3_folders with CLI prefix that already has trailing slash."""
    mock_s3_client.list_objects_v2.return_value = {}

    with patch("photo_terminal.s3_browser.boto3.Session", return_value=mock_session):
        result = browse_s3_folders("test-bucket", "test-profile", "japan/tokyo/")

    assert result == "japan/tokyo/"


def test_browse_with_empty_cli_prefix(mock_session, mock_s3_client):
    """Test browse_s3_folders with empty string as CLI prefix (root)."""
    mock_s3_client.list_objects_v2.return_value = {}

    with patch("photo_terminal.s3_browser.boto3.Session", return_value=mock_session):
        result = browse_s3_folders("test-bucket", "test-profile", "")

    assert result == ""


def test_browse_s3_access_error(mock_session, mock_s3_client):
    """Test browse_s3_folders fails when S3 access test fails."""
    mock_s3_client.list_objects_v2.side_effect = NoCredentialsError()

    with patch("photo_terminal.s3_browser.boto3.Session", return_value=mock_session):
        with pytest.raises(SystemExit) as exc_info:
            browse_s3_folders("test-bucket", "test-profile")

        assert exc_info.value.code == 1


def test_browse_interactive_cancelled():
    """Test browse_s3_folders raises SystemExit when user cancels."""
    mock_browser = Mock()
    mock_browser.run.side_effect = KeyboardInterrupt()

    with patch("photo_terminal.s3_browser.validate_s3_access"):
        with patch("photo_terminal.s3_browser.S3FolderBrowser", return_value=mock_browser):
            with pytest.raises(SystemExit) as exc_info:
                browse_s3_folders("test-bucket", "test-profile")

            assert exc_info.value.code == 1


def test_browse_interactive_success():
    """Test browse_s3_folders returns selected prefix from interactive browser."""
    mock_browser = Mock()
    mock_browser.run.return_value = "japan/tokyo/"

    with patch("photo_terminal.s3_browser.validate_s3_access"):
        with patch("photo_terminal.s3_browser.S3FolderBrowser", return_value=mock_browser):
            result = browse_s3_folders("test-bucket", "test-profile")

    assert result == "japan/tokyo/"


# Integration tests


def test_full_navigation_flow(mock_session, mock_s3_client):
    """The screen and the boto3 lister together: root -> subfolder -> select."""

    # Setup mock responses for different levels
    def list_objects_side_effect(**kwargs):
        prefix = kwargs.get("Prefix", "")
        if prefix == "":
            return {"CommonPrefixes": [{"Prefix": "japan/"}]}
        elif prefix == "japan/":
            return {"CommonPrefixes": [{"Prefix": "japan/tokyo/"}]}
        return {"CommonPrefixes": []}

    mock_s3_client.list_objects_v2.side_effect = list_objects_side_effect

    browser = S3FolderBrowser(S3FolderLister("test-bucket", "test-profile"))

    with patch("photo_terminal.s3_browser.boto3.Session", return_value=mock_session):
        # Start at root
        browser.load_folders()
        assert browser.folders == ["japan"]
        assert browser.current_prefix == ""

        # Drill into japan. The listing runs off the input loop, so the test
        # waits for it exactly where the loop's wakeup pipe would.
        browser.current_index = 1  # "japan" folder
        result = browser.handle_selection()
        assert result is None
        assert browser.current_prefix == "japan/"
        browser.settle(timeout=5)
        assert browser.folders == ["tokyo"]

        # Select current folder
        browser.current_index = 0  # "Select current folder"
        result = browser.handle_selection()
        assert result == "japan/"


# Tests for the boto3 implementation of the browser's port


def test_folder_lister_delegates_to_list_s3_folders(mock_session, mock_s3_client):
    """The screen depends on this one method and nothing else."""
    mock_s3_client.list_objects_v2.return_value = {
        "CommonPrefixes": [{"Prefix": "japan/tokyo/"}, {"Prefix": "japan/kyoto/"}]
    }

    lister = S3FolderLister("test-bucket", "test-profile")
    with patch("photo_terminal.s3_browser.boto3.Session", return_value=mock_session):
        folders = lister.list_folders("japan/")

    assert folders == ["kyoto", "tokyo"]
    mock_s3_client.list_objects_v2.assert_called_once_with(
        Bucket="test-bucket", Prefix="japan/", Delimiter="/"
    )

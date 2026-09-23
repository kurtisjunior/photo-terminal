"""The composition root, and the one function in it with a decision to make.

``browse_destination`` used to be ``storage.s3.browse_s3_folders``, which made
the storage package import a terminal screen. It is the same behaviour, moved
to the only layer allowed to know about both.
"""

from unittest.mock import Mock, patch

import pytest
from botocore.exceptions import NoCredentialsError

from photo_terminal.app.context import Deps
from photo_terminal.app.wiring import browse_destination, build_deps
from photo_terminal.domain.errors import S3AccessError
from photo_terminal.domain.progress import NullReporter


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


def test_build_deps_fills_every_hole():
    """A missing field here is a step that cannot run, found at import time."""
    deps = build_deps(NullReporter())

    assert isinstance(deps, Deps)
    for field in Deps.__dataclass_fields__:
        assert getattr(deps, field) is not None


# Tests for browse_destination


def test_browse_with_cli_prefix(mock_session, mock_s3_client):
    """Test browse_destination with CLI prefix (skip browser)."""
    mock_s3_client.list_objects_v2.return_value = {}

    with patch("photo_terminal.storage.s3.boto3.Session", return_value=mock_session):
        result = browse_destination("test-bucket", "test-profile", "japan/tokyo")

    # Should return prefix directly without showing browser
    assert result == "japan/tokyo/"


def test_browse_with_cli_prefix_already_trailing_slash(mock_session, mock_s3_client):
    """Test browse_destination with CLI prefix that already has trailing slash."""
    mock_s3_client.list_objects_v2.return_value = {}

    with patch("photo_terminal.storage.s3.boto3.Session", return_value=mock_session):
        result = browse_destination("test-bucket", "test-profile", "japan/tokyo/")

    assert result == "japan/tokyo/"


def test_browse_with_empty_cli_prefix(mock_session, mock_s3_client):
    """Test browse_destination with empty string as CLI prefix (root)."""
    mock_s3_client.list_objects_v2.return_value = {}

    with patch("photo_terminal.storage.s3.boto3.Session", return_value=mock_session):
        result = browse_destination("test-bucket", "test-profile", "")

    assert result == ""


def test_browse_s3_access_error(mock_session, mock_s3_client):
    """An unreachable bucket is a typed error that names the bucket."""
    mock_s3_client.list_objects_v2.side_effect = NoCredentialsError()

    with patch("photo_terminal.storage.s3.boto3.Session", return_value=mock_session):
        with pytest.raises(S3AccessError) as exc_info:
            browse_destination("test-bucket", "test-profile")

    assert "Cannot access S3 bucket 'test-bucket'" in exc_info.value.message
    assert "AWS credentials not found" in exc_info.value.message
    assert exc_info.value.exit_code == 1


def test_browse_interactive_cancelled():
    """Ctrl-C propagates; what cancelling means is the caller's decision."""
    mock_browser = Mock()
    mock_browser.run.side_effect = KeyboardInterrupt()

    with patch("photo_terminal.app.wiring.validate_s3_access"):
        with patch("photo_terminal.app.wiring.S3FolderBrowser", return_value=mock_browser):
            with pytest.raises(KeyboardInterrupt):
                browse_destination("test-bucket", "test-profile")


def test_browse_interactive_success():
    """Test browse_destination returns selected prefix from interactive browser."""
    mock_browser = Mock()
    mock_browser.run.return_value = "japan/tokyo/"

    with patch("photo_terminal.app.wiring.validate_s3_access"):
        with patch("photo_terminal.app.wiring.S3FolderBrowser", return_value=mock_browser):
            result = browse_destination("test-bucket", "test-profile")

    assert result == "japan/tokyo/"

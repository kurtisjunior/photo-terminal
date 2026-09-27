"""Tests for fail-fast S3 access validation."""

from unittest.mock import Mock, patch

import pytest
from botocore.exceptions import (
    ClientError,
    EndpointConnectionError,
    NoCredentialsError,
    ProfileNotFound,
)

from photo_terminal.domain.errors import S3AccessError
from photo_terminal.storage.s3 import validate_s3_access


@pytest.fixture
def mock_s3_client():
    return Mock()


@pytest.fixture
def mock_session(mock_s3_client):
    session = Mock()
    session.client.return_value = mock_s3_client
    return session


def test_s3_access_success(mock_session, mock_s3_client):
    mock_s3_client.list_objects_v2.return_value = {"Contents": []}

    with patch("photo_terminal.storage.s3.boto3.Session", return_value=mock_session):
        validate_s3_access("test-bucket", "test-profile")

    mock_s3_client.list_objects_v2.assert_called_once_with(Bucket="test-bucket", MaxKeys=1)


def test_s3_access_no_profile_uses_env(mock_session, mock_s3_client):
    mock_s3_client.list_objects_v2.return_value = {"Contents": []}

    with patch(
        "photo_terminal.storage.s3.boto3.Session", return_value=mock_session
    ) as session_constructor:
        validate_s3_access("test-bucket", None)

    session_constructor.assert_called_once_with()
    mock_session.client.assert_called_once_with("s3")


def test_s3_access_profile_not_found():
    with patch(
        "photo_terminal.storage.s3.boto3.Session",
        side_effect=ProfileNotFound(profile="test-profile"),
    ):
        with pytest.raises(S3AccessError) as exc_info:
            validate_s3_access("test-bucket", "test-profile")

    error = str(exc_info.value)
    assert "test-profile" in error
    assert "aws configure" in error.lower()
    assert ".env" in error
    assert "AWS_ACCESS_KEY_ID" in error


def test_s3_access_no_credentials(mock_session, mock_s3_client):
    mock_s3_client.list_objects_v2.side_effect = NoCredentialsError()

    with patch("photo_terminal.storage.s3.boto3.Session", return_value=mock_session):
        with pytest.raises(S3AccessError) as exc_info:
            validate_s3_access("test-bucket", "test-profile")

    error = str(exc_info.value)
    assert "credentials" in error.lower()
    assert "aws configure" in error.lower()
    assert ".env" in error


def test_s3_access_no_credentials_no_profile(mock_session, mock_s3_client):
    mock_s3_client.list_objects_v2.side_effect = NoCredentialsError()

    with patch("photo_terminal.storage.s3.boto3.Session", return_value=mock_session):
        with pytest.raises(S3AccessError) as exc_info:
            validate_s3_access("test-bucket", None)

    error = str(exc_info.value)
    assert "AWS_ACCESS_KEY_ID" in error
    assert "AWS_SECRET_ACCESS_KEY" in error


def test_s3_access_bucket_not_found(mock_session, mock_s3_client):
    response = {"Error": {"Code": "NoSuchBucket", "Message": "The specified bucket does not exist"}}
    mock_s3_client.list_objects_v2.side_effect = ClientError(response, "ListObjectsV2")

    with patch("photo_terminal.storage.s3.boto3.Session", return_value=mock_session):
        with pytest.raises(S3AccessError) as exc_info:
            validate_s3_access("test-bucket", "test-profile")

    assert "test-bucket" in str(exc_info.value)
    assert "does not exist" in str(exc_info.value).lower()


def test_s3_access_denied(mock_session, mock_s3_client):
    response = {"Error": {"Code": "AccessDenied", "Message": "Access Denied"}}
    mock_s3_client.list_objects_v2.side_effect = ClientError(response, "ListObjectsV2")

    with patch("photo_terminal.storage.s3.boto3.Session", return_value=mock_session):
        with pytest.raises(S3AccessError) as exc_info:
            validate_s3_access("test-bucket", "test-profile")

    assert "access denied" in str(exc_info.value).lower()
    assert "permission" in str(exc_info.value).lower()


def test_s3_access_network_error(mock_session, mock_s3_client):
    mock_s3_client.list_objects_v2.side_effect = EndpointConnectionError(
        endpoint_url="https://s3.amazonaws.com"
    )

    with patch("photo_terminal.storage.s3.boto3.Session", return_value=mock_session):
        with pytest.raises(S3AccessError) as exc_info:
            validate_s3_access("test-bucket", "test-profile")

    assert "network" in str(exc_info.value).lower()

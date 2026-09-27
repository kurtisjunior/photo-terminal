"""Tests for production dependency wiring and destination entry."""

from unittest.mock import Mock, patch

import pytest
from botocore.exceptions import NoCredentialsError

from photo_terminal.app.context import Deps
from photo_terminal.app.wiring import build_deps, enter_destination
from photo_terminal.domain.errors import S3AccessError
from photo_terminal.domain.progress import NullReporter


def test_build_deps_fills_every_hole():
    deps = build_deps(NullReporter())

    assert isinstance(deps, Deps)
    for field in Deps.__dataclass_fields__:
        assert getattr(deps, field) is not None


def test_destination_is_entered_after_access_is_validated():
    with patch("photo_terminal.app.wiring.validate_s3_access") as validate:
        with patch(
            "photo_terminal.app.wiring.enter_upload_location", return_value="newyork/summer-23"
        ) as enter:
            result = enter_destination("test-bucket", "test-profile")

    validate.assert_called_once_with("test-bucket", "test-profile")
    enter.assert_called_once_with("test-bucket")
    assert result == "newyork/summer-23"


def test_destination_entry_can_be_cancelled():
    with patch("photo_terminal.app.wiring.validate_s3_access"):
        with patch("photo_terminal.app.wiring.enter_upload_location", return_value=None):
            assert enter_destination("test-bucket", "test-profile") is None


def test_destination_access_error_names_the_bucket():
    client = Mock()
    client.list_objects_v2.side_effect = NoCredentialsError()
    session = Mock()
    session.client.return_value = client

    with patch("photo_terminal.storage.s3.boto3.Session", return_value=session):
        with pytest.raises(S3AccessError) as exc_info:
            enter_destination("test-bucket", "test-profile")

    assert "Cannot access S3 bucket 'test-bucket'" in exc_info.value.message
    assert "AWS credentials not found" in exc_info.value.message

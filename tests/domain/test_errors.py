"""Tests for the typed error hierarchy.

Every error the library raises has to answer two questions the CLI will ask it:
what should the user read, and what should the process exit with. These assert
both, for every type, so a new member of the hierarchy cannot be added without
one.
"""

import pytest

from photo_terminal.domain.errors import (
    ConfigError,
    DuplicateKeyError,
    InsufficientDiskSpaceError,
    NoImagesFound,
    PhotoTerminalError,
    ProcessingError,
    S3AccessError,
    UploadFailed,
)

# Every type that takes a plain message. DuplicateKeyError builds its own and
# is covered separately below.
MESSAGE_ERRORS = [
    PhotoTerminalError,
    ConfigError,
    NoImagesFound,
    S3AccessError,
    UploadFailed,
    ProcessingError,
    InsufficientDiskSpaceError,
]


@pytest.mark.parametrize("error_type", MESSAGE_ERRORS)
def test_every_error_carries_its_message(error_type):
    error = error_type("something specific went wrong")

    assert error.message == "something specific went wrong"
    assert str(error) == "something specific went wrong"


@pytest.mark.parametrize("error_type", MESSAGE_ERRORS)
def test_every_error_carries_an_exit_code(error_type):
    assert error_type("boom").exit_code == 1


@pytest.mark.parametrize("error_type", MESSAGE_ERRORS)
def test_every_error_is_a_photo_terminal_error(error_type):
    """One `except` in the pipeline has to be able to catch all of them."""
    assert isinstance(error_type("boom"), PhotoTerminalError)


@pytest.mark.parametrize("error_type", MESSAGE_ERRORS)
def test_no_error_message_carries_its_own_error_prefix(error_type):
    """The presentation layer adds the framing. Messages must not duplicate it."""
    assert not error_type("boom").message.startswith("Error:")


def test_a_multi_line_message_survives_intact():
    """Guidance is part of the message, not something printed alongside it."""
    error = ConfigError("Malformed YAML in photo-uploader.yaml\nDetails: bad token")

    assert error.message.splitlines() == [
        "Malformed YAML in photo-uploader.yaml",
        "Details: bad token",
    ]


def test_duplicate_key_error_message_names_the_target_and_the_files():
    error = DuplicateKeyError(["image1.jpg", "image2.jpg"], "my-bucket", "japan/tokyo")

    assert "s3://my-bucket/japan/tokyo" in error.message
    assert "image1.jpg" in error.message
    assert "image2.jpg" in error.message
    assert "Aborting to prevent overwrites" in error.message
    assert "No files were uploaded" in error.message
    assert error.exit_code == 1


def test_duplicate_key_error_targets_the_root_when_there_is_no_prefix():
    error = DuplicateKeyError(["photo.png"], "my-bucket", "")

    assert "s3://my-bucket/" in error.message


def test_duplicate_key_error_keeps_what_it_found():
    error = DuplicateKeyError(["test.jpg"], "bucket", "prefix")

    assert error.duplicates == ["test.jpg"]
    assert error.bucket == "bucket"
    assert error.prefix == "prefix"


def test_duplicate_key_error_is_a_photo_terminal_error():
    assert isinstance(DuplicateKeyError([], "bucket", ""), PhotoTerminalError)

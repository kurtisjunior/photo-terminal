"""The values the pipeline threads between its steps."""

from pathlib import Path

import pytest

from photo_terminal.domain.models import (
    OUTPUT_FORMATS,
    Config,
    ProcessedImage,
    ProcessingOptions,
    S3Destination,
)

# -- Config --------------------------------------------------------------- #


def test_config_keeps_what_it_was_given():
    config = Config(bucket="two-touch", aws_profile="work", target_size_kb=400)

    assert config.bucket == "two-touch"
    assert config.aws_profile == "work"
    assert config.target_size_kb == 400


def test_a_target_size_override_is_a_copy():
    """``--target-size`` used to be applied by assigning to the loaded config."""
    original = Config(bucket="b", aws_profile=None, target_size_kb=400)

    overridden = original.with_target_size(500)

    assert overridden.target_size_kb == 500
    assert original.target_size_kb == 400
    assert overridden is not original


def test_no_override_returns_the_same_config():
    original = Config(bucket="b", aws_profile=None, target_size_kb=400)

    assert original.with_target_size(None) is original


def test_configs_compare_by_value():
    assert Config("b", None, 400) == Config("b", None, 400)


# -- S3Destination -------------------------------------------------------- #


@pytest.mark.parametrize(
    ("prefix", "expected"),
    [
        ("", "s3://two-touch/"),
        ("japan/tokyo", "s3://two-touch/japan/tokyo/"),
        ("japan/tokyo/", "s3://two-touch/japan/tokyo/"),
        ("/japan/tokyo/", "s3://two-touch/japan/tokyo/"),
    ],
)
def test_the_url_survives_however_the_prefix_arrived(prefix, expected):
    """The browser hands back a trailing slash and ``--prefix`` does not."""
    assert S3Destination("two-touch", prefix).url == expected


def test_a_destination_is_immutable():
    with pytest.raises(AttributeError):
        S3Destination("b", "").prefix = "other"  # type: ignore[misc]


# -- ProcessingOptions ---------------------------------------------------- #


def test_processing_options_are_immutable():
    options = ProcessingOptions(
        resize=True, target_size_kb=400, preserve_exif=True, output_format="JPEG"
    )

    with pytest.raises(AttributeError):
        options.resize = False  # type: ignore[misc]


def test_every_output_format_the_screen_cycles_is_one_the_optimizer_writes():
    assert OUTPUT_FORMATS == ("JPEG", "PNG", "WEBP")


# -- ProcessedImage ------------------------------------------------------- #


def _processed(**overrides) -> ProcessedImage:
    fields = {
        "original_path": Path("/source/photo.jpg"),
        "temp_path": Path("/tmp/photo.jpg"),
        "original_size": 1_000_000,
        "final_size": 200_000,
        "quality_used": 85,
        "warnings": [],
    }
    fields.update(overrides)
    return ProcessedImage(**fields)


def test_the_target_filename_is_the_original_name_by_default():
    assert _processed().target_filename == "photo.jpg"


def test_a_reordered_image_uploads_under_its_new_name():
    assert _processed(upload_filename="01_photo.jpg").target_filename == "01_photo.jpg"


def test_an_empty_upload_filename_falls_back_to_the_original():
    """The uploader used to spell this out at its own call site, twice."""
    assert _processed(upload_filename="").target_filename == "photo.jpg"

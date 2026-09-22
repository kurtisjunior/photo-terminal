"""Tests for the configuration module.

These were previously written as a printing script with a ``__main__`` runner,
and four of them swallowed ``SystemExit`` in an ``except`` clause without
asserting anything - so they passed whether or not the config layer rejected
bad input. They now assert on the raise.

``SystemExit`` and the printed guidance that went with it are now a typed
``ConfigError`` carrying that guidance as its message, so each of these asserts
on the message and on the exit code the CLI will use.
"""

from pathlib import Path

import pytest

from photo_terminal import config
from photo_terminal.errors import ConfigError
from tests.conftest import RecordingReporter


def _write_config(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "photo-uploader.yaml"
    path.write_text(body)
    return path


def test_default_config_creation(tmp_path: Path) -> None:
    """A missing config file is created with defaults, and reloads identically."""
    path = tmp_path / "photo-uploader.yaml"

    cfg = config.load_config(path)

    assert path.exists()
    assert cfg.bucket == "two-touch"
    assert cfg.aws_profile is None
    assert cfg.target_size_kb == 400

    # Config has no __eq__, so compare the fields the file round-trips.
    reloaded = config.load_config(path)
    assert (reloaded.bucket, reloaded.aws_profile, reloaded.target_size_kb) == (
        cfg.bucket,
        cfg.aws_profile,
        cfg.target_size_kb,
    )


def test_malformed_yaml(tmp_path: Path) -> None:
    """Unparseable YAML is rejected rather than silently ignored."""
    path = _write_config(tmp_path, "bucket: two-touch\naws_profile: [\n")

    with pytest.raises(ConfigError) as exc_info:
        config.load_config(path)

    assert "Malformed YAML" in exc_info.value.message
    assert exc_info.value.exit_code == 1


def test_missing_field(tmp_path: Path) -> None:
    """A required field left out of the file is rejected."""
    path = _write_config(tmp_path, "bucket: two-touch\naws_profile: kurtis-site\n")

    with pytest.raises(ConfigError) as exc_info:
        config.load_config(path)

    assert "Missing required config field" in exc_info.value.message
    assert "Required fields: bucket, target_size_kb" in exc_info.value.message
    assert exc_info.value.exit_code == 1


def test_invalid_value(tmp_path: Path) -> None:
    """A negative target size is rejected."""
    path = _write_config(
        tmp_path,
        "bucket: two-touch\naws_profile: kurtis-site\ntarget_size_kb: -100\n",
    )

    with pytest.raises(ConfigError) as exc_info:
        config.load_config(path)

    assert "'target_size_kb' must be a positive integer" in exc_info.value.message
    assert exc_info.value.exit_code == 1


def test_custom_values(tmp_path: Path) -> None:
    """Every field is read back from the file."""
    path = _write_config(
        tmp_path,
        "bucket: my-custom-bucket\naws_profile: my-profile\ntarget_size_kb: 500\n",
    )

    cfg = config.load_config(path)

    assert cfg.bucket == "my-custom-bucket"
    assert cfg.aws_profile == "my-profile"
    assert cfg.target_size_kb == 500


def test_omitted_aws_profile(tmp_path: Path) -> None:
    """``aws_profile`` is optional and defaults to None when absent."""
    path = _write_config(tmp_path, "bucket: two-touch\ntarget_size_kb: 400\n")

    cfg = config.load_config(path)

    assert cfg.bucket == "two-touch"
    assert cfg.aws_profile is None
    assert cfg.target_size_kb == 400


def test_empty_aws_profile(tmp_path: Path) -> None:
    """An empty ``aws_profile`` is a mistake, not the same as omitting it."""
    path = _write_config(
        tmp_path,
        "bucket: two-touch\naws_profile: ''\ntarget_size_kb: 400\n",
    )

    with pytest.raises(ConfigError) as exc_info:
        config.load_config(path)

    assert "'aws_profile' must be a non-empty string if provided" in exc_info.value.message
    assert exc_info.value.exit_code == 1


def test_a_non_dictionary_document_is_rejected(tmp_path: Path) -> None:
    """A YAML list where a mapping was expected names what it got."""
    path = _write_config(tmp_path, "- bucket: two-touch\n")

    with pytest.raises(ConfigError) as exc_info:
        config.load_config(path)

    assert "must contain a YAML dictionary" in exc_info.value.message
    assert "Got: list" in exc_info.value.message


def test_an_empty_bucket_is_rejected(tmp_path: Path) -> None:
    """The bucket name has to be a name."""
    path = _write_config(tmp_path, "bucket: ''\ntarget_size_kb: 400\n")

    with pytest.raises(ConfigError) as exc_info:
        config.load_config(path)

    assert "'bucket' must be a non-empty string" in exc_info.value.message


def test_the_first_run_notice_goes_to_the_reporter(tmp_path: Path) -> None:
    """Creating the default file is news, and news is the reporter's job."""
    path = tmp_path / "photo-uploader.yaml"
    reporter = RecordingReporter()

    config.load_config(path, reporter=reporter)

    assert reporter.infos == [f"Created default configuration at {path}"]


def test_loading_an_existing_file_says_nothing(tmp_path: Path) -> None:
    """Nothing is reported when there was nothing to report."""
    path = _write_config(tmp_path, "bucket: two-touch\ntarget_size_kb: 400\n")
    reporter = RecordingReporter()

    config.load_config(path, reporter=reporter)

    assert reporter.infos == []


def test_loading_prints_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The config layer has no opinion about stdout."""
    path = _write_config(tmp_path, "bucket: two-touch\ntarget_size_kb: 400\n")

    config.load_config(path)

    assert capsys.readouterr().out == ""

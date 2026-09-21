"""Tests for the configuration module.

These were previously written as a printing script with a ``__main__`` runner,
and four of them swallowed ``SystemExit`` in an ``except`` clause without
asserting anything - so they passed whether or not the config layer rejected
bad input. They now assert on the raise.

Phase 5 converts ``SystemExit`` here into a typed ``ConfigError``; these tests
move with it.
"""

from pathlib import Path

import pytest

from photo_terminal import config


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

    with pytest.raises(SystemExit) as exc_info:
        config.load_config(path)

    assert exc_info.value.code == 1


def test_missing_field(tmp_path: Path) -> None:
    """A required field left out of the file is rejected."""
    path = _write_config(tmp_path, "bucket: two-touch\naws_profile: kurtis-site\n")

    with pytest.raises(SystemExit) as exc_info:
        config.load_config(path)

    assert exc_info.value.code == 1


def test_invalid_value(tmp_path: Path) -> None:
    """A negative target size is rejected."""
    path = _write_config(
        tmp_path,
        "bucket: two-touch\naws_profile: kurtis-site\ntarget_size_kb: -100\n",
    )

    with pytest.raises(SystemExit) as exc_info:
        config.load_config(path)

    assert exc_info.value.code == 1


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

    with pytest.raises(SystemExit) as exc_info:
        config.load_config(path)

    assert exc_info.value.code == 1

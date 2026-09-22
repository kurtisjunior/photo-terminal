"""argv in, exit code out.

What is left of ``test_photo_upload.py``'s CLI-shaped assertions, now that the
run itself is covered step by step in ``test_pipeline.py``. These are about the
surface: which flags exist, what the banner says, and what happens before the
first step gets a chance to run.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from photo_terminal.app import cli
from photo_terminal.app.context import CliOptions
from photo_terminal.domain.errors import ConfigError, InvalidSourceFolder
from photo_terminal.domain.models import Config

CONFIG = Config(bucket="test-bucket", aws_profile="test-profile", target_size_kb=200)


@pytest.fixture
def loaded_config():
    """Keep the CLI hermetic: it reads a gitignored photo-uploader.yaml otherwise."""
    with patch("photo_terminal.app.cli.load_config", return_value=CONFIG) as mock:
        yield mock


@pytest.fixture
def executed():
    """Capture the context and deps the CLI hands to the pipeline."""
    with patch("photo_terminal.app.cli.execute", return_value=0) as mock:
        yield mock


# -- resolve_folder ------------------------------------------------------- #


def test_resolve_folder_accepts_a_directory(tmp_path):
    assert cli.resolve_folder(str(tmp_path)) == tmp_path.resolve()


def test_resolve_folder_rejects_a_missing_path():
    with pytest.raises(InvalidSourceFolder) as excinfo:
        cli.resolve_folder("/nonexistent/folder")

    assert "Folder does not exist" in excinfo.value.message
    assert excinfo.value.exit_code == 1


def test_resolve_folder_rejects_a_file(tmp_path):
    target = tmp_path / "test.txt"
    target.write_text("not a folder")

    with pytest.raises(InvalidSourceFolder) as excinfo:
        cli.resolve_folder(str(target))

    assert "Path is not a directory" in excinfo.value.message


# -- the parser ----------------------------------------------------------- #


def test_the_flags_are_unchanged():
    args = cli.build_parser(400).parse_args(
        ["./images", "--prefix", "japan/tokyo", "--target-size", "500", "--dry-run"]
    )

    assert args.folder_path == "./images"
    assert args.prefix == "japan/tokyo"
    assert args.target_size == 500
    assert args.dry_run is True


def test_the_optional_flags_default_to_nothing():
    args = cli.build_parser(400).parse_args(["./images"])

    assert args.prefix is None
    assert args.target_size is None
    assert args.dry_run is False


def test_the_folder_is_required(capsys):
    with pytest.raises(SystemExit):
        cli.build_parser(400).parse_args([])


def test_the_help_shows_the_configured_default_size():
    assert "default: 400" in cli.build_parser(400).format_help()


# -- the banner ----------------------------------------------------------- #


def test_the_banner_names_the_target(tmp_path):
    options = CliOptions(folder=tmp_path, prefix="japan/tokyo", target_size_kb=None, dry_run=False)

    banner = cli.render_effective_config(CONFIG, options)

    assert "Photo Upload Manager" in banner
    assert str(tmp_path) in banner
    assert "S3 bucket:      test-bucket" in banner
    assert "Target size:    200 KB" in banner
    assert "Dry-run mode:   No" in banner
    assert "Upload target: s3://test-bucket/japan/tokyo/" in banner


def test_the_banner_says_root_when_no_prefix_was_given(tmp_path):
    options = CliOptions(folder=tmp_path, prefix=None, target_size_kb=None, dry_run=False)

    banner = cli.render_effective_config(CONFIG, options)

    assert "S3 prefix:      (root)" in banner
    assert "Upload target: s3://test-bucket/" in banner


def test_the_banner_says_env_vars_when_there_is_no_profile(tmp_path):
    options = CliOptions(folder=tmp_path, prefix=None, target_size_kb=None, dry_run=False)
    config = Config(bucket="b", aws_profile=None, target_size_kb=400)

    assert "AWS profile:    (env vars)" in cli.render_effective_config(config, options)


# -- run ------------------------------------------------------------------ #


def test_run_hands_the_pipeline_a_validated_context(tmp_path, loaded_config, executed, reporter):
    assert cli.run([str(tmp_path), "--prefix", "japan/tokyo"], reporter=reporter) == 0

    ctx = executed.call_args.args[0]
    assert ctx.options == CliOptions(
        folder=tmp_path.resolve(), prefix="japan/tokyo", target_size_kb=None, dry_run=False
    )
    assert ctx.config is CONFIG


def test_target_size_overrides_the_configured_one(tmp_path, loaded_config, executed, reporter):
    cli.run([str(tmp_path), "--target-size", "500"], reporter=reporter)

    ctx = executed.call_args.args[0]
    assert ctx.config.target_size_kb == 500
    # By copy, so the loaded configuration is still what was on disk.
    assert CONFIG.target_size_kb == 200


def test_run_prints_the_banner_before_the_first_step(tmp_path, loaded_config, executed, reporter):
    cli.run([str(tmp_path)], reporter=reporter)

    assert "Photo Upload Manager" in reporter.infos[0]


def test_an_invalid_folder_never_reaches_the_pipeline(loaded_config, executed, reporter):
    assert cli.run(["/nonexistent/folder"], reporter=reporter) == 1

    executed.assert_not_called()
    assert any("Folder does not exist" in w for w in reporter.warnings)


def test_a_bad_config_never_reaches_the_parser(tmp_path, executed, reporter):
    with patch(
        "photo_terminal.app.cli.load_config",
        side_effect=ConfigError("Malformed YAML in photo-uploader.yaml"),
    ):
        assert cli.run([str(tmp_path)], reporter=reporter) == 1

    executed.assert_not_called()
    assert reporter.warnings == ["Error: Malformed YAML in photo-uploader.yaml"]


def test_run_returns_the_pipeline_exit_code(tmp_path, loaded_config, reporter):
    with patch("photo_terminal.app.cli.execute", return_value=2):
        assert cli.run([str(tmp_path)], reporter=reporter) == 2


def test_main_forwards_argv(tmp_path):
    from photo_terminal.__main__ import main

    with patch("photo_terminal.__main__.run", return_value=7) as run:
        with patch("sys.argv", ["photo-upload", str(tmp_path), "--dry-run"]):
            assert main() == 7

    assert run.call_args.args[0] == [str(tmp_path), "--dry-run"]


def test_main_is_thin():
    """The whole point of the phase: argv in, exit code out, nothing else."""
    source = Path("photo_terminal/__main__.py").read_text()

    assert len(source.splitlines()) < 40

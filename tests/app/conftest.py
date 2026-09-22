"""Fakes for driving pipeline steps without a terminal, a bucket, or Pillow.

``test_photo_upload.py`` used to reach the same code through six stacked
``@patch`` decorators per test against ``main()``. A step takes its
collaborators as a value, so these build that value instead.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from photo_terminal.app.context import CliOptions, Deps, PipelineContext
from photo_terminal.domain.models import (
    Config,
    ProcessedImage,
    ProcessingOptions,
    S3Destination,
)
from photo_terminal.reporting.dry_run import DryRunReport

CONFIG = Config(bucket="test-bucket", aws_profile="test-profile", target_size_kb=200)

OPTIONS = ProcessingOptions(
    resize=True, target_size_kb=200, preserve_exif=True, output_format="JPEG"
)

EMPTY_REPORT = DryRunReport(
    bucket="test-bucket", prefix="", target_size_kb=200, output_format="JPEG", files=()
)


def make_processed(tmp_path: Path, name: str = "photo.jpg") -> ProcessedImage:
    """A ProcessedImage whose temp file actually exists."""
    temp_path = tmp_path / name
    temp_path.write_text("optimized bytes")
    return ProcessedImage(
        original_path=Path("/source") / name,
        temp_path=temp_path,
        original_size=1_000_000,
        final_size=200_000,
        quality_used=85,
        warnings=[],
    )


def make_context(
    tmp_path: Path,
    *,
    prefix: str | None = None,
    dry_run: bool = False,
    target_size_kb: int | None = None,
    config: Config | None = None,
    **fields: object,
) -> PipelineContext:
    """A context at whatever point in the run a test needs it."""
    ctx = PipelineContext(
        config=config if config is not None else CONFIG,
        options=CliOptions(
            folder=tmp_path,
            prefix=prefix,
            target_size_kb=target_size_kb,
            dry_run=dry_run,
        ),
    )
    for name, value in fields.items():
        setattr(ctx, name, value)
    return ctx


def configured(tmp_path: Path, **fields: object) -> PipelineContext:
    """A context that has already been through configure and choose_destination."""
    fields.setdefault("processing", OPTIONS)
    fields.setdefault("destination", S3Destination("test-bucket", "japan/tokyo/"))
    return make_context(tmp_path, **fields)


class FakeDeps:
    """Builds a :class:`Deps` whose every field records what it was asked.

    Fields a test does not care about still have to be filled - a step that
    reaches for one it was not given should fail loudly rather than quietly do
    nothing - so each default raises if it is called unexpectedly only where
    that would hide a bug, and returns a benign value otherwise.
    """

    def __init__(self, reporter, **overrides: object):
        self.reporter = reporter
        self.calls: dict[str, object] = {}
        self._overrides = overrides

    def build(self) -> Deps:
        defaults: dict[str, object] = {
            "reporter": self.reporter,
            "scan_folder": lambda folder: [Path(folder) / "a.jpg"],
            "process_images": self._process_images,
            "select_images": lambda images: list(images),
            "ask_reorder": lambda: False,
            "reorder_images": lambda images: None,
            "show_processing_config": lambda images, size: OPTIONS,
            "browse_destination": lambda bucket, profile, prefix: prefix or "",
            "confirm_upload": lambda images, bucket, prefix: True,
            "check_for_duplicates": lambda images, bucket, prefix, profile: None,
            "upload_images": self._upload_images,
            "dry_run_upload": lambda *a, **kw: EMPTY_REPORT,
            "render_completion_summary": lambda *a: "UPLOAD COMPLETE",
        }
        defaults.update(self._overrides)
        return Deps(**defaults)  # type: ignore[arg-type]

    def _process_images(self, images, *args, **kwargs):
        self.calls["process_images"] = (images, args, kwargs)
        return tempfile.TemporaryDirectory(prefix="pipeline_test_"), []

    def _upload_images(self, processed, bucket, prefix, profile, **kwargs):
        self.calls["upload_images"] = (processed, bucket, prefix, profile, kwargs)
        return [f"{prefix}{p.target_filename}" for p in processed]


@pytest.fixture
def deps(reporter):
    """A :class:`FakeDeps` builder wired to a recording reporter."""

    def build(**overrides):
        return FakeDeps(reporter, **overrides).build()

    return build

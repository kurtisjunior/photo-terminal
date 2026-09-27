"""The composition root: which concrete thing fills each hole in ``Deps``."""

from __future__ import annotations

from photo_terminal.app.context import Deps
from photo_terminal.domain.errors import S3AccessError
from photo_terminal.domain.progress import ProgressReporter
from photo_terminal.imaging.processor import process_images
from photo_terminal.imaging.scanner import scan_folder
from photo_terminal.reporting.dry_run import dry_run_upload
from photo_terminal.reporting.summary import render_completion_summary
from photo_terminal.storage.duplicates import check_for_duplicates
from photo_terminal.storage.s3 import validate_s3_access
from photo_terminal.storage.uploader import upload_images
from photo_terminal.terminal.screens.confirm import confirm_upload
from photo_terminal.terminal.screens.destination import enter_upload_location
from photo_terminal.terminal.screens.processing_config import show_processing_config
from photo_terminal.terminal.screens.prompt import ask_yes_no
from photo_terminal.terminal.screens.reorder import reorder_images_interactive
from photo_terminal.terminal.screens.select import select_images

__all__ = ["REORDER_QUESTION", "build_deps", "enter_destination"]

REORDER_QUESTION = "Reorder images? (y/N): "


def enter_destination(bucket: str, aws_profile: str | None) -> str | None:
    """Validate bucket access, then ask for the upload location."""
    try:
        validate_s3_access(bucket, aws_profile)
    except S3AccessError as e:
        raise S3AccessError(f"Cannot access S3 bucket '{bucket}'\n\n{e.message}") from None
    return enter_upload_location(bucket)


def build_deps(reporter: ProgressReporter) -> Deps:
    """The production wiring: real screens, real S3, real Pillow."""
    return Deps(
        reporter=reporter,
        scan_folder=scan_folder,
        process_images=process_images,
        select_images=select_images,
        ask_reorder=lambda: ask_yes_no(REORDER_QUESTION),
        reorder_images=reorder_images_interactive,
        show_processing_config=show_processing_config,
        enter_destination=enter_destination,
        confirm_upload=confirm_upload,
        check_for_duplicates=check_for_duplicates,
        upload_images=upload_images,
        dry_run_upload=dry_run_upload,
        render_completion_summary=render_completion_summary,
    )

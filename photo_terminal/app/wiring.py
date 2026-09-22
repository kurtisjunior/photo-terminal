"""The composition root: which concrete thing fills each hole in ``Deps``.

This is the only module that names a screen and an S3 call in the same
sentence, and that is deliberate. ``browse_s3_folders`` used to do this job
from inside ``storage``, which meant the storage package imported a terminal
screen - the exact inversion the dependency contract now forbids.
"""

from __future__ import annotations

from photo_terminal.app.context import Deps
from photo_terminal.domain.errors import S3AccessError
from photo_terminal.domain.progress import ProgressReporter
from photo_terminal.imaging.processor import process_images
from photo_terminal.imaging.scanner import scan_folder
from photo_terminal.reporting.dry_run import dry_run_upload
from photo_terminal.reporting.summary import render_completion_summary
from photo_terminal.storage.duplicates import check_for_duplicates
from photo_terminal.storage.s3 import S3FolderLister, validate_s3_access
from photo_terminal.storage.uploader import upload_images
from photo_terminal.terminal.screens.confirm import confirm_upload
from photo_terminal.terminal.screens.processing_config import show_processing_config
from photo_terminal.terminal.screens.prompt import ask_yes_no
from photo_terminal.terminal.screens.reorder import reorder_images_interactive
from photo_terminal.terminal.screens.s3_browse import S3FolderBrowser
from photo_terminal.terminal.screens.select import select_images

__all__ = ["REORDER_QUESTION", "browse_destination", "build_deps"]

REORDER_QUESTION = "Reorder images? (y/N): "


def browse_destination(
    bucket: str, aws_profile: str | None, initial_prefix: str | None = None
) -> str | None:
    """Choose an upload prefix, interactively unless ``--prefix`` already did.

    Args:
        bucket: The bucket to browse.
        aws_profile: AWS CLI profile name, or ``None`` for the environment.
        initial_prefix: A prefix from the command line. When given, the browser
            is skipped and this is normalised and returned.

    Returns:
        The chosen prefix - ``""`` is the bucket root and a real answer - or
        ``None`` if the browser was quit without choosing one.

    Raises:
        S3AccessError: If the bucket cannot be reached.
        KeyboardInterrupt: If the user cancels the browser.
    """
    try:
        validate_s3_access(bucket, aws_profile)
    except S3AccessError as e:
        raise S3AccessError(f"Cannot access S3 bucket '{bucket}'\n\n{e.message}") from None

    if initial_prefix is not None:
        if initial_prefix and not initial_prefix.endswith("/"):
            initial_prefix = initial_prefix + "/"
        return initial_prefix

    return S3FolderBrowser(S3FolderLister(bucket, aws_profile)).run()


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
        browse_destination=browse_destination,
        confirm_upload=confirm_upload,
        check_for_duplicates=check_for_duplicates,
        upload_images=upload_images,
        dry_run_upload=dry_run_upload,
        render_completion_summary=render_completion_summary,
    )

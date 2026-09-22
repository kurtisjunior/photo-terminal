"""Each pipeline step, on its own.

These replace ``test_photo_upload.py``: 1,322 lines of six-deep ``@patch``
stacks against ``main()``, which could only ever assert on captured stdout and
could not reach a failure path without staging the eleven steps in front of it.

A step is a function of two values, so each test builds the context it cares
about and the two or three collaborators that step uses.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from photo_terminal.app import pipeline
from photo_terminal.app.pipeline import Outcome
from photo_terminal.domain.errors import (
    DuplicateKeyError,
    NoImagesFound,
    PhotoTerminalError,
    ProcessingError,
    S3AccessError,
    UploadFailed,
)
from photo_terminal.domain.models import ProcessingOptions, S3Destination

from .conftest import EMPTY_REPORT, OPTIONS, configured, make_context, make_processed

# -- scan ----------------------------------------------------------------- #


def test_scan_records_every_candidate(tmp_path, deps, reporter):
    ctx = make_context(tmp_path)

    assert pipeline.scan(ctx, deps()) is Outcome.CONTINUE
    assert ctx.candidates == [tmp_path / "a.jpg"]
    assert "Found 1 valid image(s)" in "".join(reporter.infos)


def test_scan_lets_an_empty_folder_fail(tmp_path, deps):
    def empty(folder: str) -> list[Path]:
        raise NoImagesFound(f"Folder is empty: {folder}")

    with pytest.raises(NoImagesFound):
        pipeline.scan(make_context(tmp_path), deps(scan_folder=empty))


# -- select --------------------------------------------------------------- #


def test_select_keeps_what_the_screen_returned(tmp_path, deps, reporter):
    ctx = make_context(tmp_path, candidates=[tmp_path / "a.jpg", tmp_path / "b.jpg"])

    assert pipeline.select(ctx, deps()) is Outcome.CONTINUE
    assert ctx.selection == ctx.candidates
    assert "Selected 2 image(s)" in "".join(reporter.infos)


def test_select_aborts_on_an_empty_selection(tmp_path, deps):
    """Cancelling is an answer. It is not an exception and not a crash."""
    ctx = make_context(tmp_path, candidates=[tmp_path / "a.jpg"])

    assert pipeline.select(ctx, deps(select_images=lambda images: [])) is Outcome.ABORT
    assert ctx.selection == []


# -- reorder -------------------------------------------------------------- #


def test_reorder_is_skipped_unless_asked_for(tmp_path, deps, reporter):
    ctx = make_context(tmp_path, selection=[tmp_path / "a.jpg"])

    assert pipeline.reorder(ctx, deps(ask_reorder=lambda: False)) is Outcome.CONTINUE
    assert ctx.ordering is None
    assert "Skipping reorder" in "".join(reporter.infos)


def test_reorder_records_the_new_filenames(tmp_path, deps):
    image = tmp_path / "a.jpg"
    ctx = make_context(tmp_path, selection=[image])

    outcome = pipeline.reorder(
        ctx,
        deps(ask_reorder=lambda: True, reorder_images=lambda images: [(image, "01_a.jpg")]),
    )

    assert outcome is Outcome.CONTINUE
    assert ctx.ordering == {image: "01_a.jpg"}


def test_reorder_aborts_when_the_screen_is_cancelled(tmp_path, deps):
    ctx = make_context(tmp_path, selection=[tmp_path / "a.jpg"])

    outcome = pipeline.reorder(
        ctx, deps(ask_reorder=lambda: True, reorder_images=lambda images: None)
    )

    assert outcome is Outcome.ABORT
    assert ctx.ordering is None


# -- configure ------------------------------------------------------------ #


def test_configure_records_the_typed_options(tmp_path, deps, reporter):
    ctx = make_context(tmp_path, selection=[tmp_path / "a.jpg"])

    assert pipeline.configure_processing(ctx, deps()) is Outcome.CONTINUE
    assert ctx.processing == OPTIONS
    assert "Output format:     JPEG" in "".join(reporter.infos)


def test_configure_is_offered_the_configured_target_size(tmp_path, deps):
    seen: list[int] = []

    def screen(images, size):
        seen.append(size)
        return OPTIONS

    pipeline.configure_processing(make_context(tmp_path), deps(show_processing_config=screen))

    assert seen == [200]


def test_configure_aborts_when_cancelled(tmp_path, deps):
    ctx = make_context(tmp_path)

    outcome = pipeline.configure_processing(
        ctx, deps(show_processing_config=lambda images, size: None)
    )

    assert outcome is Outcome.ABORT
    assert ctx.processing is None


# -- choose_destination --------------------------------------------------- #


def test_destination_takes_the_cli_prefix_without_browsing(tmp_path, deps, reporter):
    ctx = make_context(tmp_path, prefix="japan/tokyo")

    outcome = pipeline.choose_destination(
        ctx, deps(browse_destination=lambda b, p, initial: "japan/tokyo/")
    )

    assert outcome is Outcome.CONTINUE
    assert ctx.destination == S3Destination("test-bucket", "japan/tokyo/")
    assert "Select S3 upload folder" not in "".join(reporter.infos)


def test_destination_announces_the_browser_when_no_prefix_was_given(tmp_path, deps, reporter):
    pipeline.choose_destination(make_context(tmp_path), deps())

    assert "Select S3 upload folder" in "".join(reporter.infos)


def test_the_bucket_root_is_a_real_destination(tmp_path, deps):
    """An empty prefix means the root. Only ``None`` means "nothing chosen"."""
    ctx = make_context(tmp_path)

    outcome = pipeline.choose_destination(ctx, deps(browse_destination=lambda b, p, initial: ""))

    assert outcome is Outcome.CONTINUE
    assert ctx.destination == S3Destination("test-bucket", "")
    assert ctx.destination.url == "s3://test-bucket/"


def test_destination_aborts_when_the_browser_was_quit(tmp_path, deps):
    ctx = make_context(tmp_path)

    outcome = pipeline.choose_destination(ctx, deps(browse_destination=lambda b, p, initial: None))

    assert outcome is Outcome.ABORT
    assert ctx.destination is None


def test_destination_lets_an_access_failure_through(tmp_path, deps):
    def refuse(bucket, profile, initial):
        raise S3AccessError("Cannot access S3 bucket 'test-bucket'")

    with pytest.raises(S3AccessError):
        pipeline.choose_destination(make_context(tmp_path), deps(browse_destination=refuse))


# -- confirm -------------------------------------------------------------- #


def test_confirm_continues_on_yes(tmp_path, deps):
    assert pipeline.confirm(configured(tmp_path), deps()) is Outcome.CONTINUE


def test_confirm_aborts_on_no(tmp_path, deps):
    outcome = pipeline.confirm(
        configured(tmp_path), deps(confirm_upload=lambda images, bucket, prefix: False)
    )

    assert outcome is Outcome.ABORT


def test_confirm_is_asked_about_the_chosen_destination(tmp_path, deps):
    seen: list[tuple[str, str]] = []

    def ask(images, bucket, prefix):
        seen.append((bucket, prefix))
        return True

    pipeline.confirm(configured(tmp_path), deps(confirm_upload=ask))

    assert seen == [("test-bucket", "japan/tokyo/")]


# -- dry run -------------------------------------------------------------- #


def test_dry_run_is_a_no_op_without_the_flag(tmp_path, deps, reporter):
    ctx = configured(tmp_path)

    assert pipeline.dry_run(ctx, deps()) is Outcome.CONTINUE
    assert ctx.dry_run_report is None
    assert reporter.infos == []


def test_dry_run_reports_and_stops(tmp_path, deps, reporter):
    ctx = configured(tmp_path, dry_run=True)

    assert pipeline.dry_run(ctx, deps()) is Outcome.STOP
    assert ctx.dry_run_report is EMPTY_REPORT

    printed = "".join(reporter.infos)
    assert "DRY RUN MODE - No files will be uploaded" in printed
    assert "DRY RUN COMPLETE" in printed


def test_dry_run_uses_the_configured_size_when_resizing_is_off(tmp_path, deps):
    seen: list[int] = []

    def measure(images, bucket, prefix, target_size, profile, fmt, reporter=None):
        seen.append(target_size)
        return EMPTY_REPORT

    ctx = configured(
        tmp_path,
        dry_run=True,
        processing=ProcessingOptions(
            resize=False, target_size_kb=999, preserve_exif=True, output_format="JPEG"
        ),
    )
    pipeline.dry_run(ctx, deps(dry_run_upload=measure))

    assert seen == [200]  # the config's size, not the screen's


def test_dry_run_never_reaches_the_bucket(tmp_path, deps):
    """The steps that touch S3 come after it, and it returns STOP."""
    assert pipeline.PIPELINE.index(pipeline.dry_run) < pipeline.PIPELINE.index(
        pipeline.check_duplicates
    )


# -- duplicates ----------------------------------------------------------- #


def test_duplicate_check_continues_when_the_prefix_is_clear(tmp_path, deps, reporter):
    ctx = configured(tmp_path)

    assert pipeline.check_duplicates(ctx, deps()) is Outcome.CONTINUE
    assert "No duplicates found" in "".join(reporter.infos)


def test_duplicate_check_raises_rather_than_returning(tmp_path, deps):
    def conflict(images, bucket, prefix, profile):
        raise DuplicateKeyError(["a.jpg"], bucket, prefix)

    with pytest.raises(DuplicateKeyError):
        pipeline.check_duplicates(configured(tmp_path), deps(check_for_duplicates=conflict))


# -- process -------------------------------------------------------------- #


def test_process_passes_the_reorder_map_through(tmp_path, deps):
    image = tmp_path / "a.jpg"
    seen: dict[str, object] = {}

    def process(images, target, fmt, **kwargs):
        seen["images"] = images
        seen.update(kwargs)
        import tempfile

        return tempfile.TemporaryDirectory(prefix="t_"), []

    ctx = configured(tmp_path, selection=[image], ordering={image: "01_a.jpg"})
    assert pipeline.process(ctx, deps(process_images=process)) is Outcome.CONTINUE

    assert seen["images"] == [image]
    assert seen["filename_map"] == {image: "01_a.jpg"}
    assert seen["max_dimension"] == 1920


def test_process_keeps_the_temp_directory_on_the_context(tmp_path, deps):
    ctx = configured(tmp_path, selection=[tmp_path / "a.jpg"])

    pipeline.process(ctx, deps())

    assert ctx.temp_dir is not None
    ctx.temp_dir.cleanup()


def test_process_raises_a_typed_error(tmp_path, deps):
    def fail(*args, **kwargs):
        raise ProcessingError("Failed to process image 'a.jpg': broken")

    with pytest.raises(ProcessingError):
        pipeline.process(configured(tmp_path), deps(process_images=fail))


# -- upload --------------------------------------------------------------- #


def test_upload_records_the_keys_it_wrote(tmp_path, deps):
    ctx = configured(tmp_path, processed=[make_processed(tmp_path)])

    assert pipeline.upload(ctx, deps()) is Outcome.CONTINUE
    assert ctx.uploaded == ["japan/tokyo/photo.jpg"]


def test_upload_raises_rather_than_exiting(tmp_path, deps):
    def fail(*args, **kwargs):
        raise UploadFailed("Failed to upload 'photo.jpg'")

    with pytest.raises(UploadFailed):
        pipeline.upload(configured(tmp_path), deps(upload_images=fail))


# -- summary and cleanup -------------------------------------------------- #


def test_summary_is_printed(tmp_path, deps, reporter):
    ctx = configured(tmp_path, processed=[make_processed(tmp_path)], uploaded=["k"])

    assert pipeline.summarize(ctx, deps()) is Outcome.CONTINUE
    assert "UPLOAD COMPLETE" in "".join(reporter.infos)


def test_a_broken_summary_does_not_undo_a_good_upload(tmp_path, deps, reporter):
    def fail(*args):
        raise ValueError("mismatch")

    ctx = configured(tmp_path, processed=[make_processed(tmp_path)], uploaded=["k"])

    assert pipeline.summarize(ctx, deps(render_completion_summary=fail)) is Outcome.CONTINUE
    assert any("Failed to display completion summary" in w for w in reporter.warnings)
    assert "Upload completed successfully: 1 files" in "".join(reporter.infos)


def test_cleanup_removes_the_temp_directory(tmp_path, deps):
    ctx = configured(tmp_path, selection=[tmp_path / "a.jpg"])
    pipeline.process(ctx, deps())
    temp_path = Path(ctx.temp_dir.name)
    assert temp_path.exists()

    assert pipeline.cleanup(ctx, deps()) is Outcome.CONTINUE
    assert not temp_path.exists()


def test_cleanup_is_a_no_op_when_nothing_was_processed(tmp_path, deps):
    assert pipeline.cleanup(configured(tmp_path), deps()) is Outcome.CONTINUE


def test_a_failed_cleanup_only_warns(tmp_path, deps, reporter):
    class Stubborn:
        def cleanup(self) -> None:
            raise OSError("device busy")

    ctx = configured(tmp_path, temp_dir=Stubborn())

    assert pipeline.cleanup(ctx, deps()) is Outcome.CONTINUE
    assert any("Failed to cleanup temp files" in w for w in reporter.warnings)


# -- execute -------------------------------------------------------------- #


def test_a_full_run_exits_zero(tmp_path, deps, reporter):
    ctx = make_context(tmp_path, prefix="japan/tokyo")

    assert pipeline.execute(ctx, deps()) == 0
    assert "UPLOAD COMPLETE" in "".join(reporter.infos)


def test_a_dry_run_exits_zero_without_uploading(tmp_path, deps):
    uploaded: list[object] = []

    ctx = make_context(tmp_path, prefix="japan/tokyo", dry_run=True)
    assert pipeline.execute(ctx, deps(upload_images=lambda *a, **k: uploaded.append(a))) == 0
    assert uploaded == []


def test_cancelling_exits_one(tmp_path, deps):
    ctx = make_context(tmp_path)

    assert pipeline.execute(ctx, deps(select_images=lambda images: [])) == 1


def test_a_typed_failure_exits_with_its_own_code(tmp_path, deps, reporter):
    class Fatal(PhotoTerminalError):
        exit_code = 3

    def fail(folder):
        raise Fatal("the disk is on fire")

    assert pipeline.execute(make_context(tmp_path), deps(scan_folder=fail)) == 3
    assert reporter.warnings == ["Error: the disk is on fire"]


def test_ctrl_c_exits_one_from_any_step(tmp_path, deps, reporter):
    def interrupt(images):
        raise KeyboardInterrupt

    assert pipeline.execute(make_context(tmp_path), deps(select_images=interrupt)) == 1
    assert "Cancelled by user" in "".join(reporter.infos)


def test_a_failed_upload_says_the_temp_files_were_kept(tmp_path, deps, reporter):
    def fail(*args, **kwargs):
        raise UploadFailed("Failed to upload 'photo.jpg'")

    ctx = make_context(tmp_path, prefix="japan/tokyo")
    assert pipeline.execute(ctx, deps(upload_images=fail)) == 1
    assert "Temp files preserved for retry" in "".join(reporter.infos)

    # And they really are still there, for the retry that message promises.
    assert Path(ctx.temp_dir.name).exists()
    ctx.temp_dir.cleanup()


def test_every_step_is_in_the_pipeline_exactly_once():
    assert len(set(pipeline.PIPELINE)) == len(pipeline.PIPELINE)


def test_the_pipeline_runs_in_a_safe_order():
    """Nothing irreversible happens before the user has confirmed it."""
    order = list(pipeline.PIPELINE)

    assert order.index(pipeline.confirm) < order.index(pipeline.upload)
    assert order.index(pipeline.check_duplicates) < order.index(pipeline.upload)
    assert order.index(pipeline.process) < order.index(pipeline.upload)
    assert order.index(pipeline.upload) < order.index(pipeline.cleanup)

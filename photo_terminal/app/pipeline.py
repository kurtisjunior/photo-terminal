"""The run, as a list of named steps.

Each step takes the :class:`~photo_terminal.app.context.PipelineContext` and
the :class:`~photo_terminal.app.context.Deps`, does one thing, records its
answer on the context, and says whether the run continues. Failures are typed
exceptions raised by the layer that hit them, caught once in :func:`execute`,
rather than fifteen copies of ``try/except SystemExit: return 1``.

Three outcomes are possible and they are different from each other:

``CONTINUE``
    The step did its job; run the next one.
``STOP``
    There is nothing left to do and nothing went wrong - a ``--dry-run`` that
    finished its report. Exit 0.
``ABORT``
    The user declined. Not a failure of the tool, but not a completed upload
    either. Exit 1, and the step has already said why on screen.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from enum import Enum, auto

from photo_terminal.app.context import Deps, PipelineContext
from photo_terminal.domain.errors import PhotoTerminalError
from photo_terminal.domain.models import S3Destination
from photo_terminal.domain.progress import ProgressReporter
from photo_terminal.reporting.dry_run import render_header, render_report

logger = logging.getLogger(__name__)

__all__ = [
    "PIPELINE",
    "Outcome",
    "Step",
    "check_duplicates",
    "choose_destination",
    "cleanup",
    "configure_processing",
    "confirm",
    "dry_run",
    "execute",
    "process",
    "reorder",
    "report_failure",
    "scan",
    "select",
    "summarize",
    "upload",
]


class Outcome(Enum):
    """What a step says about the rest of the run."""

    CONTINUE = auto()
    STOP = auto()
    ABORT = auto()


#: A step: given what is known and who to ask, decide what happens next.
Step = Callable[[PipelineContext, Deps], Outcome]


# -- steps ---------------------------------------------------------------- #


def scan(ctx: PipelineContext, deps: Deps) -> Outcome:
    """Find every image in the source folder."""
    ctx.candidates = deps.scan_folder(str(ctx.options.folder))
    deps.reporter.info(f"Found {len(ctx.candidates)} valid image(s)\n")
    return Outcome.CONTINUE


def select(ctx: PipelineContext, deps: Deps) -> Outcome:
    """Stage 1: let the user choose which of them to upload."""
    ctx.selection = deps.select_images(ctx.candidates)

    # An empty selection is the user declining, and the screen has already
    # said so. It is not a failure and it is not an exception.
    if not ctx.selection:
        return Outcome.ABORT

    lines = [f"Selected {len(ctx.selection)} image(s):"]
    lines.extend(f"  - {image.name}" for image in ctx.selection)
    deps.reporter.info("\n".join(lines) + "\n")
    return Outcome.CONTINUE


def reorder(ctx: PipelineContext, deps: Deps) -> Outcome:
    """Stage 2: optionally give the images an explicit upload order."""
    if not deps.ask_reorder():
        deps.reporter.info("Skipping reorder - using original order\n")
        return Outcome.CONTINUE

    result = deps.reorder_images(ctx.selection)
    if result is None:
        deps.reporter.info("\nReordering cancelled")
        return Outcome.ABORT

    ctx.ordering = dict(result)
    deps.reporter.info(
        f"\n✓ Images reordered - {len(result)} images will be uploaded with numeric prefixes\n"
    )
    return Outcome.CONTINUE


def configure_processing(ctx: PipelineContext, deps: Deps) -> Outcome:
    """Stage 3: resize, EXIF and output format."""
    options = deps.show_processing_config(ctx.selection, ctx.config.target_size_kb)
    if options is None:
        deps.reporter.info("\nProcessing configuration cancelled")
        return Outcome.ABORT

    ctx.processing = options
    lines = [
        "Processing configuration:",
        f"  Resize images:     {'Yes' if options.resize else 'No'}",
    ]
    if options.resize:
        lines.append(f"  Target size:       {options.target_size_kb} KB")
    lines.append(f"  Preserve EXIF:     {'Yes' if options.preserve_exif else 'No'}")
    lines.append(f"  Output format:     {options.output_format}")
    deps.reporter.info("\n".join(lines) + "\n")
    return Outcome.CONTINUE


def choose_destination(ctx: PipelineContext, deps: Deps) -> Outcome:
    """Stage 4: pick the bucket prefix, or take the one ``--prefix`` gave."""
    if ctx.options.prefix is None:
        deps.reporter.info("\nSelect S3 upload folder:\n")

    prefix = deps.browse_destination(ctx.config.bucket, ctx.config.aws_profile, ctx.options.prefix)

    # "" is the bucket root and a real answer, so None is the only way the
    # browser can say "I was quit without choosing".
    if prefix is None:
        return Outcome.ABORT

    ctx.destination = S3Destination(bucket=ctx.config.bucket, prefix=prefix)
    deps.reporter.info(f"\nUpload target: {ctx.destination.url}\n")
    return Outcome.CONTINUE


def confirm(ctx: PipelineContext, deps: Deps) -> Outcome:
    """Show what is about to happen and ask for a yes."""
    destination = ctx.require_destination()
    if not deps.confirm_upload(ctx.selection, destination.bucket, destination.prefix):
        return Outcome.ABORT
    return Outcome.CONTINUE


def dry_run(ctx: PipelineContext, deps: Deps) -> Outcome:
    """Measure what would be uploaded and stop, when ``--dry-run`` was given."""
    if not ctx.options.dry_run:
        return Outcome.CONTINUE

    processing = ctx.require_processing()
    destination = ctx.require_destination()
    target_size = processing.target_size_kb if processing.resize else ctx.config.target_size_kb

    deps.reporter.info(
        render_header(destination.bucket, destination.prefix, target_size, processing.output_format)
    )
    deps.reporter.info("Processing images to calculate sizes...\n")

    ctx.dry_run_report = deps.dry_run_upload(
        ctx.selection,
        destination.bucket,
        destination.prefix,
        target_size,
        ctx.config.aws_profile,
        processing.output_format,
        reporter=deps.reporter,
    )
    deps.reporter.info(render_report(ctx.dry_run_report))
    return Outcome.STOP


def check_duplicates(ctx: PipelineContext, deps: Deps) -> Outcome:
    """Refuse to overwrite anything already at the destination."""
    destination = ctx.require_destination()

    deps.reporter.info("Checking for duplicate files in S3...")
    deps.check_for_duplicates(
        ctx.selection, destination.bucket, destination.prefix, ctx.config.aws_profile
    )
    deps.reporter.info("No duplicates found - proceeding with upload\n")
    return Outcome.CONTINUE


def process(ctx: PipelineContext, deps: Deps) -> Outcome:
    """Optimize the selection into a temp directory."""
    processing = ctx.require_processing()
    target_size = processing.target_size_kb if processing.resize else ctx.config.target_size_kb

    deps.reporter.info("Processing images...\n")
    ctx.temp_dir, ctx.processed = deps.process_images(
        ctx.selection,
        target_size,
        processing.output_format,
        max_dimension=1920,
        filename_map=ctx.ordering,
        reporter=deps.reporter,
    )
    return Outcome.CONTINUE


def upload(ctx: PipelineContext, deps: Deps) -> Outcome:
    """Put the optimized copies in the bucket."""
    destination = ctx.require_destination()
    ctx.uploaded = deps.upload_images(
        ctx.processed,
        destination.bucket,
        destination.prefix,
        ctx.config.aws_profile,
        reporter=deps.reporter,
    )
    return Outcome.CONTINUE


def summarize(ctx: PipelineContext, deps: Deps) -> Outcome:
    """Tell the user what was uploaded and how much it saved.

    A summary that cannot be rendered must not undo a successful upload, so
    this is the one step that swallows its own failure.
    """
    destination = ctx.require_destination()
    try:
        deps.reporter.info(
            deps.render_completion_summary(
                ctx.processed, ctx.uploaded, destination.bucket, destination.prefix
            )
        )
    except Exception as e:
        logger.debug("completion summary failed", exc_info=True)
        deps.reporter.warn(f"Warning: Failed to display completion summary: {e}")
        deps.reporter.info(f"\nUpload completed successfully: {len(ctx.uploaded)} files\n")
    return Outcome.CONTINUE


def cleanup(ctx: PipelineContext, deps: Deps) -> Outcome:
    """Remove the temp directory now that its contents are safely in S3.

    Only on success. Every earlier failure leaves it in place deliberately, so
    a retry does not have to reprocess.
    """
    if ctx.temp_dir is None:
        return Outcome.CONTINUE
    try:
        ctx.temp_dir.cleanup()
    except Exception as e:
        logger.debug("temp directory cleanup failed", exc_info=True)
        deps.reporter.warn(f"Warning: Failed to cleanup temp files: {e}")
    return Outcome.CONTINUE


#: The run, in order. This list is the program.
PIPELINE: tuple[Step, ...] = (
    scan,
    select,
    reorder,
    configure_processing,
    choose_destination,
    confirm,
    dry_run,
    check_duplicates,
    process,
    upload,
    summarize,
    cleanup,
)


# -- running it ----------------------------------------------------------- #


def report_failure(reporter: ProgressReporter, error: PhotoTerminalError) -> int:
    """Present a typed failure and hand back the exit code it carries.

    Library code no longer decides how a failure looks or what the process
    exits with. It raises, and this is the one place that answers both.
    """
    reporter.warn(f"Error: {error.message}")
    return error.exit_code


def execute(ctx: PipelineContext, deps: Deps, steps: tuple[Step, ...] = PIPELINE) -> int:
    """Run the steps in order and return the process exit code.

    Args:
        ctx: The starting state - configuration and CLI options.
        deps: The collaborators each step reaches through.
        steps: The steps to run. Defaults to :data:`PIPELINE`.

    Returns:
        ``0`` on a completed run or a finished dry run, otherwise the exit code
        carried by the failure, or ``1`` when the user cancelled.
    """
    for step in steps:
        try:
            outcome = step(ctx, deps)
        except PhotoTerminalError as e:
            return _report_step_failure(step, ctx, deps, e)
        except KeyboardInterrupt:
            deps.reporter.info("\nCancelled by user")
            return 1

        if outcome is Outcome.STOP:
            return 0
        if outcome is Outcome.ABORT:
            return 1

    return 0


def _report_step_failure(
    step: Step, ctx: PipelineContext, deps: Deps, error: PhotoTerminalError
) -> int:
    """Print the failure, plus the one piece of advice that depends on where it happened."""
    exit_code = report_failure(deps.reporter, error)
    if step is upload and ctx.temp_dir is not None:
        deps.reporter.info("\nUpload failed. Temp files preserved for retry.\n")
    return exit_code

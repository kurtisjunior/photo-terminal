"""The state a run accumulates, and the collaborators it accumulates it with.

``main()`` used to be one 283-line function whose state was fifteen local
variables and whose failure handling was ``try/except SystemExit: return 1``
repeated fifteen times. Neither the state nor any individual phase could be
reached from a test without patching a dozen module-level names at once.

Two values replace that. :class:`PipelineContext` is what a run knows so far -
it starts nearly empty and each step fills in its own field. :class:`Deps` is
everything a step talks to that is not pure: the screens, the S3 calls, the
optimizer, the reporter. A test builds a context, hands the step a ``Deps``
with fakes in the fields that step uses, and asserts on what came back.
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from photo_terminal.domain.models import (
    Config,
    ProcessedImage,
    ProcessingOptions,
    S3Destination,
)
from photo_terminal.domain.progress import ProgressReporter
from photo_terminal.reporting.dry_run import DryRunReport

__all__ = ["CliOptions", "Deps", "PipelineContext"]


@dataclass(frozen=True)
class CliOptions:
    """What the user asked for on the command line, already validated."""

    folder: Path
    prefix: str | None
    target_size_kb: int | None
    dry_run: bool


@dataclass
class PipelineContext:
    """What the run knows so far.

    Every field past ``config`` and ``options`` is filled in by exactly one
    step, which is what makes the steps orderable and individually testable.
    """

    config: Config
    options: CliOptions

    #: Every valid image in the source folder. Filled by ``scan``.
    candidates: list[Path] = field(default_factory=list)
    #: The images the user chose. Filled by ``select``.
    selection: list[Path] = field(default_factory=list)
    #: Original path -> upload filename, when the user reordered. ``None``
    #: means the original names and order stand.
    ordering: dict[Path, str] | None = None
    #: How to process them. Filled by ``configure``.
    processing: ProcessingOptions | None = None
    #: Where they go. ``None`` until ``choose_destination`` has run; an empty
    #: prefix is the bucket root and a real answer.
    destination: S3Destination | None = None
    #: The measurements a ``--dry-run`` took, if it took any.
    dry_run_report: DryRunReport | None = None
    #: Where the optimized copies live until they are uploaded. Deliberately
    #: left in place when a step after ``process`` fails, so a retry does not
    #: reprocess.
    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    #: The optimized copies. Filled by ``process``.
    processed: list[ProcessedImage] = field(default_factory=list)
    #: The S3 keys that were written. Filled by ``upload``.
    uploaded: list[str] = field(default_factory=list)

    @property
    def bucket(self) -> str:
        return self.config.bucket

    @property
    def prefix(self) -> str:
        """The chosen prefix, or ``""`` before a destination has been chosen."""
        return self.destination.prefix if self.destination is not None else ""

    def require_processing(self) -> ProcessingOptions:
        """The processing options, or an error naming the step that was skipped."""
        if self.processing is None:
            raise RuntimeError("configure_processing must run before this step")
        return self.processing

    def require_destination(self) -> S3Destination:
        """The destination, or an error naming the step that was skipped."""
        if self.destination is None:
            raise RuntimeError("choose_destination must run before this step")
        return self.destination


@dataclass(frozen=True)
class Deps:
    """Everything a step reaches outside itself.

    Each field is exactly the call the old ``main()`` made, with the same
    signature, so a step is a rewiring rather than a rewrite. Holding them here
    instead of importing them at module level is what removes the ``@patch``
    stacks: a test supplies the two or three a step actually uses.
    """

    reporter: ProgressReporter

    # imaging
    scan_folder: Callable[[str], list[Path]]
    process_images: Callable[..., tuple[tempfile.TemporaryDirectory[str], list[ProcessedImage]]]

    # terminal
    select_images: Callable[[list[Path]], list[Path]]
    ask_reorder: Callable[[], bool]
    reorder_images: Callable[[list[Path]], list[tuple[Path, str]] | None]
    show_processing_config: Callable[[list[Path], int], ProcessingOptions | None]
    browse_destination: Callable[[str, str | None, str | None], str | None]
    confirm_upload: Callable[[list[Path], str, str], bool]

    # storage
    check_for_duplicates: Callable[[list[Path], str, str, str | None], None]
    upload_images: Callable[..., list[str]]

    # reporting
    dry_run_upload: Callable[..., DryRunReport]
    render_completion_summary: Callable[[list[ProcessedImage], list[str], str, str], str]

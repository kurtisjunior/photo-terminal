"""The progress-reporting port.

``processor`` used to print ``Processing image 3/12...`` and a raw
``\\033[2K\\033[1G`` from inside its optimization loop, and ``uploader``
animated a spinner straight to ``sys.stdout``. Both now call a reporter that is
handed to them, so *what progress looks like* is a decision the pipeline makes
once, and a test can assert on the calls rather than on captured stdout.

The port is four methods wide. ``step`` is a running count, ``done`` ends that
run, and ``info``/``warn`` are one-shot messages that a console implementation
must be careful to write *after* clearing any spinner still on the line.

The port lives in ``domain`` because every layer above it reports through it
and it imports nothing itself. The concrete console implementation lives at the
other end of the dependency graph, in :mod:`photo_terminal.app.reporter`.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

__all__ = ["NullReporter", "ProgressReporter", "reporter_or_null"]


@runtime_checkable
class ProgressReporter(Protocol):
    """Where long-running library code sends its progress and its asides."""

    def step(self, current: int, total: int, label: str) -> None:
        """Report item ``current`` of ``total`` is being worked on."""
        ...

    def done(self, label: str = "") -> None:
        """End the current run of ``step`` calls, optionally with a summary."""
        ...

    def info(self, message: str) -> None:
        """Report something the user should see but need not act on."""
        ...

    def warn(self, message: str) -> None:
        """Report something that went wrong but did not stop the run."""
        ...


class NullReporter:
    """Drops everything. The default when a caller supplies no reporter."""

    def step(self, current: int, total: int, label: str) -> None:
        return None

    def done(self, label: str = "") -> None:
        return None

    def info(self, message: str) -> None:
        return None

    def warn(self, message: str) -> None:
        return None


def reporter_or_null(reporter: ProgressReporter | None) -> ProgressReporter:
    """``reporter``, or a reporter that discards everything when it is ``None``."""
    return reporter if reporter is not None else NullReporter()

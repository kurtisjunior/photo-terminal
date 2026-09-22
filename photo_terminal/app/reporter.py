"""The console :class:`~photo_terminal.domain.progress.ProgressReporter`.

This is the one place that knows a step is drawn as a spinner and a line is
erased with ``\\033[2K``. The spinner frames moved here from ``uploader.py``,
which used to animate them itself.

The reporter tracks whether a progress line is currently on screen, so a
message that arrives mid-run - a warning, an error report, the next section of
output - erases the spinner before writing rather than landing beside it.
"""

from __future__ import annotations

import sys
from typing import TextIO

__all__ = ["SPINNER_FRAMES", "ConsoleProgressReporter"]

SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

# Erase the whole line and return to column 1.
_CLEAR_LINE = "\033[2K\r"


class ConsoleProgressReporter:
    """Writes progress to a text stream, defaulting to stdout.

    The stream is resolved per write rather than captured at construction, so a
    reporter built at startup still follows ``sys.stdout`` when a test or a
    screen replaces it.
    """

    def __init__(self, stream: TextIO | None = None):
        self._stream = stream
        self._line_active = False

    @property
    def stream(self) -> TextIO:
        return self._stream if self._stream is not None else sys.stdout

    def step(self, current: int, total: int, label: str) -> None:
        frame = SPINNER_FRAMES[(current - 1) % len(SPINNER_FRAMES)]
        suffix = f" {label}" if label else ""
        self._write(f"{_CLEAR_LINE}{frame} {current}/{total}{suffix}")
        self._line_active = True

    def done(self, label: str = "") -> None:
        self._clear_active_line()
        if label:
            self._write(f"{label}\n")

    def info(self, message: str) -> None:
        self._clear_active_line()
        self._write(f"{message}\n")

    def warn(self, message: str) -> None:
        self._clear_active_line()
        self._write(f"{message}\n")

    def _clear_active_line(self) -> None:
        if self._line_active:
            self._write(_CLEAR_LINE)
            self._line_active = False

    def _write(self, text: str) -> None:
        stream = self.stream
        stream.write(text)
        stream.flush()

"""Shared test fixtures and terminal test doubles.

Two things live here:

1. Real image fixtures. Every image the suite renders has actual pixels in it.
   The previous `.touch()`ed zero-byte files could not be opened by any
   renderer, which is a large part of why a completely broken render path sat
   under a green suite.
2. ``FakeTerminal`` - a recorder that accepts the bytes a screen writes and
   reconstructs what they mean, so a test can assert on placement geometry and
   on where the cursor actually went.

The geometry primitives it reconstructs into now come from the production
package, so a test and the code under test cannot disagree about what a cell
coordinate is.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import termios
import tty
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from photo_terminal.terminal.background import BackgroundWorker
from photo_terminal.terminal.geometry import CellMetrics, Point, Size
from photo_terminal.terminal.layout import Layout
from photo_terminal.terminal.preview.service import PreviewService

FIXTURES = Path(__file__).parent / "fixtures"

# A measured 8x16 cell: the shape a terminal reporting its pixel dimensions
# would give us, and the shape the half-block renderer assumes by construction.
MEASURED_CELL = CellMetrics(px=Size(8, 16), measured=True)


# --------------------------------------------------------------------------- #
# Session options
# --------------------------------------------------------------------------- #


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--no-skips",
        action="store_true",
        default=False,
        help="Fail the session if any test was skipped. Used by CI: a skip is a "
        "test that silently stopped testing anything.",
    )


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if not session.config.getoption("--no-skips"):
        return
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if reporter is None:
        return
    skipped = reporter.stats.get("skipped", [])
    if not skipped:
        return
    reporter.write_sep("=", f"{len(skipped)} skipped test(s); --no-skips was requested")
    for report in skipped:
        reporter.write_line(f"  {report.nodeid}")
    session.exitstatus = pytest.ExitCode.TESTS_FAILED


@pytest.fixture(autouse=True)
def close_background_workers(monkeypatch: pytest.MonkeyPatch):
    """Close every :class:`BackgroundWorker` a test constructs.

    A screen owns its worker for its own lifetime and closes it in ``run()``'s
    ``finally``. A test that builds a screen without running it would otherwise
    leak the worker's pipe pair - two descriptors per construction, growing
    with the suite. ``close()`` is idempotent.
    """
    created: list[BackgroundWorker] = []
    original = BackgroundWorker.__init__

    def tracking_init(worker: BackgroundWorker, *args: object, **kwargs: object) -> None:
        original(worker, *args, **kwargs)  # type: ignore[arg-type]
        created.append(worker)

    monkeypatch.setattr(BackgroundWorker, "__init__", tracking_init)
    yield
    for worker in created:
        worker.close()


@pytest.fixture(autouse=True)
def close_preview_services(monkeypatch: pytest.MonkeyPatch):
    """Close every :class:`PreviewService` a test constructs.

    A screen owns its service for its own lifetime and closes it in ``run()``'s
    ``finally``. A test that builds a screen without running it would otherwise
    leak the service's pipe pair - two descriptors per construction, growing with
    the suite. ``close()`` is idempotent, so a test that closes its own service
    is unaffected.
    """
    created: list[PreviewService] = []
    original = PreviewService.__init__

    def tracking_init(service: PreviewService, *args: object, **kwargs: object) -> None:
        original(service, *args, **kwargs)  # type: ignore[arg-type]
        created.append(service)

    monkeypatch.setattr(PreviewService, "__init__", tracking_init)
    yield
    for service in created:
        service.close()


# --------------------------------------------------------------------------- #
# Scripted keyboard input
# --------------------------------------------------------------------------- #


@pytest.fixture
def scripted_keys(monkeypatch: pytest.MonkeyPatch):
    """Drive a screen's input loop from a list of characters.

    Every screen now reads through ``terminal.input``, so one fake serves all of
    them. The characters are fed one at a time exactly as a terminal would
    deliver them, escape sequences included: ``["\x1b", "[", "B"]`` is a down
    arrow. ``termios`` and ``tty`` are neutralised at the same time, because a
    test process's stdin is not a terminal and the session would otherwise
    decline to enter raw mode.
    """

    def install(keys: Sequence[str]) -> MagicMock:
        reader = MagicMock(side_effect=list(keys))
        monkeypatch.setattr(sys.stdin, "read", reader, raising=False)
        monkeypatch.setattr(sys.stdin, "fileno", lambda: 0, raising=False)
        monkeypatch.setattr(termios, "tcgetattr", lambda fd: [])
        monkeypatch.setattr(termios, "tcsetattr", lambda fd, when, mode: None)
        monkeypatch.setattr(tty, "setraw", lambda fd, when=None: None)
        return reader

    return install


# --------------------------------------------------------------------------- #
# FakeTerminal
# --------------------------------------------------------------------------- #

# Cursor position: CSI row ; col H (or f). Missing parameters default to 1.
_CUP = re.compile(rb"\x1b\[(\d*)(?:;(\d*))?[Hf]")
# Any CSI sequence: parameter bytes, then intermediates, then one final byte.
_CSI = re.compile(r"\x1b\[([\x30-\x3f]*)([\x20-\x2f]*)([\x40-\x7e])")


@dataclass
class FakeTerminal:
    """Records every byte written, and reconstructs what it means.

    The replay is deliberately literal: it does not wrap at the right margin
    and does not scroll at the bottom, so a write that lands outside the
    terminal shows up as an out-of-bounds cell rather than being silently
    folded back inside. That is the signal ``cells_touched`` exists to expose.
    """

    size: os.terminal_size = field(default_factory=lambda: os.terminal_size((178, 58)))
    # What TIOCGWINSZ would have reported; None means the pixel fields were zero.
    cell_px: Size | None = None
    # The column the preview is anchored at, used by preview_payload(). Left
    # at None it follows the layout for this terminal size, which is what the
    # screen under test will have used.
    preview_column: int | None = None
    _buffer: bytearray = field(default_factory=bytearray, repr=False)

    def __post_init__(self) -> None:
        if self.preview_column is None:
            self.preview_column = Layout.for_terminal(self.size, MEASURED_CELL).preview_box.left

    # -- writing ---------------------------------------------------------- #

    def write(self, data: bytes) -> None:
        self._buffer.extend(data)

    def write_text(self, data: str) -> None:
        self.write(data.encode("utf-8", errors="replace"))

    def flush(self) -> None:
        """Present so the recorder can stand in for a stream. A no-op."""

    @property
    def bytes_written(self) -> bytes:
        return bytes(self._buffer)

    def as_stdout(self) -> _TextStream:
        """A ``sys.stdout`` stand-in backed by this recorder."""
        return _TextStream(self)

    # -- reconstruction --------------------------------------------------- #

    def kitty_commands(self) -> list[dict[str, str]]:
        r"""Each ``\x1b_G...\x1b\`` control block, parsed to its key/value pairs.

        The base64 payload after the first ``;`` is dropped; only the control
        keys are returned. A chunk with no control keys yields an empty dict.
        """
        commands: list[dict[str, str]] = []
        text = self._decoded()
        start = 0
        while True:
            open_at = text.find("\x1b_G", start)
            if open_at == -1:
                return commands
            close_at = text.find("\x1b\\", open_at)
            body = text[open_at + 3 : close_at if close_at != -1 else len(text)]
            control = body.split(";", 1)[0]
            command: dict[str, str] = {}
            for pair in control.split(","):
                key, _, value = pair.partition("=")
                if key:
                    command[key] = value
            commands.append(command)
            start = (close_at + 2) if close_at != -1 else len(text)

    def cells_touched(self) -> set[Point]:
        """Replay cursor moves and printable runs; which cells were written.

        Spaces count as writes: the screens pad their panes with spaces
        specifically to overwrite stale content.
        """
        touched: set[Point] = set()
        row, col = 1, 1
        text = self._decoded()
        i = 0
        while i < len(text):
            ch = text[i]

            if ch == "\x1b":
                if text.startswith("\x1b_G", i):
                    # A graphics command. Its cell footprint is asserted from
                    # kitty_commands(); it does not print text cells, and a
                    # well-formed placement carries C=1 so the cursor is still.
                    close_at = text.find("\x1b\\", i)
                    i = (close_at + 2) if close_at != -1 else len(text)
                    continue
                match = _CSI.match(text, i)
                if match:
                    row, col = self._apply_csi(match, row, col)
                    i = match.end()
                    continue
                i += 2  # ESC + one byte: ESC \, ESC ), ...
                continue

            if ch == "\r":
                col = 1
            elif ch == "\n":
                row += 1
            elif ch == "\b":
                col = max(1, col - 1)
            elif ch == "\t":
                col += 8 - ((col - 1) % 8)
            else:
                touched.add(Point(col, row))
                col += 1
            i += 1

        return touched

    def preview_payload(self) -> bytes:
        """Bytes written between the preview anchor and the end of the frame.

        The anchor is the last cursor-position escape that lands at or right of
        ``preview_column`` - i.e. the point at which the screen handed over to
        the preview.
        """
        anchor: int | None = None
        for match in _CUP.finditer(self._buffer):
            column = int(match.group(2) or b"1")
            if column >= self.preview_column:
                anchor = match.end()
        if anchor is None:
            return b""
        return bytes(self._buffer[anchor:])

    # -- internals -------------------------------------------------------- #

    def _decoded(self) -> str:
        return self._buffer.decode("utf-8", errors="replace")

    @staticmethod
    def _apply_csi(match: re.Match[str], row: int, col: int) -> tuple[int, int]:
        params, _intermediates, final = match.groups()
        if params.startswith("?"):
            return row, col  # private mode set/reset: ?25l, ?1049h, ...

        def arg(index: int, default: int = 1) -> int:
            fields = params.split(";")
            if index >= len(fields) or not fields[index]:
                return default
            return int(fields[index])

        if final in "Hf":
            return max(1, arg(0)), max(1, arg(1))
        if final == "A":
            return max(1, row - arg(0)), col
        if final == "B":
            return row + arg(0), col
        if final == "C":
            return row, col + arg(0)
        if final == "D":
            return row, max(1, col - arg(0))
        if final == "G":
            return row, max(1, arg(0))
        if final == "d":
            return max(1, arg(0)), col
        # J (erase display), K (erase line), m (SGR), h/l, r, s, u: no move, and
        # erasure is not a write.
        return row, col


@dataclass
class _TextStream:
    """Text-mode ``sys.stdout`` stand-in over a :class:`FakeTerminal`."""

    terminal: FakeTerminal
    encoding: str = "utf-8"

    def write(self, data: str) -> int:
        self.terminal.write_text(data)
        return len(data)

    def flush(self) -> None:
        pass

    def isatty(self) -> bool:
        return True

    def fileno(self) -> int:
        return 1

    @property
    def buffer(self) -> _ByteStream:
        return _ByteStream(self.terminal)


@dataclass
class _ByteStream:
    """Binary ``sys.stdout.buffer`` stand-in over a :class:`FakeTerminal`."""

    terminal: FakeTerminal

    def write(self, data: bytes) -> int:
        self.terminal.write(data)
        return len(data)

    def flush(self) -> None:
        pass


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture
def fake_term() -> FakeTerminal:
    """A recorder sized to the 178x58 window from the bug report screenshot."""
    return FakeTerminal(size=os.terminal_size((178, 58)), cell_px=MEASURED_CELL.px)


@pytest.fixture
def measured_cell() -> CellMetrics:
    """An 8x16 cell, as a terminal that reports its pixel dimensions would."""
    return MEASURED_CELL


@pytest.fixture
def portrait_3x4() -> Path:
    """300x400 JPEG. Known 3:4 aspect ratio."""
    return FIXTURES / "portrait_3x4.jpg"


@pytest.fixture
def landscape_4x3() -> Path:
    """400x300 JPEG. Known 4:3 aspect ratio."""
    return FIXTURES / "landscape_4x3.jpg"


@pytest.fixture
def tiny_40x30() -> Path:
    """40x30 PNG. Smaller than any preview box; must never be upscaled."""
    return FIXTURES / "tiny_40x30.png"


@pytest.fixture
def photo_2400x1800() -> Path:
    """A photographic 2400x1800 JPEG, large enough to exercise the optimizer.

    Above the optimizer's 1920px max dimension, and above 400KB at quality 95
    after that resize, so the quality-iteration loop genuinely runs.
    """
    return FIXTURES / "photo_2400x1800.jpg"


@pytest.fixture
def sample_images(tmp_path: Path) -> list[Path]:
    """Three real images in a scratch folder, named as a scan would find them."""
    sources = ["portrait_3x4.jpg", "landscape_4x3.jpg", "tiny_40x30.png"]
    images = []
    for index, source in enumerate(sources):
        destination = tmp_path / f"image{index}{Path(source).suffix}"
        shutil.copyfile(FIXTURES / source, destination)
        images.append(destination)
    return images

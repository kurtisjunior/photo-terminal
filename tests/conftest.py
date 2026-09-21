"""Shared test fixtures and terminal test doubles.

Three things live here:

1. Real image fixtures. Every image the suite renders now has actual pixels in
   it. The previous `.touch()`ed zero-byte files could not be opened by any
   renderer, which is a large part of why a completely broken render path sat
   under a green suite.
2. ``FakeTerminal`` - a recorder that accepts the bytes a screen writes and
   reconstructs what they mean, so a test can assert on placement geometry and
   on where the cursor actually went.
3. A recorded ``viu`` block-fallback capture, so the current defect mechanism
   can be pinned deterministically on a machine that has no ``viu`` installed.

``Size``, ``Point`` and ``Rect`` are defined here for now. Phase 2 moves them
into ``photo_terminal/terminal/geometry.py`` and this module imports them.
"""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


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


# --------------------------------------------------------------------------- #
# Geometry primitives
# --------------------------------------------------------------------------- #


class Size(NamedTuple):
    """A width/height pair. Units are stated by the field that holds it."""

    w: int
    h: int


class Point(NamedTuple):
    """A 1-based cell coordinate, matching ANSI cursor addressing."""

    col: int
    row: int


@dataclass(frozen=True)
class Rect:
    """A 1-based, inclusive-origin rectangle of terminal cells."""

    left: int
    top: int
    width: int
    height: int

    @property
    def origin(self) -> Point:
        return Point(self.left, self.top)

    @property
    def cells(self) -> frozenset[Point]:
        return frozenset(
            Point(col, row)
            for row in range(self.top, self.top + self.height)
            for col in range(self.left, self.left + self.width)
        )

    def __or__(self, other: Rect | frozenset[Point]) -> frozenset[Point]:
        return self.cells | (other.cells if isinstance(other, Rect) else other)

    __ror__ = __or__


@dataclass(frozen=True)
class ExpectedLayout:
    """The geometry the preview is *supposed* to respect.

    This encodes the intended two-pane split so a test can assert on it before
    the production code has a single source of truth for it. Phase 2 replaces
    this with ``photo_terminal.terminal.layout.Layout``.
    """

    list_pane: Rect
    preview_box: Rect

    @classmethod
    def for_terminal(cls, size: os.terminal_size) -> ExpectedLayout:
        list_width = 55
        preview_left = 60
        return cls(
            list_pane=Rect(left=1, top=1, width=list_width, height=size.lines),
            preview_box=Rect(
                left=preview_left,
                top=1,
                width=max(0, size.columns - preview_left - 1),
                height=max(0, size.lines - 2),
            ),
        )


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
    # The column the preview is anchored at, used by preview_payload().
    preview_column: int = 60
    _buffer: bytearray = field(default_factory=bytearray, repr=False)

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
    return FakeTerminal(size=os.terminal_size((178, 58)))


@pytest.fixture
def viu_block_capture() -> bytes:
    r"""Real ``viu`` 1.6.1 output captured with stdout on a pipe.

    Recorded with::

        env -i TERM=xterm-ghostty TERM_PROGRAM=ghostty COLORTERM=truecolor \
            viu -w 116 -h 56 tests/fixtures/portrait_3x4.jpg > viu_block_capture.bin

    116x56 cells is what the current graphics path asks for on a 178x58
    terminal. The capture opens with viu's 35-byte Kitty capability probe plus
    the ``\x1b[c`` DA1 fallback, contains no ``a=T`` placement anywhere, and
    continues as 56 rows of 116 half-block cells separated by ``\r\n``.
    """
    return (FIXTURES / "viu_block_capture.bin").read_bytes()


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

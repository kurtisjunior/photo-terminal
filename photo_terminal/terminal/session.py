"""One owner for the terminal's state, with one teardown path.

Raw-mode setup used to be copy-pasted across four screens with four different
teardowns: one restored termios and nothing else, one left the cursor hidden,
two cleared the screen and destroyed the user's scrollback. A context manager
makes the pairing structural - whatever the body does, and however it leaves,
the terminal is handed back in the state it was found in.

Entering the alternate screen buffer is what makes "the app left junk on my
terminal" impossible rather than merely unlikely: the whole session paints on a
throwaway buffer, and leaving it restores the user's prompt and scrollback
untouched. It is also a second safety net under the Kitty ``a=d`` delete, since
graphics placements die with the buffer they were placed on.
"""

from __future__ import annotations

import signal
import sys
import termios
import tty
from types import FrameType, TracebackType
from typing import Any

from photo_terminal.terminal.frame import HIDE_CURSOR, SHOW_CURSOR, ByteSink, Frame

ALT_SCREEN_ON = "\033[?1049h"
ALT_SCREEN_OFF = "\033[?1049l"

#: Alternate screen on, cursor hidden. Ordered so the cursor is never briefly
#: visible on the fresh buffer.
ENTER = ALT_SCREEN_ON + HIDE_CURSOR
#: Cursor back, alternate screen off - the exact inverse, in the inverse order.
EXIT = SHOW_CURSOR + ALT_SCREEN_OFF

#: Signals that would otherwise kill the process with the terminal still in raw
#: mode and still on the alternate buffer.
_FATAL_SIGNALS = (signal.SIGTERM, signal.SIGHUP)


class TerminalSession:
    """Owns raw mode, the alternate screen and cursor visibility.

    Use it as a context manager::

        with TerminalSession():
            ...  # paint and read keys

    ``__exit__`` runs on every path out of the body - normal return, exception,
    ``SystemExit`` - and a handler installed for ``SIGTERM``/``SIGHUP`` covers
    the one case a ``finally`` cannot.
    """

    def __init__(self, sink: ByteSink | None = None) -> None:
        """Args:
        sink: Where the session's escape sequences go. Defaults to stdout.
            Tests pass a recorder so the byte sequence can be asserted on.
        """
        self._sink = sink
        self._fd: int | None = None
        # What `termios.tcgetattr` handed us. Its element type is a union of
        # ints and lists that only `tcsetattr` needs to understand.
        self._saved_mode: list[Any] | None = None
        self._saved_handlers: dict[int, object] = {}
        self._active = False

    # -- the context manager ---------------------------------------------- #

    def __enter__(self) -> TerminalSession:
        self._fd = _input_fd()
        self._enter_raw_mode()
        self._install_signal_handlers()
        self._write(ENTER)
        self._active = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Restore the terminal. Never suppresses the exception that got here."""
        self._restore()

    # -- state ------------------------------------------------------------ #

    @property
    def fd(self) -> int | None:
        """The descriptor raw mode was applied to, or ``None`` if there wasn't one."""
        return self._fd

    @property
    def raw(self) -> bool:
        """Whether raw mode is actually in effect.

        ``False`` when stdin is not a terminal - a pipe, a captured stream under
        a test runner - in which case the session degrades to painting only.
        """
        return self._saved_mode is not None

    # -- internals -------------------------------------------------------- #

    def _enter_raw_mode(self) -> None:
        if self._fd is None:
            return
        try:
            self._saved_mode = termios.tcgetattr(self._fd)
            tty.setraw(self._fd)
        except (termios.error, OSError, ValueError):
            self._saved_mode = None
            return
        self._restore_output_processing()

    def _restore_output_processing(self) -> None:
        """Put ``OPOST``/``ONLCR`` back after ``setraw`` cleared them.

        Raw mode is about *input*: no line buffering, no echo, no signal
        characters. Clearing output post-processing as well is an unrelated
        side effect of ``tty.setraw``, and it is why a screen that prints
        through Rich stair-steps down the display - a bare ``\\n`` moves down
        without returning to column 1. The painter never relies on either, so
        turning output processing back on costs it nothing.
        """
        if self._fd is None:
            return
        try:
            mode = termios.tcgetattr(self._fd)
            mode[1] |= termios.OPOST | termios.ONLCR
            termios.tcsetattr(self._fd, termios.TCSADRAIN, mode)
        except (termios.error, OSError, ValueError, IndexError, TypeError):
            # A stand-in termios (tests) or a descriptor that stopped being a
            # terminal. Raw mode is already in effect; this is a refinement.
            return

    def _install_signal_handlers(self) -> None:
        """Restore the terminal before a fatal signal takes the process down.

        ``__exit__`` cannot run for a default-disposition ``SIGTERM``, so the
        handler does the restore and then re-raises the signal with the default
        handler back in place - the process still dies of exactly what killed
        it, but with a usable terminal behind it.
        """
        for signum in _FATAL_SIGNALS:
            try:
                self._saved_handlers[signum] = signal.signal(signum, self._on_fatal_signal)
            except (ValueError, OSError):
                # Not the main thread, or a platform without this signal.
                continue

    def _on_fatal_signal(self, signum: int, frame: FrameType | None) -> None:
        self._restore()
        signal.signal(signum, signal.SIG_DFL)
        signal.raise_signal(signum)

    def _restore(self) -> None:
        """Undo everything ``__enter__`` did. Safe to call more than once."""
        if not self._active:
            return
        self._active = False
        self._write(EXIT)
        self._restore_signal_handlers()
        if self._fd is not None and self._saved_mode is not None:
            try:
                termios.tcsetattr(self._fd, termios.TCSADRAIN, self._saved_mode)
            except (termios.error, OSError, ValueError):
                pass
            self._saved_mode = None

    def _restore_signal_handlers(self) -> None:
        for signum, handler in self._saved_handlers.items():
            try:
                signal.signal(signum, handler)  # type: ignore[arg-type]
            except (ValueError, OSError):
                continue
        self._saved_handlers.clear()

    def _write(self, escapes: str) -> None:
        frame = Frame()
        frame.write(escapes)
        frame.flush(self._sink)


def _input_fd() -> int | None:
    """The descriptor keys arrive on, or ``None`` when stdin is detached."""
    try:
        fd = sys.stdin.fileno()
    except (OSError, AttributeError, ValueError):
        return None
    return fd if isinstance(fd, int) else None

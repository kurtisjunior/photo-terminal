"""Tests for :class:`TerminalSession`.

The session is the one thing standing between a crash and a terminal the user
has to `reset`. Everything here is about the guarantee that whatever happened
inside the body, the bytes that leave the terminal in a usable state were
written and the saved termios mode was put back.
"""

from __future__ import annotations

import signal
import sys
import termios
import tty

import pytest

from photo_terminal.terminal.frame import HIDE_CURSOR, SHOW_CURSOR
from photo_terminal.terminal.session import ALT_SCREEN_OFF, ALT_SCREEN_ON, TerminalSession
from tests.conftest import FakeTerminal


@pytest.fixture
def fake_termios(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[object]]:
    """Stand in for a real terminal on fd 0, recording what was applied to it."""
    calls: dict[str, list[object]] = {"setraw": [], "tcsetattr": []}
    saved_mode = ["saved-mode"]

    monkeypatch.setattr(sys.stdin, "fileno", lambda: 0, raising=False)
    monkeypatch.setattr(termios, "tcgetattr", lambda fd: saved_mode)
    monkeypatch.setattr(
        termios, "tcsetattr", lambda fd, when, mode: calls["tcsetattr"].append(mode)
    )
    monkeypatch.setattr(tty, "setraw", lambda fd, when=None: calls["setraw"].append(fd))
    calls["saved_mode"] = saved_mode
    return calls


def test_enter_and_exit_write_the_inverse_sequences(fake_termios):
    """The alternate screen goes on at enter and off at exit, cursor likewise."""
    recorder = FakeTerminal()

    with TerminalSession(sink=recorder):
        entered = recorder.bytes_written.decode()

    written = recorder.bytes_written.decode()

    assert entered == ALT_SCREEN_ON + HIDE_CURSOR
    assert written == ALT_SCREEN_ON + HIDE_CURSOR + SHOW_CURSOR + ALT_SCREEN_OFF


def test_body_paints_between_the_two_transitions(fake_termios):
    """Nothing the body writes can escape the alternate screen."""
    recorder = FakeTerminal()

    with TerminalSession(sink=recorder):
        recorder.write_text("the whole UI")

    written = recorder.bytes_written.decode()
    assert written.index(ALT_SCREEN_ON) < written.index("the whole UI")
    assert written.index("the whole UI") < written.index(ALT_SCREEN_OFF)


def test_raw_mode_is_entered_once(fake_termios):
    with TerminalSession(sink=FakeTerminal()):
        pass

    assert fake_termios["setraw"] == [0]


def test_termios_is_restored_when_the_body_raises(fake_termios):
    """The teardown is not conditional on a clean exit - that is the point."""
    recorder = FakeTerminal()

    with pytest.raises(RuntimeError, match="boom"), TerminalSession(sink=recorder):
        raise RuntimeError("boom")

    assert fake_termios["saved_mode"] in fake_termios["tcsetattr"]
    assert recorder.bytes_written.decode().endswith(SHOW_CURSOR + ALT_SCREEN_OFF)


def test_systemexit_from_the_body_still_restores(fake_termios):
    """`q` on the S3 browser leaves via SystemExit, not a return."""
    recorder = FakeTerminal()

    with pytest.raises(SystemExit), TerminalSession(sink=recorder):
        raise SystemExit(1)

    assert fake_termios["saved_mode"] in fake_termios["tcsetattr"]


def test_keyboardinterrupt_propagates_and_still_restores(fake_termios):
    """Ctrl-C converges: every screen propagates it, the session cleans up."""
    recorder = FakeTerminal()

    with pytest.raises(KeyboardInterrupt), TerminalSession(sink=recorder):
        raise KeyboardInterrupt

    assert fake_termios["saved_mode"] in fake_termios["tcsetattr"]
    assert ALT_SCREEN_OFF in recorder.bytes_written.decode()


def test_output_processing_is_restored_after_setraw(monkeypatch):
    """`tty.setraw` also clears OPOST, which is not what raw *input* means.

    A screen that prints through Rich would stair-step down the display without
    it, so the session puts the output flags back.
    """
    mode = [0, 0, 0, 0, 0, 0, []]
    applied: list[list[int]] = []

    monkeypatch.setattr(sys.stdin, "fileno", lambda: 0, raising=False)
    monkeypatch.setattr(termios, "tcgetattr", lambda fd: list(mode))
    monkeypatch.setattr(termios, "tcsetattr", lambda fd, when, m: applied.append(m))
    monkeypatch.setattr(tty, "setraw", lambda fd, when=None: None)

    with TerminalSession(sink=FakeTerminal()):
        pass

    assert applied, "the session never wrote a termios mode back"
    output_flags = applied[0][1]
    assert output_flags & termios.OPOST
    assert output_flags & termios.ONLCR


def test_a_detached_stdin_degrades_to_painting_only(monkeypatch):
    """No terminal to put into raw mode is not a reason to fail."""

    def no_descriptor():
        raise OSError("not a terminal")

    monkeypatch.setattr(sys.stdin, "fileno", no_descriptor, raising=False)
    recorder = FakeTerminal()

    with TerminalSession(sink=recorder) as session:
        assert session.fd is None
        assert session.raw is False

    assert recorder.bytes_written.decode().endswith(ALT_SCREEN_OFF)


def test_a_stdin_that_is_not_a_terminal_degrades_to_painting_only(monkeypatch):
    monkeypatch.setattr(sys.stdin, "fileno", lambda: 0, raising=False)
    monkeypatch.setattr(
        termios, "tcgetattr", lambda fd: (_ for _ in ()).throw(termios.error("not a tty"))
    )
    recorder = FakeTerminal()

    with TerminalSession(sink=recorder) as session:
        assert session.raw is False

    assert ALT_SCREEN_OFF in recorder.bytes_written.decode()


def test_sigterm_restores_the_terminal_before_the_process_dies(fake_termios):
    """`__exit__` cannot run for a default-disposition SIGTERM; a handler can."""
    recorder = FakeTerminal()
    installed: dict[int, object] = {}
    original = signal.signal

    def record(signum, handler):
        previous = installed.get(signum, signal.SIG_DFL)
        installed[signum] = handler
        return previous

    with pytest.MonkeyPatch.context() as patched:
        patched.setattr(signal, "signal", record)
        patched.setattr(signal, "raise_signal", lambda signum: None)
        with TerminalSession(sink=recorder):
            handler = installed[signal.SIGTERM]
            assert handler is not signal.SIG_DFL
            handler(signal.SIGTERM, None)  # the signal arrives mid-session

            # Restored on the spot, not at the end of the block.
            assert fake_termios["saved_mode"] in fake_termios["tcsetattr"]
            assert recorder.bytes_written.decode().endswith(SHOW_CURSOR + ALT_SCREEN_OFF)
            # And the default disposition is back, so the process still dies.
            assert installed[signal.SIGTERM] is signal.SIG_DFL

    assert original is signal.signal


def test_the_previous_signal_handler_is_put_back(fake_termios):
    """A session must not permanently own the process's SIGTERM."""
    before = signal.getsignal(signal.SIGTERM)

    with TerminalSession(sink=FakeTerminal()):
        assert signal.getsignal(signal.SIGTERM) is not before

    assert signal.getsignal(signal.SIGTERM) is before


def test_restoring_twice_is_harmless(fake_termios):
    """The SIGTERM handler and `__exit__` can both fire; only one takes effect."""
    recorder = FakeTerminal()

    session = TerminalSession(sink=recorder)
    with session:
        pass
    session.__exit__(None, None, None)

    assert recorder.bytes_written.decode().count(ALT_SCREEN_OFF) == 1

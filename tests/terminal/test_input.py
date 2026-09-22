"""Tests for the one keyboard reader.

`input_utils` has been in the package since the beginning and has never had a
test of its own; it was only ever exercised incidentally, through the two
screens that used it. The other two hand-rolled `sys.stdin.read(1)` instead and
got ESC wrong - a bare Escape blocked until the next keypress. Now that all
four go through here, this is where that behaviour is pinned down.
"""

from __future__ import annotations

import os

import pytest

from photo_terminal.terminal.input import (
    KEY_DOWN,
    KEY_ESC,
    KEY_UP,
    read_key,
    read_key_with_timeout,
    read_key_with_timeout_or_signal,
)


@pytest.fixture
def tty_pair():
    """A real pipe standing in for the terminal, so `select` genuinely blocks.

    The mock-based path is covered by the screen tests; this exercises the
    descriptor-level path, which is the one that actually runs in production
    and the only one where the ESC timeout means anything.
    """
    read_fd, write_fd = os.pipe()
    try:
        yield read_fd, write_fd
    finally:
        for fd in (read_fd, write_fd):
            try:
                os.close(fd)
            except OSError:
                pass


@pytest.fixture
def keys(tty_pair, monkeypatch):
    """Feed bytes to the reader as the terminal would."""
    read_fd, write_fd = tty_pair

    class _Stdin:
        def fileno(self) -> int:
            return read_fd

        def read(self, size: int = 1) -> str:
            return os.read(read_fd, size).decode()

    monkeypatch.setattr("sys.stdin", _Stdin())

    def send(data: str) -> None:
        os.write(write_fd, data.encode())

    return send


class TestOrdinaryKeys:
    def test_a_printable_character_comes_back_as_itself(self, keys):
        keys("y")
        assert read_key() == "y"

    def test_control_characters_are_passed_through(self, keys):
        """Ctrl-C and Enter are decided by the screens, not here."""
        keys("\x03")
        assert read_key() == "\x03"
        keys("\r")
        assert read_key() == "\r"


class TestEscape:
    def test_a_bare_escape_resolves_after_the_timeout(self, keys):
        """The defect the two hand-rolled loops had: this must not block."""
        keys("\x1b")
        assert read_key(timeout_sec=0.05) == KEY_ESC

    def test_escape_followed_by_a_plain_character_is_still_escape(self, keys):
        """Meta-<key> is not a key this app has any use for."""
        keys("\x1bz")
        assert read_key(timeout_sec=0.05) == KEY_ESC

    def test_up_arrow_decodes(self, keys):
        keys("\x1b[A")
        assert read_key(timeout_sec=0.05) == KEY_UP

    def test_down_arrow_decodes(self, keys):
        keys("\x1b[B")
        assert read_key(timeout_sec=0.05) == KEY_DOWN

    def test_the_ss3_spelling_of_an_arrow_decodes(self, keys):
        """Application cursor mode sends ESC O A rather than ESC [ A."""
        keys("\x1bOA")
        assert read_key(timeout_sec=0.05) == KEY_UP

    def test_an_unrecognised_sequence_is_dropped(self, keys):
        """A terminal reply must not reach the screen as a keystroke.

        This is why the Kitty emitter sets `q=2`: the fewer replies arrive, the
        less this matters - but the reader has to drop the ones that do.
        """
        keys("\x1b[?62;c")
        assert read_key(timeout_sec=0.05) is None

    def test_a_left_arrow_is_dropped_rather_than_guessed_at(self, keys):
        """No screen navigates horizontally; ESC [ D is not ESC."""
        keys("\x1b[D")
        assert read_key(timeout_sec=0.05) is None


class TestTimeouts:
    def test_no_input_within_the_timeout_returns_none(self, keys):
        assert read_key_with_timeout(timeout_sec=0.01) is None

    def test_input_within_the_timeout_is_returned(self, keys):
        keys("q")
        assert read_key_with_timeout(timeout_sec=0.05) == "q"

    def test_an_idle_poll_returns_none(self, keys):
        assert read_key_with_timeout_or_signal(0.01) is None

    def test_stdin_wins_when_both_it_and_an_extra_fd_are_ready(self, keys, tty_pair):
        """A background preview waking the loop is not a keystroke.

        The caller is expected to check its own signal source and repaint; a
        key typed in the meantime must still be there on the next poll.
        """
        keys("y")
        signal_r, signal_w = os.pipe()
        try:
            os.write(signal_w, b"\x00")
            # Both are ready; stdin wins, because a keystroke is the more
            # urgent of the two and the pipe stays readable until drained.
            assert read_key_with_timeout_or_signal(0.05, extra_fds=[signal_r]) == "y"
            assert read_key_with_timeout_or_signal(0.05, extra_fds=[signal_r]) is None
        finally:
            os.close(signal_r)
            os.close(signal_w)

    def test_a_key_is_read_when_only_stdin_is_ready(self, keys, tty_pair):
        signal_r, signal_w = os.pipe()
        try:
            keys("n")
            assert read_key_with_timeout_or_signal(0.05, extra_fds=[signal_r]) == "n"
        finally:
            os.close(signal_r)
            os.close(signal_w)

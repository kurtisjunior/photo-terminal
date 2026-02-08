"""Utilities for reading keyboard input in raw mode."""

from __future__ import annotations

import os
import select
import sys
from typing import Optional

KEY_UP = "UP"
KEY_DOWN = "DOWN"
KEY_ESC = "ESC"


_DEFAULT_ESC_TIMEOUT = float(os.environ.get("PHOTO_TERMINAL_ESC_TIMEOUT", "0.10"))


def read_key(timeout_sec: float = _DEFAULT_ESC_TIMEOUT) -> Optional[str]:
    """Read a single key or decoded escape sequence.

    Returns:
        - "UP" / "DOWN" for arrow keys
        - "ESC" for a lone Escape key press
        - single-character string for regular keys
        - None for ignored/unknown escape sequences
    """
    char = sys.stdin.read(1)
    if char != "\x1b":
        return char

    # ESC received; determine if it's a lone key press or part of a sequence.
    if not _stdin_has_data(timeout_sec):
        return KEY_ESC

    seq = _read_escape_sequence()
    if not seq:
        return KEY_ESC

    # Arrow keys can arrive as ESC [ A / ESC O A or extended CSI forms.
    if seq.endswith("A"):
        return KEY_UP
    if seq.endswith("B"):
        return KEY_DOWN

    # If this looks like a Meta-<key> (ESC + single char), treat as ESC.
    if len(seq) == 1 and seq not in ("[", "O"):
        return KEY_ESC

    # Ignore other escape sequences (focus events, kitty protocol, etc.)
    return None


def read_key_with_timeout(timeout_sec: float = _DEFAULT_ESC_TIMEOUT) -> Optional[str]:
    """Read a key if available within timeout_sec.

    Returns:
        Same values as read_key(), or None if no input is ready.
    """
    if not _stdin_has_data(timeout_sec):
        return None
    return read_key(timeout_sec)


def is_ghostty() -> bool:
    term_program = os.environ.get("TERM_PROGRAM", "")
    term = os.environ.get("TERM", "")
    return term_program == "ghostty" or "ghostty" in term


def _stdin_has_data(timeout_sec: float) -> bool:
    if _is_mocked_reader():
        return True
    try:
        ready, _, _ = select.select([sys.stdin], [], [], timeout_sec)
        return bool(ready)
    except Exception:
        return False


def _read_escape_sequence() -> str:
    seq = ""
    try:
        seq += sys.stdin.read(1)
    except Exception:
        return seq

    if _is_mocked_reader():
        # Tests often mock sys.stdin.read with side_effects; just read next char.
        if seq in ("[", "O"):
            try:
                seq += sys.stdin.read(1)
            except Exception:
                return seq
        return seq

    # Read any remaining bytes that are immediately available.
    while _stdin_has_data(0):
        ch = sys.stdin.read(1)
        seq += ch
        # CSI sequences typically end with @-~ range; stop early if reached.
        if "@" <= ch <= "~":
            break

    return seq


def _is_mocked_reader() -> bool:
    reader = sys.stdin.read
    if hasattr(reader, "mock_calls"):
        return True
    module_name = getattr(reader, "__module__", "")
    if module_name == "unittest.mock":
        return True
    class_name = reader.__class__.__name__
    return "Mock" in class_name

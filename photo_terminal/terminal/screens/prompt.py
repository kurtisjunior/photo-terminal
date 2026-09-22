"""Line-mode questions asked on the main screen.

Not every question deserves a full-screen UI. The reorder hand-off is one
yes/no, asked between two screens that each own the alternate buffer, so it
stays on the main buffer with no session and no raw mode - which is also why it
belongs here rather than inside either screen.

It lives in ``terminal`` because it reads stdin and writes stdout, and the
pipeline calls it through a one-method dependency, so a test answers the
question without touching either.
"""

from __future__ import annotations

__all__ = ["ask_yes_no"]

_YES = {"y", "yes"}
_NO = {"n", "no"}


def ask_yes_no(question: str, default: bool = False) -> bool:
    """Ask ``question`` on the main screen and return the answer.

    Args:
        question: The prompt, including its trailing space.
        default: What an empty line, an unrecognised answer, or EOF means.

    Returns:
        The user's answer, or ``default``.
    """
    try:
        response = input(question).strip().lower()
    except EOFError:
        return default

    if response in _YES:
        return True
    if response in _NO:
        return False
    return default

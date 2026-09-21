"""Which graphics protocol the terminal can actually be driven with.

Two values, not four. The previous four-value string set routed ``iterm`` and
``sixel`` down the same subprocess path as Kitty, which means neither ever
produced a correct frame - they failed exactly the way Ghostty did, for the same
reason. Both now get the in-process half-block preview, which is a strict
improvement on what they had. A two-value enum that is honest about what is
implemented beats a four-value one where half the values are aspirational.

Adding a real iTerm2 or Sixel emitter later is a third member plus a third
:class:`~photo_terminal.terminal.preview.frames.PreviewFrame`, which is a small
change now that the seam exists.
"""

from __future__ import annotations

import os
from enum import Enum


class GraphicsProtocol(Enum):
    """How previews reach the screen."""

    KITTY = "kitty"
    """Native Kitty graphics placements. Kitty, Ghostty, WezTerm."""

    HALF_BLOCK = "half_block"
    """Unicode half-blocks with 24-bit colour. Everything else, including
    terminal multiplexers."""


def detect_graphics_protocol(
    environ: os._Environ[str] | dict[str, str] | None = None,
) -> GraphicsProtocol:
    """Classify the terminal from its environment.

    Detection order:

    1. ``TMUX`` or ``STY`` set - a multiplexer sits between us and the terminal
       and will not pass graphics placements through, so half-blocks.
    2. Ghostty (``TERM_PROGRAM=ghostty`` or ``ghostty`` in ``TERM``), Kitty
       (``kitty`` in ``TERM``) or WezTerm (``TERM_PROGRAM=WezTerm``) - Kitty
       protocol.
    3. Anything else - half-blocks.

    This is a heuristic over environment variables, not a live capability query.
    A query would mean writing an escape sequence and reading the reply off the
    same stdin the input loop polls in raw mode, which is the failure mode this
    whole change exists to remove.
    """
    env = os.environ if environ is None else environ

    if env.get("TMUX") or env.get("STY"):
        return GraphicsProtocol.HALF_BLOCK

    term_program = env.get("TERM_PROGRAM", "")
    term = env.get("TERM", "")

    if term_program == "ghostty" or "ghostty" in term:
        return GraphicsProtocol.KITTY
    if "kitty" in term:
        return GraphicsProtocol.KITTY
    if term_program == "WezTerm":
        return GraphicsProtocol.KITTY

    return GraphicsProtocol.HALF_BLOCK

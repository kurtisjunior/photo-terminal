"""The right-hand pane: one preview at a time, cleanly replaced.

Both two-pane screens need exactly the same four things - ask the service for a
frame, show a placeholder until it lands, erase the outgoing frame before
painting the incoming one, and know when nothing changed so the frame can be
skipped. Written twice, that is where "the previous image's leftovers stay on
screen" comes from: the erase is easy to forget, and a graphics placement
survives every kind of text erasure.

Written once, the screens cannot forget it.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from photo_terminal.terminal.frame import Frame
from photo_terminal.terminal.geometry import Point, Rect, Size
from photo_terminal.terminal.preview.frames import MessageFrame, PreviewFrame
from photo_terminal.terminal.preview.service import PreviewService

LOADING_MESSAGE = "[Loading preview...]"
TOO_SMALL_MESSAGE = "[Window too small for a preview]"

#: Which neighbours to warm after each render, in the order a user is most
#: likely to need them.
PRELOAD_OFFSETS = (1, -1, 2, -2)

#: How many images to warm before the first paint of a screen.
STARTUP_PRELOAD = 5


class PreviewPane:
    """Owns what is currently drawn in the preview box, and the service behind it."""

    def __init__(self, service: PreviewService) -> None:
        self._service = service
        self.painted: PreviewFrame | None = None
        self.painted_at: Point | None = None
        self.token: tuple[object, ...] | None = None
        # What the notice currently says, so it is written when it changes
        # rather than on every frame.
        self._notice = ""

    # -- the input loop's half ------------------------------------------- #

    @property
    def wait_fd(self) -> int:
        """Fold this into the input loop's ``select`` set."""
        return self._service.wait_fd

    @property
    def dirty(self) -> bool:
        """Whether a background render has landed since the last :meth:`drain`."""
        return self._service.dirty

    def drain(self) -> None:
        self._service.drain()

    def close(self) -> None:
        self._service.close()

    # -- painting --------------------------------------------------------- #

    def paint(self, frame: Frame, box: Rect, path: Path) -> None:
        """Show ``path`` in ``box``, replacing whatever is there.

        Writes nothing when the preview has not changed, which is what keeps
        arrowing through a folder from re-transmitting an image the terminal
        already holds.
        """
        if box.is_empty:
            self.erase(frame)
            return

        incoming, token = self._incoming(path, box.size)
        if token == self.token:
            return

        self.erase(frame)
        frame.write(incoming.paint(box.origin))
        self.painted = incoming
        self.painted_at = box.origin
        self.token = token

    def erase(self, frame: Frame) -> None:
        """Remove what is on screen. The only thing that can remove a placement."""
        if self.painted is None or self.painted_at is None:
            return
        frame.write(self.painted.erase(self.painted_at))
        self.painted = None
        self.painted_at = None
        self.token = None

    def paint_notice(self, frame: Frame, at: Rect, suppressed: bool) -> None:
        """Say why there is no preview, in ``at`` - normally the footer row.

        A window too narrow for two panes gives all of its columns to the file
        list, so the explanation cannot live in the preview column: there is
        no preview column. Written only when it changes, so a screen with a
        preview touches no cells here at all.
        """
        if at.is_empty:
            return
        message = TOO_SMALL_MESSAGE if suppressed else ""
        if message == self._notice:
            return
        self._notice = message
        text = f" {message}".ljust(at.width)[: at.width]
        frame.place(at.origin, f"\033[2m{text}\033[0m")

    def take_pending_writes(self) -> bytes:
        """Bytes the cache owes the terminal, to ride along in the next frame."""
        return self._service.take_pending_writes()

    # -- warming ---------------------------------------------------------- #

    def preload(self, box: Rect, items: Sequence[Path], cursor: int) -> None:
        """Warm the neighbours of ``cursor`` in the background."""
        if box.is_empty:
            return
        for offset in PRELOAD_OFFSETS:
            target = cursor + offset
            if 0 <= target < len(items):
                self._service.request(items[target], box.size)

    def warm(self, box: Rect, items: Sequence[Path], count: int) -> None:
        """Warm the first ``count`` items, before the first paint."""
        if box.is_empty:
            return
        for path in items[:count]:
            self._service.request(path, box.size)

    # -- internals -------------------------------------------------------- #

    def _incoming(self, path: Path, box: Size) -> tuple[PreviewFrame, tuple[object, ...]]:
        """The frame to show for ``path``, and a token identifying it.

        The token is what the change detector compares. It has to distinguish a
        placeholder from the real image for the same path and box, because that
        transition is exactly when a repaint is required.
        """
        frame = self._service.frame_for(path, box)
        if frame is None:
            return MessageFrame(LOADING_MESSAGE, box.w), (path, box, "loading")
        return frame, (path, box, "ready")

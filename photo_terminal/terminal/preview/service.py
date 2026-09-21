"""Off-loop preview rendering: a worker pool, an LRU cache, and a wakeup pipe.

The asynchronous machinery here is the best-designed piece of the code this
replaces, and its behaviour is preserved verbatim: previews render on a bounded
thread pool, and a self-pipe folded into the input loop's ``select`` set wakes
the loop in microseconds rather than waiting out the 50ms poll. Only ownership
changed - six fields duplicated across two screen classes became one object with
one ``wait_fd``.

Two things are genuinely new:

* The cache key is a frozen record, so the stored value's type follows from the
  key's ``protocol`` field instead of from parsing a string prefix.
* The cache has a bound. It previously grew for the lifetime of the screen, one
  entry per (path, mode, width, height) tuple. Eviction of a Kitty frame also
  frees the terminal's copy of the pixels, which is what keeps the terminal's
  memory tracking ours.
"""

from __future__ import annotations

import functools
import logging
import os
import threading
from collections import OrderedDict
from collections.abc import Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from photo_terminal.terminal.capabilities import GraphicsProtocol
from photo_terminal.terminal.geometry import CellMetrics, Size, fit
from photo_terminal.terminal.preview import kitty
from photo_terminal.terminal.preview.frames import (
    HalfBlockFrame,
    KittyFrame,
    MessageFrame,
    PreviewFrame,
)
from photo_terminal.terminal.preview.halfblock import render_image_to_ansi_from_pil

logger = logging.getLogger(__name__)

DEFAULT_WORKERS = 4
DEFAULT_CACHE_ENTRIES = 12
"""Enough for the cursor plus several screens of preloaded neighbours, bounded
so a long folder cannot grow the cache without limit."""


@dataclass(frozen=True)
class PreviewKey:
    """What a cached preview is a preview *of*.

    ``cells`` is the preview **box**, not the fitted image: the fitted size is a
    function of the box and the source, so the box is what decides a hit. A
    resize therefore misses and re-renders rather than painting stale content.
    """

    path: Path
    protocol: GraphicsProtocol
    cells: Size


class PreviewService:
    """Renders previews off the input loop and caches the frames."""

    def __init__(
        self,
        protocol: GraphicsProtocol,
        cell: CellMetrics,
        *,
        max_entries: int = DEFAULT_CACHE_ENTRIES,
        workers: int = DEFAULT_WORKERS,
    ) -> None:
        self._protocol = protocol
        self._cell = cell
        self._max_entries = max(1, max_entries)
        self._executor = ThreadPoolExecutor(max_workers=workers)
        self._futures: dict[PreviewKey, Future[PreviewFrame]] = {}
        self._cache: OrderedDict[PreviewKey, PreviewFrame] = OrderedDict()
        self._lock = threading.Lock()
        self._dirty = False
        self._pending = bytearray()
        self._ids: Iterator[int] = kitty.image_ids()
        self._notify_r, self._notify_w = os.pipe()
        os.set_blocking(self._notify_r, False)
        self._closed = False

    # -- the input loop's half ------------------------------------------- #

    @property
    def wait_fd(self) -> int:
        """Fold this into the input loop's ``select`` set to be woken by a render."""
        return self._notify_r

    @property
    def dirty(self) -> bool:
        """Whether a render has landed since the last :meth:`drain`."""
        return self._dirty

    def drain(self) -> None:
        """Consume the wakeup and clear the dirty flag."""
        try:
            os.read(self._notify_r, 1024)
        except OSError:
            pass
        self._dirty = False

    # -- the render path's half ------------------------------------------ #

    def frame_for(self, path: Path, box: Size) -> PreviewFrame | None:
        """The cached frame for ``path`` in a ``box``-sized box.

        Returns ``None`` when the render has been scheduled but has not landed
        yet, which is the screen's cue to paint a placeholder.
        """
        key = PreviewKey(path=path, protocol=self._protocol, cells=box)
        with self._lock:
            frame = self._cache.get(key)
            if frame is not None:
                self._cache.move_to_end(key)
                return frame
        self._schedule(key)
        return None

    def request(self, path: Path, box: Size) -> None:
        """Warm the cache for ``path`` without needing the result now."""
        key = PreviewKey(path=path, protocol=self._protocol, cells=box)
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return
        self._schedule(key)

    def take_pending_writes(self) -> bytes:
        """Bytes the service needs written to the terminal, and clears them.

        Today this is only the uppercase deletion an LRU eviction owes the
        terminal. The screen folds it into its next frame, so the service still
        writes nothing itself.
        """
        with self._lock:
            payload = bytes(self._pending)
            self._pending.clear()
        return payload

    def close(self) -> None:
        """Shut the pool down and close the pipe. Idempotent."""
        if self._closed:
            return
        self._closed = True
        try:
            self._executor.shutdown(wait=False, cancel_futures=True)
        except Exception:  # pragma: no cover - shutdown is best-effort
            logger.debug("preview executor shutdown failed", exc_info=True)
        for fd in (self._notify_r, self._notify_w):
            try:
                os.close(fd)
            except OSError:
                pass

    # -- internals -------------------------------------------------------- #

    def _schedule(self, key: PreviewKey) -> None:
        if self._closed:
            return
        with self._lock:
            if key in self._futures or key in self._cache:
                return
            future = self._executor.submit(self._render, key)
            self._futures[key] = future
        future.add_done_callback(functools.partial(self._store, key))

    def _render(self, key: PreviewKey) -> PreviewFrame:
        """Worker-thread body. Opens the image, fits it, builds the frame."""
        with Image.open(key.path) as image:
            image.load()
            source = Size(image.width, image.height)
            placement = fit(source, key.cells, self._cell_for(key.protocol))
            if placement.is_empty:
                return MessageFrame("[Preview: no room]", key.cells.w)

            if key.protocol is GraphicsProtocol.KITTY:
                png = kitty.encode_png(image, placement.px)
                return KittyFrame(png=png, cells=placement.cells, image_id=next(self._ids))

            lines = render_image_to_ansi_from_pil(image, placement.cells.w, placement.cells.h)

        if len(lines) != placement.cells.h:
            # The half-block renderer reports failure as a single bracketed
            # line rather than raising. Anything that is not one line per row is
            # that, and a message is the honest frame for it.
            return MessageFrame(lines[0] if lines else "[Preview error]", key.cells.w)
        return HalfBlockFrame(lines=lines, cells=placement.cells)

    def _cell_for(self, protocol: GraphicsProtocol) -> CellMetrics:
        """Which cell metrics to fit against.

        The Kitty path resizes real pixels into real cells, so it wants the
        measured cell. The half-block path stacks exactly two pixels per row, so
        its cell *is* 1:2 by construction regardless of the font - fitting it
        against a measured 9x19 cell would skew the aspect ratio rather than
        correct it.
        """
        if protocol is GraphicsProtocol.KITTY:
            return self._cell
        return CellMetrics.assumed()

    def _store(self, key: PreviewKey, future: Future[PreviewFrame]) -> None:
        """Completion callback. Caches the frame and wakes the input loop."""
        try:
            frame: PreviewFrame = future.result()
        except Exception as error:
            logger.debug("preview render failed for %s", key.path, exc_info=True)
            frame = MessageFrame(f"[Preview error: {error}]", key.cells.w)

        with self._lock:
            self._futures.pop(key, None)
            self._cache[key] = frame
            self._cache.move_to_end(key)
            while len(self._cache) > self._max_entries:
                _, evicted = self._cache.popitem(last=False)
                self._pending.extend(self._eviction_bytes(evicted))
            self._dirty = True
            try:
                os.write(self._notify_w, b"\x00")
            except OSError:
                pass

    @staticmethod
    def _eviction_bytes(frame: PreviewFrame) -> bytes:
        """What the terminal is owed when we drop ``frame`` from the cache."""
        if isinstance(frame, KittyFrame) and frame.resident:
            return frame.evict()
        return b""

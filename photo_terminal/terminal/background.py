"""A worker pool and a self-pipe that can wake a ``select``-based input loop.

This is the one piece of asynchronous machinery in the package. It was the
best-designed part of the code this replaces - work runs on a bounded pool and a
self-pipe folded into the input loop's ``select`` set wakes the loop in
microseconds rather than waiting out the 50ms poll - but it was written twice,
once in the select screen and once in the reorder screen, and a third screen
that needed it (the S3 browser) made its blocking call straight from the
keystroke loop instead.

Now there is one copy. ``PreviewService`` owns one for rendering previews and
the S3 browser owns one for listings; both hand ``wait_fd`` to the same reader.
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from typing import TypeVar

logger = logging.getLogger(__name__)

DEFAULT_WORKERS = 4

T = TypeVar("T")


class BackgroundWorker:
    """Runs callables off the input loop and wakes it when they land.

    The contract is deliberately small: submit work, be told (through
    :attr:`wait_fd` and :attr:`dirty`) that something finished, and drain. What
    the result *means* is the caller's business - this class never touches the
    terminal and holds no state beyond the pipe and the pool.
    """

    def __init__(self, workers: int = DEFAULT_WORKERS) -> None:
        self._executor = ThreadPoolExecutor(max_workers=workers)
        self._lock = threading.Lock()
        self._dirty = False
        self._closed = False
        self._notify_r, self._notify_w = os.pipe()
        os.set_blocking(self._notify_r, False)

    # -- the input loop's half ------------------------------------------- #

    @property
    def wait_fd(self) -> int:
        """Fold this into the input loop's ``select`` set."""
        return self._notify_r

    @property
    def dirty(self) -> bool:
        """Whether a job has landed since the last :meth:`drain`."""
        return self._dirty

    @property
    def closed(self) -> bool:
        return self._closed

    def drain(self) -> None:
        """Consume the wakeup and clear the dirty flag."""
        with self._lock:
            try:
                os.read(self._notify_r, 1024)
            except OSError:
                pass
            self._dirty = False

    # -- the worker's half ------------------------------------------------ #

    def submit(self, work: Callable[[], T]) -> Future[T] | None:
        """Run ``work`` on the pool. Returns ``None`` once closed.

        Completion callbacks are the caller's to attach, and are attached
        *after* any lock the caller holds has been released: a callback added to
        an already-finished future runs inline on the calling thread, which
        would deadlock against a lock the callback also wants.
        """
        if self._closed:
            return None
        return self._executor.submit(work)

    def notify(self) -> None:
        """Mark a result available and poke the pipe. Safe from any thread."""
        with self._lock:
            self._dirty = True
            try:
                os.write(self._notify_w, b"\x00")
            except OSError:
                pass

    def close(self) -> None:
        """Shut the pool down and close the pipe. Idempotent."""
        if self._closed:
            return
        self._closed = True
        try:
            self._executor.shutdown(wait=False, cancel_futures=True)
        except Exception:  # pragma: no cover - shutdown is best-effort
            logger.debug("background executor shutdown failed", exc_info=True)
        for fd in (self._notify_r, self._notify_w):
            try:
                os.close(fd)
            except OSError:
                pass

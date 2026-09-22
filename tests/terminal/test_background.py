"""The worker pool and the wakeup pipe, which used to be written twice.

The pipe is the piece worth testing directly: it is what lets a screen sit in
one ``select`` over both the keyboard and its own background work, and be woken
in microseconds rather than waiting out the 50ms poll.
"""

from __future__ import annotations

import os
import select
import threading

from photo_terminal.terminal.background import BackgroundWorker


def wait_readable(fd: int, timeout: float = 5.0) -> bool:
    readable, _, _ = select.select([fd], [], [], timeout)
    return bool(readable)


class TestSubmitting:
    def test_work_runs_and_returns_its_value(self):
        worker = BackgroundWorker(workers=1)
        assert worker.submit(lambda: 6 * 7).result(5) == 42
        worker.close()

    def test_a_failure_is_carried_on_the_future(self):
        worker = BackgroundWorker(workers=1)
        future = worker.submit(lambda: 1 / 0)
        assert isinstance(future.exception(5), ZeroDivisionError)
        worker.close()

    def test_a_closed_worker_accepts_nothing_more(self):
        worker = BackgroundWorker(workers=1)
        worker.close()
        assert worker.submit(lambda: 1) is None


class TestWakeup:
    def test_notify_makes_the_wait_fd_readable(self):
        """This is what folds into the input loop's select set."""
        worker = BackgroundWorker(workers=1)
        assert not wait_readable(worker.wait_fd, 0)

        worker.notify()

        assert wait_readable(worker.wait_fd, 1)
        assert worker.dirty is True
        worker.close()

    def test_draining_clears_the_pipe_and_the_flag(self):
        worker = BackgroundWorker(workers=1)
        worker.notify()
        worker.drain()

        assert worker.dirty is False
        assert not wait_readable(worker.wait_fd, 0)
        worker.close()

    def test_a_completed_job_can_wake_a_waiting_loop(self):
        worker = BackgroundWorker(workers=1)
        gate = threading.Event()

        future = worker.submit(lambda: gate.wait(5) and "done")
        future.add_done_callback(lambda _: worker.notify())

        assert not wait_readable(worker.wait_fd, 0)
        gate.set()
        assert wait_readable(worker.wait_fd, 5)
        worker.close()

    def test_many_notifications_drain_in_one_read(self):
        worker = BackgroundWorker(workers=1)
        for _ in range(50):
            worker.notify()

        worker.drain()

        assert not wait_readable(worker.wait_fd, 0)
        worker.close()


class TestClosing:
    def test_closing_releases_both_descriptors(self):
        worker = BackgroundWorker(workers=1)
        read_fd = worker.wait_fd

        worker.close()

        assert worker.closed is True
        try:
            os.fstat(read_fd)
        except OSError:
            return  # closed, as expected
        raise AssertionError("the read end of the pipe was left open")

    def test_closing_twice_is_harmless(self):
        worker = BackgroundWorker(workers=1)
        worker.close()
        worker.close()
        assert worker.closed is True

    def test_notify_after_close_does_not_raise(self):
        """A job can land after the screen has gone; it must not take it down."""
        worker = BackgroundWorker(workers=1)
        worker.close()
        worker.notify()

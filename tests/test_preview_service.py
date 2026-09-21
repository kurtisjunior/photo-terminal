"""The preview service: cache behaviour, eviction, and the wakeup pipe.

None of this was asserted before. The executor, the futures dict, the dirty flag
and the self-pipe all ran during the suite - against zero-byte fixtures, inside
worker threads, with every failure swallowed by a bare ``except``.
"""

from __future__ import annotations

import os
import select
import shutil
import time
from pathlib import Path

import pytest

from photo_terminal.terminal.capabilities import GraphicsProtocol
from photo_terminal.terminal.geometry import Point, Size
from photo_terminal.terminal.preview.frames import HalfBlockFrame, KittyFrame, MessageFrame
from photo_terminal.terminal.preview.service import PreviewKey, PreviewService

from .conftest import MEASURED_CELL, FakeTerminal

BOX = Size(60, 30)


@pytest.fixture
def kitty_service():
    service = PreviewService(GraphicsProtocol.KITTY, MEASURED_CELL)
    yield service
    service.close()


@pytest.fixture
def half_block_service():
    service = PreviewService(GraphicsProtocol.HALF_BLOCK, MEASURED_CELL)
    yield service
    service.close()


def settled(service: PreviewService, path: Path, box: Size = BOX, timeout: float = 5.0):
    """Block until the background render for ``path`` has landed."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        frame = service.frame_for(path, box)
        if frame is not None:
            return frame
        time.sleep(0.005)
    raise AssertionError(f"no preview landed for {path} within {timeout}s")


class TestCache:
    def test_a_miss_returns_none_and_schedules(self, kitty_service, portrait_3x4):
        assert kitty_service.frame_for(portrait_3x4, BOX) is None
        assert settled(kitty_service, portrait_3x4) is not None

    def test_a_hit_returns_the_same_frame_object(self, kitty_service, portrait_3x4):
        """Identity matters: the frame remembers whether the terminal still
        holds its pixels, which is what makes a return visit one short
        re-placement instead of a re-transmission."""
        frame = settled(kitty_service, portrait_3x4)
        assert kitty_service.frame_for(portrait_3x4, BOX) is frame

    def test_a_different_box_is_a_different_entry(self, kitty_service, portrait_3x4):
        """A resize must miss and re-render rather than paint stale content."""
        first = settled(kitty_service, portrait_3x4, BOX)
        assert kitty_service.frame_for(portrait_3x4, Size(40, 20)) is None
        second = settled(kitty_service, portrait_3x4, Size(40, 20))

        assert second is not first
        assert second.cells != first.cells

    def test_request_warms_the_cache_without_returning_anything(self, kitty_service, portrait_3x4):
        assert kitty_service.request(portrait_3x4, BOX) is None
        settled(kitty_service, portrait_3x4)

    def test_repeated_requests_do_not_pile_up_futures(self, kitty_service, portrait_3x4):
        for _ in range(20):
            kitty_service.request(portrait_3x4, BOX)
        settled(kitty_service, portrait_3x4)

        assert kitty_service._futures == {}


class TestEviction:
    def test_eviction_frees_the_pixels_the_terminal_is_holding(self, portrait_3x4, tmp_path):
        """The old cache had no bound at all and grew for the lifetime of the
        screen. Dropping an entry now owes the terminal an uppercase deletion."""
        service = PreviewService(GraphicsProtocol.KITTY, MEASURED_CELL, max_entries=1)
        try:
            first = settled(service, portrait_3x4)
            first.paint(Point(60, 1))  # transmits, so the pixels are now resident
            assert service.take_pending_writes() == b""

            second = tmp_path / "second.jpg"
            shutil.copyfile(portrait_3x4, second)
            settled(service, second)

            terminal = FakeTerminal()
            terminal.write(service.take_pending_writes())
            assert terminal.kitty_commands() == [
                {"a": "d", "d": "I", "i": str(first.image_id), "q": "2"}
            ]
        finally:
            service.close()

    def test_evicting_a_frame_the_terminal_never_saw_owes_nothing(self, portrait_3x4, tmp_path):
        service = PreviewService(GraphicsProtocol.KITTY, MEASURED_CELL, max_entries=1)
        try:
            settled(service, portrait_3x4)  # never painted, so never transmitted
            second = tmp_path / "second.jpg"
            shutil.copyfile(portrait_3x4, second)
            settled(service, second)

            assert service.take_pending_writes() == b""
        finally:
            service.close()

    def test_taking_pending_writes_clears_them(self, portrait_3x4, tmp_path):
        service = PreviewService(GraphicsProtocol.KITTY, MEASURED_CELL, max_entries=1)
        try:
            settled(service, portrait_3x4).paint(Point(60, 1))
            second = tmp_path / "second.jpg"
            shutil.copyfile(portrait_3x4, second)
            settled(service, second)

            assert service.take_pending_writes() != b""
            assert service.take_pending_writes() == b""
        finally:
            service.close()

    def test_the_most_recently_used_entry_is_never_the_one_evicted(
        self, portrait_3x4, landscape_4x3
    ):
        service = PreviewService(GraphicsProtocol.KITTY, MEASURED_CELL, max_entries=2)
        try:
            first = settled(service, portrait_3x4)
            settled(service, landscape_4x3)
            assert service.frame_for(portrait_3x4, BOX) is first
        finally:
            service.close()


class TestWakeup:
    def test_a_completed_render_makes_the_wait_fd_readable(self, kitty_service, portrait_3x4):
        """This is what wakes the input loop in microseconds instead of making
        it wait out the 50ms poll."""
        kitty_service.request(portrait_3x4, BOX)
        readable, _, _ = select.select([kitty_service.wait_fd], [], [], 5.0)

        assert readable == [kitty_service.wait_fd]
        assert kitty_service.dirty is True

    def test_draining_clears_the_flag_and_the_pipe(self, kitty_service, portrait_3x4):
        settled(kitty_service, portrait_3x4)
        kitty_service.drain()

        assert kitty_service.dirty is False
        assert select.select([kitty_service.wait_fd], [], [], 0)[0] == []

    def test_draining_an_empty_pipe_is_harmless(self, kitty_service):
        kitty_service.drain()
        assert kitty_service.dirty is False


class TestFrameSelection:
    def test_the_kitty_protocol_produces_a_placement(self, kitty_service, portrait_3x4):
        frame = settled(kitty_service, portrait_3x4)

        assert isinstance(frame, KittyFrame)
        assert frame.png.startswith(b"\x89PNG")
        assert frame.cells.w <= BOX.w and frame.cells.h <= BOX.h

    def test_the_half_block_protocol_produces_lines(self, half_block_service, portrait_3x4):
        frame = settled(half_block_service, portrait_3x4)

        assert isinstance(frame, HalfBlockFrame)
        assert len(frame.lines) == frame.cells.h

    def test_the_two_protocols_agree_on_the_footprint(
        self, kitty_service, half_block_service, portrait_3x4
    ):
        """Both fit against a 1:2 cell for this fixture, so the same photograph
        occupies the same rectangle whichever way it is drawn."""
        assert settled(kitty_service, portrait_3x4).cells == (
            settled(half_block_service, portrait_3x4).cells
        )

    def test_a_tiny_source_is_not_upscaled(self, kitty_service, tiny_40x30):
        frame = settled(kitty_service, tiny_40x30)

        assert frame.cells.w <= 40 // MEASURED_CELL.px.w
        assert frame.cells.h <= 30 // MEASURED_CELL.px.h + 1


class TestFailure:
    def test_a_missing_file_becomes_a_message_frame(self, kitty_service, tmp_path):
        frame = settled(kitty_service, tmp_path / "absent.jpg")

        assert isinstance(frame, MessageFrame)
        assert "error" in frame.text.lower()

    def test_a_corrupt_file_becomes_a_message_frame(self, half_block_service, tmp_path):
        path = tmp_path / "broken.jpg"
        path.write_bytes(b"not an image")

        assert isinstance(settled(half_block_service, path), MessageFrame)

    def test_a_message_frame_fits_the_box(self, kitty_service, tmp_path):
        """A failure must not become the thing that paints outside the box."""
        frame = settled(kitty_service, tmp_path / "absent.jpg", Size(24, 10))

        assert frame.cells.w <= 24
        assert frame.cells.h <= 10


class TestLifecycle:
    def test_close_is_idempotent(self, portrait_3x4):
        service = PreviewService(GraphicsProtocol.KITTY, MEASURED_CELL)
        service.request(portrait_3x4, BOX)
        service.close()
        service.close()

    def test_scheduling_after_close_is_a_no_op(self, portrait_3x4):
        service = PreviewService(GraphicsProtocol.KITTY, MEASURED_CELL)
        service.close()

        assert service.frame_for(portrait_3x4, BOX) is None

    def test_close_releases_the_pipe(self, portrait_3x4):
        service = PreviewService(GraphicsProtocol.KITTY, MEASURED_CELL)
        fd = service.wait_fd
        service.close()

        with pytest.raises(OSError):
            os.fstat(fd)


class TestPreviewKey:
    def test_the_key_is_hashable_and_carries_the_protocol(self, portrait_3x4):
        """The protocol is a typed field, so the stored value's type follows
        from the key instead of from parsing a string prefix."""
        key = PreviewKey(path=portrait_3x4, protocol=GraphicsProtocol.KITTY, cells=BOX)
        other = PreviewKey(path=portrait_3x4, protocol=GraphicsProtocol.HALF_BLOCK, cells=BOX)

        assert key != other
        assert len({key, other}) == 2
        assert key == PreviewKey(
            path=portrait_3x4, protocol=GraphicsProtocol.KITTY, cells=Size(60, 30)
        )

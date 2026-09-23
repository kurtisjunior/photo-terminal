"""Tests for the progress port and its console implementation.

The console reporter is the only thing in the app that still knows a step is
drawn as a spinner, so this is where the escape sequences are asserted.
"""

import io

import pytest

from photo_terminal.app.reporter import SPINNER_FRAMES, ConsoleProgressReporter
from photo_terminal.domain.progress import NullReporter, ProgressReporter, reporter_or_null
from tests.conftest import RecordingReporter

CLEAR_LINE = "\033[2K\r"


@pytest.fixture
def stream() -> io.StringIO:
    return io.StringIO()


@pytest.fixture
def console(stream: io.StringIO) -> ConsoleProgressReporter:
    return ConsoleProgressReporter(stream)


# --------------------------------------------------------------------------- #
# The port
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "implementation",
    [NullReporter(), ConsoleProgressReporter(io.StringIO()), RecordingReporter()],
)
def test_every_implementation_satisfies_the_port(implementation):
    assert isinstance(implementation, ProgressReporter)


def test_a_missing_reporter_becomes_a_null_one():
    assert isinstance(reporter_or_null(None), NullReporter)


def test_a_supplied_reporter_is_passed_through():
    supplied = RecordingReporter()

    assert reporter_or_null(supplied) is supplied


def test_the_null_reporter_accepts_everything_and_does_nothing():
    reporter = NullReporter()

    assert reporter.step(1, 2, "a.jpg") is None
    assert reporter.done("finished") is None
    assert reporter.info("hello") is None
    assert reporter.warn("careful") is None


# --------------------------------------------------------------------------- #
# The console implementation
# --------------------------------------------------------------------------- #


def test_a_step_draws_a_spinner_a_count_and_a_label(console, stream):
    console.step(1, 10, "photo.jpg")

    assert stream.getvalue() == f"{CLEAR_LINE}{SPINNER_FRAMES[0]} 1/10 photo.jpg"


def test_a_step_never_ends_the_line(console, stream):
    """The next step has to be able to overwrite it."""
    console.step(3, 10, "photo.jpg")

    assert "\n" not in stream.getvalue()


def test_the_spinner_advances_with_the_count(console, stream):
    for current in range(1, 4):
        console.step(current, 5, "x.jpg")

    drawn = [frame for frame in SPINNER_FRAMES[:3]]
    assert all(frame in stream.getvalue() for frame in drawn)
    assert stream.getvalue().endswith("3/5 x.jpg")


def test_the_spinner_wraps_past_its_last_frame(console, stream):
    console.step(len(SPINNER_FRAMES) + 1, 100, "x.jpg")

    assert SPINNER_FRAMES[0] in stream.getvalue()


def test_done_erases_the_progress_line(console, stream):
    console.step(1, 10, "photo.jpg")
    stream.truncate(0)
    stream.seek(0)

    console.done()

    assert stream.getvalue() == CLEAR_LINE


def test_done_with_a_label_leaves_a_line_behind(console, stream):
    console.step(1, 10, "photo.jpg")
    stream.truncate(0)
    stream.seek(0)

    console.done("Processed 10 images")

    assert stream.getvalue() == f"{CLEAR_LINE}Processed 10 images\n"


def test_done_without_a_run_in_progress_erases_nothing(console, stream):
    console.done()

    assert stream.getvalue() == ""


def test_done_is_idempotent(console, stream):
    console.step(1, 10, "photo.jpg")
    console.done()
    stream.truncate(0)
    stream.seek(0)

    console.done()

    assert stream.getvalue() == ""


def test_a_message_erases_a_live_spinner_before_writing(console, stream):
    """An error must never be printed beside half a spinner."""
    console.step(4, 10, "photo.jpg")
    stream.truncate(0)
    stream.seek(0)

    console.warn("Error: the upload failed")

    assert stream.getvalue() == f"{CLEAR_LINE}Error: the upload failed\n"


def test_info_and_warn_both_end_their_line(console, stream):
    console.info("first")
    console.warn("second")

    assert stream.getvalue() == "first\nsecond\n"


def test_a_message_with_no_spinner_up_writes_nothing_extra(console, stream):
    console.info("hello")

    assert stream.getvalue() == "hello\n"


def test_the_stream_defaults_to_stdout_at_write_time(capsys):
    """Resolved per write, so replacing sys.stdout still works."""
    reporter = ConsoleProgressReporter()

    reporter.info("to stdout")

    assert capsys.readouterr().out == "to stdout\n"

"""The S3 browser screen, driven against a fake port.

``run()`` was never exercised at all before this: the screen built its own
boto3 client from inside its own keystroke loop, so there was nothing to stand
in for. It now takes a ``FolderLister``, which is one method - and a test can
make that one method slow, or make it fail, and watch what the screen does.
"""

from __future__ import annotations

import io
import threading

import pytest
from rich.console import Console

from photo_terminal.terminal.screens.s3_browse import (
    GO_UP,
    SELECT_CURRENT,
    S3FolderBrowser,
)

TREE = {
    "": ["italy", "japan"],
    "japan/": ["kyoto", "tokyo"],
    "japan/tokyo/": [],
    "italy/": ["trapani"],
}

ENTER = "\r"
DOWN = ["\x1b", "[", "B"]
UP = ["\x1b", "[", "A"]


class FakeLister:
    """A folder tree in a dict, plus a record of what was asked for."""

    def __init__(self, tree: dict[str, list[str]] | None = None) -> None:
        self.tree = TREE if tree is None else tree
        self.calls: list[str] = []
        self.gate: threading.Event | None = None
        self.gate_for: str | None = None
        """Which prefix the gate holds. ``None`` holds every listing."""

    def list_folders(self, prefix: str) -> list[str]:
        self.calls.append(prefix)
        if self.gate is not None and self.gate_for in (None, prefix):
            self.gate.wait(5)
        return sorted(self.tree.get(prefix, []))


class BrokenLister:
    """A port that fails the way a bad profile or a dead network does."""

    def __init__(self, error: Exception) -> None:
        self.error = error

    def list_folders(self, prefix: str) -> list[str]:
        raise self.error


@pytest.fixture
def lister() -> FakeLister:
    return FakeLister()


@pytest.fixture
def browser(lister: FakeLister) -> S3FolderBrowser:
    """A browser wired to the fake tree, with Rich drawing into a buffer."""
    screen = S3FolderBrowser(lister, console=Console(file=io.StringIO(), width=80))
    screen.load_folders()
    return screen


class TestMenu:
    def test_the_root_menu_has_no_way_up(self, browser):
        items = browser.get_menu_items()
        assert items[0] == SELECT_CURRENT
        assert GO_UP not in items
        assert items[1:] == ["italy", "japan"]

    def test_a_subfolder_menu_offers_a_way_up(self, browser):
        browser.current_prefix = "japan/"
        browser.folders = ["kyoto", "tokyo"]
        assert browser.get_menu_items() == [SELECT_CURRENT, GO_UP, "kyoto", "tokyo"]

    @pytest.mark.parametrize(
        ("prefix", "expected"),
        [
            ("", "Root"),
            ("japan/", "Root / japan"),
            ("italy/trapani/", "Root / italy / trapani"),
        ],
    )
    def test_the_breadcrumb_shows_where_we_are(self, browser, prefix, expected):
        browser.current_prefix = prefix
        assert browser.get_breadcrumb() == expected

    def test_the_panel_renders_without_touching_the_real_terminal(self, browser):
        panel = browser.create_panel()
        assert "S3 Browser: Root" in str(panel.title)


class TestNavigation:
    def test_moving_down_is_bounded_by_the_menu(self, browser):
        for _ in range(10):
            browser.move_down()
        assert browser.current_index == len(browser.get_menu_items()) - 1

    def test_moving_up_is_bounded_at_the_top(self, browser):
        browser.current_index = 1
        browser.move_up()
        browser.move_up()
        assert browser.current_index == 0

    def test_selecting_the_current_folder_returns_its_prefix(self, browser):
        browser.current_prefix = "japan/tokyo/"
        browser.current_index = 0
        assert browser.handle_selection() == "japan/tokyo/"

    def test_drilling_in_lists_the_new_prefix(self, browser, lister):
        browser.current_index = 2  # "japan"
        assert browser.handle_selection() is None
        assert browser.current_prefix == "japan/"

        browser.settle(timeout=5)
        assert browser.folders == ["kyoto", "tokyo"]
        assert lister.calls == ["", "japan/"]

    def test_going_up_lists_the_parent(self, browser):
        browser.current_prefix = "japan/tokyo/"
        browser.current_index = 1  # ".."
        assert browser.handle_selection() is None
        assert browser.current_prefix == "japan/"

        browser.settle(timeout=5)
        assert browser.folders == ["kyoto", "tokyo"]

    def test_going_up_from_one_level_reaches_the_root(self, browser):
        browser.current_prefix = "japan/"
        browser.current_index = 1  # ".."
        browser.handle_selection()
        assert browser.current_prefix == ""

    def test_a_new_listing_resets_the_cursor_to_the_top(self, browser):
        browser.current_index = 2  # "japan"
        browser.handle_selection()
        browser.settle(timeout=5)
        assert browser.current_index == 0


class TestOffTheKeystrokeLoop:
    """The listing used to be a blocking boto3 call inside raw mode."""

    def test_a_slow_listing_does_not_block_the_selection(self, lister):
        lister.gate = threading.Event()
        browser = S3FolderBrowser(lister, console=Console(file=io.StringIO(), width=80))
        browser.folders = ["japan"]
        browser.current_index = 1  # "japan"

        browser.handle_selection()

        # The call has been handed to the worker and has not come back.
        assert browser.loading is True
        assert browser.folders == []

        lister.gate.set()
        browser.settle(timeout=5)
        assert browser.loading is False
        assert browser.folders == ["kyoto", "tokyo"]
        browser._worker.close()

    def test_the_panel_says_it_is_loading(self, lister):
        lister.gate = threading.Event()
        browser = S3FolderBrowser(lister, console=Console(file=io.StringIO(), width=80))
        browser.start_listing()

        console = Console(file=io.StringIO(), width=80)
        console.print(browser.create_panel())
        assert "Loading" in console.file.getvalue()

        lister.gate.set()
        browser.settle(timeout=5)
        browser._worker.close()

    def test_a_stale_listing_is_discarded(self, browser):
        """The user moved on before the answer arrived; it is not painted."""
        browser.start_listing()
        browser.settle(timeout=5)
        browser._landed = ("somewhere/else/", ["ghost"])
        browser.apply_listing()
        assert "ghost" not in browser.folders


class TestFailures:
    def test_a_failing_listing_surfaces_on_the_main_thread(self):
        error = RuntimeError("AWS profile 'nope' not found")
        browser = S3FolderBrowser(BrokenLister(error), console=Console(file=io.StringIO()))

        with pytest.raises(RuntimeError, match="nope"):
            browser.load_folders()
        browser._worker.close()


class TestRun:
    def test_drilling_in_then_selecting_returns_the_prefix(self, lister, scripted_keys):
        browser = S3FolderBrowser(lister, console=Console(file=io.StringIO(), width=80))
        # down to "japan", Enter to drill in, Enter on "[Select current folder]"
        scripted_keys([*DOWN, *DOWN, ENTER, ENTER])

        assert browser.run() == "japan/"
        assert lister.calls[0] == ""  # the root listing, before the screen opened

    def test_the_loop_keeps_reading_while_a_listing_is_in_flight(self, lister, scripted_keys):
        """The second Enter is handled before the drill-in listing lands."""
        # The root listing goes through; the drill-in listing is held open.
        lister.gate = threading.Event()
        lister.gate_for = "japan/"
        browser = S3FolderBrowser(lister, console=Console(file=io.StringIO(), width=80))
        scripted_keys([*DOWN, *DOWN, ENTER, ENTER])

        assert browser.run() == "japan/"
        lister.gate.set()

    def test_q_cancels(self, lister, scripted_keys):
        browser = S3FolderBrowser(lister, console=Console(file=io.StringIO(), width=80))
        scripted_keys(["q"])

        with pytest.raises(SystemExit) as exit_info:
            browser.run()
        assert exit_info.value.code == 1

    def test_a_bare_escape_cancels(self, lister, scripted_keys):
        """It used to block until the user pressed another key."""
        browser = S3FolderBrowser(lister, console=Console(file=io.StringIO(), width=80))
        scripted_keys(["\x1b", "z"])

        with pytest.raises(SystemExit):
            browser.run()

    def test_ctrl_c_propagates(self, lister, scripted_keys):
        browser = S3FolderBrowser(lister, console=Console(file=io.StringIO(), width=80))
        scripted_keys(["\x03"])

        with pytest.raises(KeyboardInterrupt):
            browser.run()

    def test_navigating_up_and_down_before_choosing(self, lister, scripted_keys):
        browser = S3FolderBrowser(lister, console=Console(file=io.StringIO(), width=80))
        scripted_keys([*DOWN, *DOWN, *UP, *UP, ENTER])

        assert browser.run() == ""  # back at "[Select current folder]" for the root

    def test_the_worker_is_closed_when_the_screen_leaves(self, lister, scripted_keys):
        browser = S3FolderBrowser(lister, console=Console(file=io.StringIO(), width=80))
        scripted_keys(["q"])

        with pytest.raises(SystemExit):
            browser.run()
        assert browser._worker.closed is True

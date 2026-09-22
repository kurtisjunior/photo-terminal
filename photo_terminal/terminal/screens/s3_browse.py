"""Choose the upload destination by walking the bucket's prefixes.

The screen knows nothing about S3. It is handed a :class:`FolderLister` - a
port with a single method - and asks it what is under a prefix. That is what
keeps the terminal package free of the AWS SDK, and it is what makes the screen
testable: the tests drive ``run()`` against a fake lister, which was impossible
while the browser built its own client.

Listings also come off the keystroke loop. ``handle_selection`` used to make a
blocking bucket-listing call from inside raw mode, so a slow network froze the
UI with no feedback at all. Now the listing runs on the shared worker, the loop
keeps reading keys, and the wakeup pipe brings the result back.
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import Future
from typing import Protocol

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from photo_terminal.terminal.background import BackgroundWorker
from photo_terminal.terminal.input import KEY_DOWN, KEY_ESC, KEY_UP, read_key_with_timeout_or_signal
from photo_terminal.terminal.layout import FOOTER_HEIGHT, sample_terminal_size
from photo_terminal.terminal.screens.widgets import ListView
from photo_terminal.terminal.session import TerminalSession

logger = logging.getLogger(__name__)

SELECT_CURRENT = "[Select current folder]"
GO_UP = ".."

#: Rows the panel spends on its border, breadcrumb and controls, so the folder
#: list is windowed into what is left rather than running off the bottom.
PANEL_CHROME = 8


class FolderLister(Protocol):
    """What the browser needs from storage, and nothing more."""

    def list_folders(self, prefix: str) -> list[str]:
        """The folder names directly under ``prefix``, sorted."""
        ...


class S3FolderBrowser:
    """Interactive S3 folder browser with hierarchy navigation."""

    def __init__(self, lister: FolderLister, console: Console | None = None):
        """Initialize the browser.

        Args:
            lister: The port that answers "what is under this prefix?".
            console: Where Rich draws. Defaults to a fresh console.
        """
        self._lister = lister
        self.console = console if console is not None else Console()
        self.current_prefix = ""  # e.g. "japan/tokyo/"
        self.folders: list[str] = []
        self.loading = False

        self._view: ListView[str] = ListView(self.get_menu_items())
        self._worker = BackgroundWorker(workers=1)
        self._listing: Future[list[str]] | None = None
        self._landed: tuple[str, list[str] | BaseException] | None = None
        self._landed_lock = threading.Lock()

        # Kept as attributes for callers that name them.
        self.SELECT_CURRENT = SELECT_CURRENT
        self.GO_UP = GO_UP

    # -- state ------------------------------------------------------------ #

    @property
    def current_index(self) -> int:
        """Which menu item is highlighted."""
        return self._view.cursor

    @current_index.setter
    def current_index(self, index: int) -> None:
        self._view.sync(self.get_menu_items(), index)

    def get_breadcrumb(self) -> str:
        """Breadcrumb path for the current location, e.g. ``Root / japan``."""
        if not self.current_prefix:
            return "Root"
        return "Root / " + " / ".join(self.current_prefix.rstrip("/").split("/"))

    def get_menu_items(self) -> list[str]:
        """The menu at this level: the special entries, then the folders."""
        items = [SELECT_CURRENT]
        if self.current_prefix:
            items.append(GO_UP)
        items.extend(self.folders)
        return items

    def move_up(self) -> None:
        """Move selection cursor up."""
        self._view.sync(self.get_menu_items())
        self._view.move_up()

    def move_down(self) -> None:
        """Move selection cursor down."""
        self._view.sync(self.get_menu_items())
        self._view.move_down()

    def handle_selection(self) -> str | None:
        """Act on Enter.

        Returns:
            The chosen prefix if the user picked the current folder, ``None``
            to keep browsing. Drilling in or going up starts a listing in the
            background; :meth:`apply_listing` or :meth:`settle` finishes it.
        """
        self._view.sync(self.get_menu_items())
        if self._view.is_empty:
            return None
        selected = self._view.current

        if selected == SELECT_CURRENT:
            return self.current_prefix

        if selected == GO_UP:
            parts = self.current_prefix.rstrip("/").split("/")
            self.current_prefix = "/".join(parts[:-1]) + "/" if len(parts) > 1 else ""
            self.start_listing()
            return None

        self.current_prefix = self.current_prefix + selected + "/"
        self.start_listing()
        return None

    # -- listings --------------------------------------------------------- #

    def start_listing(self) -> None:
        """Ask for the folders under the current prefix, off the input loop.

        The previous level's folders are dropped straight away. Leaving them on
        screen would mean the menu showed one prefix's contents under another
        prefix's breadcrumb, and Enter would act on whichever stale row the
        cursor happened to be over.
        """
        self.loading = True
        self.folders = []
        self._view.sync(self.get_menu_items(), cursor=0)
        prefix = self.current_prefix
        future = self._worker.submit(lambda: self._lister.list_folders(prefix))
        if future is None:  # the worker is closed; nothing more will land
            self.loading = False
            return
        self._listing = future
        future.add_done_callback(lambda done: self._store(prefix, done))

    def settle(self, timeout: float | None = None) -> None:
        """Block until the in-flight listing lands, then apply it.

        Used for the very first listing, where there is no interface to keep
        responsive yet and a failure should surface before the screen opens.
        """
        listing = self._listing
        if listing is not None:
            try:
                listing.result(timeout)
            except Exception:  # the error is re-raised by apply_listing
                pass
        self._worker.drain()
        self.apply_listing()

    def apply_listing(self) -> None:
        """Adopt whatever the worker finished, or re-raise what it caught."""
        with self._landed_lock:
            landed, self._landed = self._landed, None
        if landed is None:
            return
        prefix, result = landed
        if prefix != self.current_prefix:
            return  # the user moved on; this listing is stale
        self.loading = False
        if isinstance(result, BaseException):
            raise result
        self.folders = result
        self._view.sync(self.get_menu_items(), cursor=0)

    def load_folders(self) -> None:
        """List the current prefix and wait for the answer."""
        self.start_listing()
        self.settle()

    def _store(self, prefix: str, future: Future[list[str]]) -> None:
        """Completion callback, on the worker thread."""
        try:
            landed: tuple[str, list[str] | BaseException] = (prefix, future.result())
        except Exception as error:  # re-raised on the main thread by apply_listing
            landed = (prefix, error)
        with self._landed_lock:
            self._landed = landed
        self._worker.notify()

    # -- rendering -------------------------------------------------------- #

    def create_panel(self) -> Panel:
        """The browser panel: breadcrumb, the visible folders, and the controls."""
        self._view.sync(self.get_menu_items())
        height = max(1, sample_terminal_size().lines - FOOTER_HEIGHT - PANEL_CHROME)
        start, stop = self._view.window(height)

        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("item", overflow="fold")

        for index, item in self._view.rows(height):
            if item == SELECT_CURRENT:
                display = f"✓ {item}"
            elif item == GO_UP:
                display = f"↑ {item}"
            else:
                display = f"  {item}/"

            if index == self._view.cursor:
                table.add_row(Text(f"► {display}", style="bold cyan"))
            else:
                table.add_row(Text(f"  {display}"))

        controls = Text()
        if stop - start < len(self._view):
            controls.append(f"\n{start + 1}-{stop} of {len(self._view)}\n", style="dim")
        else:
            controls.append("\n")
        controls.append("─" * 40 + "\n", style="dim")
        if self.loading:
            controls.append("Loading…\n", style="cyan")
        controls.append("↑/↓: Navigate  Enter: Select/Drill down\n", style="dim")
        controls.append("q/Esc: Cancel", style="dim")

        return Panel(
            Group(table, controls),
            title=f"S3 Browser: {self.get_breadcrumb()}",
            border_style="blue",
        )

    # -- the input loop --------------------------------------------------- #

    def run(self) -> str:
        """Run the interactive browser.

        Returns:
            Selected S3 prefix (e.g., "japan/tokyo/" or "" for root)

        Raises:
            SystemExit: If the user cancels.
            KeyboardInterrupt: If the user presses Ctrl-C.
        """
        # The first listing is synchronous: there is no interface to keep
        # responsive yet, and a credentials failure should surface before the
        # screen opens rather than from inside it.
        self.load_folders()

        try:
            with TerminalSession():
                return self._loop()
        finally:
            self._worker.close()

    def _loop(self) -> str:
        with Live(self.create_panel(), console=self.console, refresh_per_second=4) as live:
            while True:
                key = read_key_with_timeout_or_signal(0.05, extra_fds=[self._worker.wait_fd])

                if key is None:
                    if self._worker.dirty:
                        self._worker.drain()
                        self.apply_listing()
                        live.update(self.create_panel())
                    continue

                if key == KEY_UP:
                    self.move_up()
                elif key == KEY_DOWN:
                    self.move_down()
                elif key == KEY_ESC:
                    raise SystemExit(1)
                elif key in ("\r", "\n"):  # Enter
                    result = self.handle_selection()
                    if result is not None:
                        return result
                elif key in ("q", "Q"):
                    raise SystemExit(1)
                elif key == "\x03":  # Ctrl+C
                    raise KeyboardInterrupt

                live.update(self.create_panel())

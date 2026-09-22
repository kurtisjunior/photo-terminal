"""The list widget: bounded navigation, and the scroll window no screen had.

A folder with more images than the window is tall used to paint every row,
straight past the bottom edge of the terminal. These are the cases that go
wrong when a scroll window is written by hand, which is why it is written once.
"""

from __future__ import annotations

import pytest

from photo_terminal.terminal.screens.widgets import (
    ListView,
    ellipsise,
    pad_line,
    rule,
    visible_len,
    widest_that_fits,
)

LETTERS = [chr(ord("a") + i) for i in range(26)]


class TestNavigation:
    def test_the_cursor_starts_at_the_top(self):
        assert ListView(LETTERS).cursor == 0

    def test_moving_is_bounded_at_the_top(self):
        view = ListView(LETTERS)
        assert view.move(-1) is False
        assert view.cursor == 0

    def test_moving_is_bounded_at_the_bottom(self):
        view = ListView(LETTERS, cursor=25)
        assert view.move(1) is False
        assert view.cursor == 25

    def test_moving_does_not_wrap(self):
        """Every screen behaves this way today, and keeps behaving this way."""
        view = ListView(LETTERS, cursor=25)
        view.move_down()
        assert view.cursor == 25
        view.cursor = 0
        view.move_up()
        assert view.cursor == 0

    def test_a_large_delta_clamps_rather_than_overshooting(self):
        view = ListView(LETTERS)
        assert view.move(100) is True
        assert view.cursor == 25

    def test_an_empty_list_has_no_current_item(self):
        view: ListView[str] = ListView([])
        assert view.is_empty
        assert view.move(1) is False
        with pytest.raises(IndexError):
            _ = view.current

    def test_an_out_of_range_initial_cursor_is_clamped(self):
        assert ListView(LETTERS, cursor=99).cursor == 25
        assert ListView(LETTERS, cursor=-4).cursor == 0

    def test_sync_keeps_the_cursor_in_range_when_the_list_shrinks(self):
        view = ListView(LETTERS, cursor=25)
        view.sync(LETTERS[:3])
        assert view.cursor == 2
        assert view.current == "c"


class TestScrollWindow:
    def test_a_list_shorter_than_the_window_is_shown_whole(self):
        view = ListView(LETTERS[:4])
        assert view.window(10) == (0, 4)
        assert list(view.visible(10)) == ["a", "b", "c", "d"]

    def test_a_list_exactly_the_window_height_is_shown_whole(self):
        view = ListView(LETTERS[:10], cursor=9)
        assert view.window(10) == (0, 10)
        assert view.has_above(10) is False
        assert view.has_below(10) is False

    def test_a_list_longer_than_the_window_starts_at_the_top(self):
        view = ListView(LETTERS)
        assert view.window(10) == (0, 10)
        assert view.has_below(10) is True

    def test_the_window_follows_the_cursor_down_with_a_margin(self):
        view = ListView(LETTERS, margin=2)
        for _ in range(8):
            view.move_down()
        # cursor 8, window height 10: two rows must remain below it
        assert view.window(10) == (1, 11)

    def test_the_window_follows_the_cursor_up_with_a_margin(self):
        view = ListView(LETTERS, margin=2, cursor=20)
        view.window(10)  # settle the window at the bottom
        view.cursor = 14
        assert view.window(10) == (12, 22)

    def test_the_window_does_not_move_while_the_cursor_is_comfortably_inside(self):
        view = ListView(LETTERS, margin=2)
        assert view.window(10) == (0, 10)
        view.cursor = 5
        assert view.window(10) == (0, 10)

    def test_the_window_stops_at_the_end_of_the_list(self):
        view = ListView(LETTERS, cursor=25)
        assert view.window(10) == (16, 26)
        assert view.has_below(10) is False

    @pytest.mark.parametrize("cursor", range(26))
    @pytest.mark.parametrize("height", [1, 2, 3, 5, 10, 26, 40])
    def test_the_cursor_is_always_inside_the_window(self, cursor, height):
        """The property the whole widget exists for."""
        view = ListView(LETTERS, cursor=cursor)
        start, stop = view.window(height)
        assert start <= cursor < stop
        assert 0 <= start <= stop <= 26
        assert stop - start == min(height, 26)

    @pytest.mark.parametrize("height", [0, -5])
    def test_a_window_with_no_height_shows_nothing(self, height):
        view = ListView(LETTERS)
        assert view.window(height) == (0, 0)
        assert view.rows(height) == []

    def test_a_short_window_still_tracks_the_cursor(self):
        """The margin cannot be honoured in two rows, so it shrinks."""
        view = ListView(LETTERS, margin=2, cursor=0)
        assert view.window(2) == (0, 2)
        view.cursor = 20
        assert view.window(2) == (19, 21)

    def test_rows_carry_the_index_in_the_full_list(self):
        view = ListView(LETTERS, cursor=25)
        rows = view.rows(3)
        assert rows == [(23, "x"), (24, "y"), (25, "z")]

    def test_an_empty_list_has_an_empty_window(self):
        view: ListView[str] = ListView([])
        assert view.window(10) == (0, 0)
        assert view.has_above(10) is False
        assert view.has_below(10) is False


class TestTextHelpers:
    def test_visible_len_ignores_colour(self):
        assert visible_len("\033[1;36mabc\033[0m") == 3

    def test_pad_line_pads_to_the_width(self):
        assert pad_line("ab", 5) == "ab   "

    def test_pad_line_clips_a_line_that_is_too_long(self):
        """A hint row longer than a narrow pane used to paint into the gutter."""
        assert pad_line("abcdef", 3) == "abc"

    def test_pad_line_clips_without_cutting_an_escape_in_half(self):
        clipped = pad_line("\033[1;36mabcdef\033[0m", 3)
        assert visible_len(clipped) == 3
        assert clipped.endswith("\033[0m")
        assert "\033[1;36m" in clipped

    def test_pad_line_measures_in_cells_not_bytes(self):
        assert visible_len(pad_line("\033[2mab\033[0m", 6)) == 6

    def test_ellipsise_leaves_a_short_string_alone(self):
        assert ellipsise("photo.jpg", 20) == "photo.jpg"

    def test_ellipsise_marks_what_it_cut(self):
        assert ellipsise("a-very-long-filename.jpg", 10) == "a-very-..."

    @pytest.mark.parametrize("width", [0, -1, 1, 2, 3])
    def test_ellipsise_degrades_rather_than_producing_a_longer_string(self, width):
        assert len(ellipsise("abcdefgh", width)) == max(0, width)

    def test_rule_centres_its_label(self):
        assert rule(" hi ", 10) == "─── hi ───"

    def test_rule_with_no_label_is_all_line(self):
        assert rule("", 5) == "─────"

    def test_rule_truncates_a_label_that_does_not_fit(self):
        assert visible_len(rule(" a very long label ", 6)) == 6

    def test_widest_that_fits_prefers_the_fullest_text(self):
        assert widest_that_fits(["long text", "short"], 20) == "long text"

    def test_widest_that_fits_falls_back_to_the_shortest(self):
        assert widest_that_fits(["long text", "short"], 6) == "short"
        assert widest_that_fits(["long text", "short"], 2) == "short"

    def test_widest_that_fits_handles_no_variants(self):
        assert widest_that_fits([], 10) == ""

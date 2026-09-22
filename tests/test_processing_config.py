"""Tests for the processing configuration screen.

These used to mock ``sys.stdin`` by hand in every test, because this screen was
one of the two that bypassed the shared reader and parsed escape sequences
itself. It now goes through ``terminal.input`` like every other screen, so it
is driven by the shared ``scripted_keys`` fixture - which also means an arrow
key can finally be scripted here the way a terminal actually sends one.
"""

from pathlib import Path

from photo_terminal.tui import show_processing_config

LOCKED = [Path("/tmp/img1.jpg"), Path("/tmp/img2.jpg")]
DOWN_ARROW = ["\x1b", "[", "B"]
UP_ARROW = ["\x1b", "[", "A"]


class TestShowProcessingConfig:
    """Test suite for show_processing_config function."""

    def test_returns_dict_structure(self):
        """Test that function signature and dict structure are correct."""
        assert callable(show_processing_config)

        # Verify docstring exists
        assert show_processing_config.__doc__ is not None
        assert "locked_images" in show_processing_config.__doc__
        assert "config" in show_processing_config.__doc__

    def test_confirm_returns_valid_dict(self, scripted_keys):
        """Test that confirming returns a properly structured dict."""
        scripted_keys(["y"])

        result = show_processing_config(LOCKED, {"target_size_kb": 500})

        assert isinstance(result, dict)
        assert result["resize"] is True
        assert result["preserve_exif"] is True
        assert result["target_size_kb"] == 500
        assert result["output_format"] == "JPEG"

    def test_cancel_returns_none(self, scripted_keys):
        """Test that pressing 'q' returns None."""
        scripted_keys(["q"])

        assert show_processing_config(LOCKED, {"target_size_kb": 400}) is None

    def test_back_returns_none(self, scripted_keys):
        """Test that pressing 'b' (back) returns None."""
        scripted_keys(["b"])

        assert show_processing_config(LOCKED, {"target_size_kb": 400}) is None

    def test_a_bare_escape_cancels(self, scripted_keys):
        """A lone ESC used to block here until the user pressed another key."""
        scripted_keys(["\x1b", "z"])

        assert show_processing_config(LOCKED, {"target_size_kb": 400}) is None

    def test_uses_config_target_size(self, scripted_keys):
        """Test that target_size_kb from config is used correctly."""
        scripted_keys(["y"])

        result = show_processing_config(LOCKED, {"target_size_kb": 600})

        assert result["target_size_kb"] == 600

    def test_toggle_options(self, scripted_keys):
        """Test that spacebar toggles options correctly."""
        scripted_keys([" ", "y"])

        result = show_processing_config(LOCKED, {"target_size_kb": 400})

        # Resize (the first option) toggled off; the rest untouched.
        assert result["resize"] is False
        assert result["preserve_exif"] is True

    def test_arrow_keys_move_between_options(self, scripted_keys):
        """Down, down, space: the output format cycles, not a checkbox."""
        scripted_keys([*DOWN_ARROW, *DOWN_ARROW, " ", "y"])

        result = show_processing_config(LOCKED, {"target_size_kb": 400})

        assert result["output_format"] == "PNG"
        assert result["resize"] is True
        assert result["preserve_exif"] is True

    def test_navigation_is_bounded_at_the_top(self, scripted_keys):
        """Up from the first option stays on the first option."""
        scripted_keys([*UP_ARROW, " ", "y"])

        result = show_processing_config(LOCKED, {"target_size_kb": 400})

        assert result["resize"] is False

    def test_navigation_is_bounded_at_the_bottom(self, scripted_keys):
        """Down past the last option stays on the last option."""
        scripted_keys([*DOWN_ARROW, *DOWN_ARROW, *DOWN_ARROW, " ", "y"])

        result = show_processing_config(LOCKED, {"target_size_kb": 400})

        assert result["output_format"] == "PNG"

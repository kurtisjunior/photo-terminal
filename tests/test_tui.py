"""Tests for TUI module."""

import os
from unittest.mock import MagicMock, patch

import pytest

from photo_terminal.terminal.capabilities import GraphicsProtocol, detect_graphics_protocol
from photo_terminal.tui import ImageSelector, select_images


class TestImageSelector:
    """Tests for ImageSelector class."""

    def test_init(self, sample_images):
        """Test ImageSelector initialization."""
        selector = ImageSelector(sample_images)

        assert selector.images == sample_images
        assert selector.selected_indices == set()
        assert selector.current_index == 0

    def test_toggle_selection(self, sample_images):
        """Test toggling selection."""
        selector = ImageSelector(sample_images)

        # Select image at index 0
        selector.toggle_selection()
        assert 0 in selector.selected_indices

        # Deselect image at index 0
        selector.toggle_selection()
        assert 0 not in selector.selected_indices

    def test_move_up(self, sample_images):
        """Test moving cursor up."""
        selector = ImageSelector(sample_images)
        selector.current_index = 2

        selector.move_up()
        assert selector.current_index == 1

        selector.move_up()
        assert selector.current_index == 0

        # Should not go below 0
        selector.move_up()
        assert selector.current_index == 0

    def test_move_down(self, sample_images):
        """Test moving cursor down."""
        selector = ImageSelector(sample_images)

        selector.move_down()
        assert selector.current_index == 1

        selector.move_down()
        assert selector.current_index == 2

        # Should not go beyond last image
        selector.move_down()
        assert selector.current_index == 2

    def test_get_selected_images(self, sample_images):
        """Test getting selected images."""
        selector = ImageSelector(sample_images)

        # Select images at indices 0 and 2
        selector.selected_indices.add(2)
        selector.selected_indices.add(0)

        selected = selector.get_selected_images()

        # Should return in sorted order
        assert selected == [sample_images[0], sample_images[2]]

    def test_get_selected_images_none_selected(self, sample_images):
        """Test getting selected images when none selected."""
        selector = ImageSelector(sample_images)

        selected = selector.get_selected_images()

        assert selected == []


class TestSelectImages:
    """Tests for select_images function."""

    def test_select_images_no_images(self):
        """Test select_images with no images."""
        with pytest.raises(SystemExit) as exc_info:
            select_images([])

        assert exc_info.value.code == 1

    @patch("photo_terminal.tui.ImageSelector")
    def test_select_images_user_cancels(self, mock_selector_class, sample_images):
        """Test select_images when user cancels."""
        # Mock selector to return None (cancelled)
        mock_selector = MagicMock()
        mock_selector.run.return_value = None
        mock_selector_class.return_value = mock_selector

        with pytest.raises(SystemExit) as exc_info:
            select_images(sample_images)

        assert exc_info.value.code == 1

    @patch("photo_terminal.tui.ImageSelector")
    def test_select_images_success(self, mock_selector_class, sample_images):
        """Test successful image selection."""
        # Mock selector to return selected images
        mock_selector = MagicMock()
        selected_images = [sample_images[0], sample_images[2]]
        mock_selector.run.return_value = selected_images
        mock_selector_class.return_value = mock_selector

        result = select_images(sample_images)

        assert result == selected_images

    @patch("photo_terminal.tui.ImageSelector")
    def test_select_images_keyboard_interrupt(self, mock_selector_class, sample_images):
        """Test select_images when user presses Ctrl+C."""
        # Mock selector to raise KeyboardInterrupt
        mock_selector = MagicMock()
        mock_selector.run.side_effect = KeyboardInterrupt()
        mock_selector_class.return_value = mock_selector

        with pytest.raises(SystemExit) as exc_info:
            select_images(sample_images)

        assert exc_info.value.code == 1


class TestNavigationLogic:
    """Tests for navigation and selection logic."""

    def test_multiple_selections(self, sample_images):
        """Test selecting multiple images."""
        selector = ImageSelector(sample_images)

        # Select first image
        selector.toggle_selection()
        assert 0 in selector.selected_indices

        # Move to second and select
        selector.move_down()
        selector.toggle_selection()
        assert 1 in selector.selected_indices

        # Should have both selected
        assert len(selector.selected_indices) == 2

    def test_selection_persistence_during_navigation(self, sample_images):
        """Test that selections persist when navigating."""
        selector = ImageSelector(sample_images)

        # Select first image
        selector.toggle_selection()

        # Navigate away and back
        selector.move_down()
        selector.move_down()
        selector.move_up()
        selector.move_up()

        # Selection should still be there
        assert 0 in selector.selected_indices

    def test_boundary_navigation(self, sample_images):
        """Test navigation at boundaries."""
        selector = ImageSelector(sample_images)

        # Try to go up from top
        selector.move_up()
        assert selector.current_index == 0

        # Move to bottom
        selector.current_index = len(sample_images) - 1

        # Try to go down from bottom
        selector.move_down()
        assert selector.current_index == len(sample_images) - 1


class TestKeyboardSelection:
    """Tests for keyboard selection shortcuts."""

    def test_y_key_selects_current_and_proceeds(self, sample_images):
        """Test that pressing 'y' toggles selection of current image (multi-stage workflow)."""
        selector = ImageSelector(sample_images)
        selector.current_index = 1  # Navigate to second image

        # Pre-select some other images
        selector.selected_indices = {0, 2}

        # Mock stdin: 'y' to toggle, Enter to lock, 'n' to proceed
        with patch("sys.stdin.read", side_effect=["y", "\r", "n"]):
            with patch.object(selector, "render"):
                with patch.object(selector._preview, "request"):
                    with patch("sys.stdin.fileno", return_value=0):
                        with patch("termios.tcgetattr", return_value=[]):
                            with patch("termios.tcsetattr"):
                                with patch("tty.setraw"):
                                    result = selector.run()

        # Verify all three images are selected (0, 2 were already selected, 1 was toggled on)
        assert len(result) == 3
        assert selector.selected_indices == {0, 1, 2}

    def test_y_clears_other_selections(self, sample_images):
        """Test that pressing 'y' toggles selection (deselects if already selected)."""
        selector = ImageSelector(sample_images)
        selector.current_index = 2  # Navigate to third image

        # Select all images first
        selector.selected_indices = {0, 1, 2}

        # Press 'y' to toggle off index 2, then Enter to lock, 'n' to proceed
        with patch("sys.stdin.read", side_effect=["y", "\r", "n"]):
            with patch.object(selector, "render"):
                with patch.object(selector._preview, "request"):
                    with patch("sys.stdin.fileno", return_value=0):
                        with patch("termios.tcgetattr", return_value=[]):
                            with patch("termios.tcsetattr"):
                                with patch("tty.setraw"):
                                    result = selector.run()

        # Verify img3 (index 2) was toggled off, leaving 0 and 1
        assert len(result) == 2
        assert selector.selected_indices == {0, 1}

    def test_a_key_selects_all(self, sample_images):
        """Test that pressing 'a' with none selected selects all images."""
        selector = ImageSelector(sample_images)

        # Initially no selections
        assert len(selector.selected_indices) == 0

        # Press 'a' to select all, Enter to lock, 'n' to proceed
        with patch("sys.stdin.read", side_effect=["a", "\r", "n"]):
            with patch.object(selector, "render"):
                with patch.object(selector._preview, "request"):
                    with patch("sys.stdin.fileno", return_value=0):
                        with patch("termios.tcgetattr", return_value=[]):
                            with patch("termios.tcsetattr"):
                                with patch("tty.setraw"):
                                    result = selector.run()

        # Verify all images are selected
        assert len(result) == len(sample_images)
        assert set(result) == set(sample_images)
        assert selector.selected_indices == {0, 1, 2}

    def test_a_key_deselects_all(self, sample_images):
        """Test that pressing 'a' with all selected deselects all images."""
        selector = ImageSelector(sample_images)

        # Select all images first
        selector.selected_indices = {0, 1, 2}

        # Press 'a' (should deselect all), then 'q' to quit
        with patch("sys.stdin.read", side_effect=["a", "q"]):
            with patch.object(selector, "render"):
                with patch.object(selector._preview, "request"):
                    with patch("sys.stdin.fileno", return_value=0):
                        with patch("termios.tcgetattr", return_value=[]):
                            with patch("termios.tcsetattr"):
                                with patch("tty.setraw"):
                                    result = selector.run()

        # Verify all selections are cleared
        assert result is None  # quit returns None
        assert len(selector.selected_indices) == 0

    def test_a_key_with_partial_selection(self, sample_images):
        """Test that pressing 'a' with partial selection selects all."""
        selector = ImageSelector(sample_images)

        # Select only first image
        selector.selected_indices = {0}

        # Press 'a' to select all, Enter to lock, 'n' to proceed
        with patch("sys.stdin.read", side_effect=["a", "\r", "n"]):
            with patch.object(selector, "render"):
                with patch.object(selector._preview, "request"):
                    with patch("sys.stdin.fileno", return_value=0):
                        with patch("termios.tcgetattr", return_value=[]):
                            with patch("termios.tcsetattr"):
                                with patch("tty.setraw"):
                                    result = selector.run()

        # Verify all images are now selected
        assert len(result) == len(sample_images)
        assert selector.selected_indices == {0, 1, 2}

    def test_a_does_not_auto_confirm(self, sample_images):
        """Test that pressing 'a' doesn't automatically return (needs Enter)."""
        selector = ImageSelector(sample_images)

        # Press 'a' then 'q' (not Enter)
        with patch("sys.stdin.read", side_effect=["a", "q"]):
            with patch.object(selector, "render"):
                with patch.object(selector._preview, "request"):
                    with patch("sys.stdin.fileno", return_value=0):
                        with patch("termios.tcgetattr", return_value=[]):
                            with patch("termios.tcsetattr"):
                                with patch("tty.setraw"):
                                    result = selector.run()

        # Should return None (quit) not the selected images
        assert result is None

    def test_spacebar_still_works(self, sample_images):
        """Test that spacebar toggles selection as expected."""
        selector = ImageSelector(sample_images)
        selector.current_index = 1

        # Press spacebar twice (toggles on then off), then spacebar once more, then Enter to lock, 'n' to proceed
        # Net result: selected once
        with patch("sys.stdin.read", side_effect=[" ", " ", " ", "\r", "n"]):
            with patch.object(selector, "render"):
                with patch.object(selector._preview, "request"):
                    with patch("sys.stdin.fileno", return_value=0):
                        with patch("termios.tcgetattr", return_value=[]):
                            with patch("termios.tcsetattr"):
                                with patch("tty.setraw"):
                                    result = selector.run()

        # Spacebar three times: on, off, on = selected
        assert result == [sample_images[1]]

    def test_spacebar_toggles_selection(self, sample_images):
        """Test that spacebar properly toggles selection on and off."""
        selector = ImageSelector(sample_images)
        selector.current_index = 0

        # Initially not selected
        assert 0 not in selector.selected_indices

        # Toggle on with spacebar, Enter to lock, 'n' to proceed
        with patch("sys.stdin.read", side_effect=[" ", "\r", "n"]):
            with patch.object(selector, "render"):
                with patch.object(selector._preview, "request"):
                    with patch("sys.stdin.fileno", return_value=0):
                        with patch("termios.tcgetattr", return_value=[]):
                            with patch("termios.tcsetattr"):
                                with patch("tty.setraw"):
                                    result = selector.run()

        # Should have selected the first image
        assert result == [sample_images[0]]

    def test_enter_still_works(self, sample_images):
        """Test that Enter locks selections, then 'n' proceeds."""
        selector = ImageSelector(sample_images)

        # Pre-select some images
        selector.selected_indices = {0, 2}

        # Press Enter to lock, 'n' to proceed
        with patch("sys.stdin.read", side_effect=["\r", "n"]):
            with patch.object(selector, "render"):
                with patch.object(selector._preview, "request"):
                    with patch("sys.stdin.fileno", return_value=0):
                        with patch("termios.tcgetattr", return_value=[]):
                            with patch("termios.tcsetattr"):
                                with patch("tty.setraw"):
                                    result = selector.run()

        # Should return the pre-selected images
        assert result == [sample_images[0], sample_images[2]]

    def test_y_on_first_image(self, sample_images):
        """Test 'y' key on the first image (edge case)."""
        selector = ImageSelector(sample_images)
        selector.current_index = 0  # First image

        # Press 'y' to toggle, Enter to lock, 'n' to proceed
        with patch("sys.stdin.read", side_effect=["y", "\r", "n"]):
            with patch.object(selector, "render"):
                with patch.object(selector._preview, "request"):
                    with patch("sys.stdin.fileno", return_value=0):
                        with patch("termios.tcgetattr", return_value=[]):
                            with patch("termios.tcsetattr"):
                                with patch("tty.setraw"):
                                    result = selector.run()

        # Should return only the first image
        assert result == [sample_images[0]]
        assert selector.selected_indices == {0}

    def test_y_on_last_image(self, sample_images):
        """Test 'y' key on the last image (edge case)."""
        selector = ImageSelector(sample_images)
        selector.current_index = len(sample_images) - 1  # Last image

        # Press 'y' to toggle, Enter to lock, 'n' to proceed
        with patch("sys.stdin.read", side_effect=["y", "\r", "n"]):
            with patch.object(selector, "render"):
                with patch.object(selector._preview, "request"):
                    with patch("sys.stdin.fileno", return_value=0):
                        with patch("termios.tcgetattr", return_value=[]):
                            with patch("termios.tcsetattr"):
                                with patch("tty.setraw"):
                                    result = selector.run()

        # Should return only the last image
        assert result == [sample_images[2]]
        assert selector.selected_indices == {2}

    def test_uppercase_y_works(self, sample_images):
        """Test that uppercase 'Y' works the same as lowercase 'y'."""
        selector = ImageSelector(sample_images)
        selector.current_index = 1

        # Press uppercase 'Y' to toggle, Enter to lock, 'n' to proceed
        with patch("sys.stdin.read", side_effect=["Y", "\r", "n"]):
            with patch.object(selector, "render"):
                with patch.object(selector._preview, "request"):
                    with patch("sys.stdin.fileno", return_value=0):
                        with patch("termios.tcgetattr", return_value=[]):
                            with patch("termios.tcsetattr"):
                                with patch("tty.setraw"):
                                    result = selector.run()

        # Should return only current image
        assert result == [sample_images[1]]

    def test_uppercase_a_works(self, sample_images):
        """Test that uppercase 'A' works the same as lowercase 'a'."""
        selector = ImageSelector(sample_images)

        # Press uppercase 'A' to select all, Enter to lock, 'n' to proceed
        with patch("sys.stdin.read", side_effect=["A", "\r", "n"]):
            with patch.object(selector, "render"):
                with patch.object(selector._preview, "request"):
                    with patch("sys.stdin.fileno", return_value=0):
                        with patch("termios.tcgetattr", return_value=[]):
                            with patch("termios.tcsetattr"):
                                with patch("tty.setraw"):
                                    result = selector.run()

        # Should select all images
        assert len(result) == len(sample_images)


class TestProtocolDetection:
    """Tests for graphics protocol detection.

    Two values, not four. ``iterm`` and ``sixel`` both routed to the same broken
    subprocess path, so neither ever produced a correct frame; both now get the
    half-block preview, which is a strict improvement on what they had.
    """

    @pytest.mark.parametrize(
        ("environment", "expected"),
        [
            ({"TERM": "xterm-ghostty"}, GraphicsProtocol.KITTY),
            ({"TERM_PROGRAM": "ghostty"}, GraphicsProtocol.KITTY),
            ({"TERM": "xterm-kitty"}, GraphicsProtocol.KITTY),
            ({"TERM": "kitty"}, GraphicsProtocol.KITTY),
            ({"TERM": "something-kitty-variant"}, GraphicsProtocol.KITTY),
            ({"TERM_PROGRAM": "WezTerm"}, GraphicsProtocol.KITTY),
            ({"TERM": "xterm-256color"}, GraphicsProtocol.HALF_BLOCK),
            ({"TERM": "xterm-sixel"}, GraphicsProtocol.HALF_BLOCK),
            ({"TERM_PROGRAM": "iTerm.app"}, GraphicsProtocol.HALF_BLOCK),
            ({}, GraphicsProtocol.HALF_BLOCK),
        ],
    )
    def test_detection(self, environment, expected):
        with patch.dict(os.environ, environment, clear=True):
            assert detect_graphics_protocol() == expected

    @pytest.mark.parametrize(
        "multiplexer",
        [{"TMUX": "/tmp/tmux-501/default,12345,0"}, {"STY": "12345.pts-0.hostname"}],
    )
    @pytest.mark.parametrize("terminal", [{"TERM": "xterm-ghostty"}, {"TERM": "xterm-kitty"}])
    def test_a_multiplexer_forces_half_blocks(self, terminal, multiplexer):
        """A multiplexer will not pass a graphics placement through."""
        with patch.dict(os.environ, {**terminal, **multiplexer}, clear=True):
            assert detect_graphics_protocol() == GraphicsProtocol.HALF_BLOCK

    def test_an_explicit_environment_can_be_passed_in(self):
        """Detection does not have to read the process environment."""
        assert detect_graphics_protocol({"TERM": "xterm-ghostty"}) == GraphicsProtocol.KITTY


class TestMultiStageWorkflow:
    """Tests for the complete multi-stage workflow (mark → lock → proceed)."""

    def test_full_workflow_success(self, sample_images):
        """Test complete workflow: mark → lock → proceed → success."""
        selector = ImageSelector(sample_images)

        # Mark first two images, then lock, then proceed
        with patch("sys.stdin.read", side_effect=["y", "\x1b", "[", "B", " ", "\r", "n"]):
            with patch.object(selector, "render"):
                with patch.object(selector._preview, "request"):
                    with patch("sys.stdin.fileno", return_value=0):
                        with patch("termios.tcgetattr", return_value=[]):
                            with patch("termios.tcsetattr"):
                                with patch("tty.setraw"):
                                    result = selector.run()

        # Should return 2 selected images
        assert result is not None
        assert len(result) == 2
        assert sample_images[0] in result
        assert sample_images[1] in result
        assert selector._selections_locked is True

    def test_lock_without_selection(self, sample_images):
        """Test trying to lock with no images selected (should do nothing)."""
        selector = ImageSelector(sample_images)

        # Try to lock without selecting anything, then quit
        with patch("sys.stdin.read", side_effect=["\r", "q"]):
            with patch.object(selector, "render"):
                with patch.object(selector._preview, "request"):
                    with patch("sys.stdin.fileno", return_value=0):
                        with patch("termios.tcgetattr", return_value=[]):
                            with patch("termios.tcsetattr"):
                                with patch("tty.setraw"):
                                    result = selector.run()

        # Should return None (quit), lock should not have happened
        assert result is None
        assert selector._selections_locked is False
        assert len(selector.selected_indices) == 0

    def test_proceed_without_lock(self, sample_images):
        """Test trying 'n' without locking (should be ignored)."""
        selector = ImageSelector(sample_images)

        # Mark an image, try 'n' without locking, then quit
        with patch("sys.stdin.read", side_effect=["y", "n", "q"]):
            with patch.object(selector, "render"):
                with patch.object(selector._preview, "request"):
                    with patch("sys.stdin.fileno", return_value=0):
                        with patch("termios.tcgetattr", return_value=[]):
                            with patch("termios.tcsetattr"):
                                with patch("tty.setraw"):
                                    result = selector.run()

        # Should return None (quit), not proceed
        assert result is None
        assert selector._selections_locked is False

    def test_lock_unlock_cycle(self, sample_images):
        """Test lock, then unlock, then lock again."""
        selector = ImageSelector(sample_images)

        # Mark image, lock, unlock, lock again, proceed
        with patch("sys.stdin.read", side_effect=["y", "\r", "\r", "\r", "n"]):
            with patch.object(selector, "render"):
                with patch.object(selector._preview, "request"):
                    with patch("sys.stdin.fileno", return_value=0):
                        with patch("termios.tcgetattr", return_value=[]):
                            with patch("termios.tcsetattr"):
                                with patch("tty.setraw"):
                                    result = selector.run()

        # Should return selected image, and be locked at end
        assert result is not None
        assert len(result) == 1
        assert selector._selections_locked is True

    def test_mark_after_lock(self, sample_images):
        """Test that marking works even after locking (lock doesn't prevent changes)."""
        selector = ImageSelector(sample_images)

        # Mark first image, lock, mark second image, proceed
        with patch("sys.stdin.read", side_effect=["y", "\r", "\x1b", "[", "B", "y", "n"]):
            with patch.object(selector, "render"):
                with patch.object(selector._preview, "request"):
                    with patch("sys.stdin.fileno", return_value=0):
                        with patch("termios.tcgetattr", return_value=[]):
                            with patch("termios.tcsetattr"):
                                with patch("tty.setraw"):
                                    result = selector.run()

        # Should have both images selected (lock doesn't prevent changes in current implementation)
        assert result is not None
        assert len(result) == 2

    def test_unlock_allows_changes(self, sample_images):
        """Test that after unlocking, can mark/unmark images again."""
        selector = ImageSelector(sample_images)

        # Mark image, lock, unlock, unmark image, mark different image, lock, proceed
        with patch(
            "sys.stdin.read", side_effect=["y", "\r", "\r", "y", "\x1b", "[", "B", "y", "\r", "n"]
        ):
            with patch.object(selector, "render"):
                with patch.object(selector._preview, "request"):
                    with patch("sys.stdin.fileno", return_value=0):
                        with patch("termios.tcgetattr", return_value=[]):
                            with patch("termios.tcsetattr"):
                                with patch("tty.setraw"):
                                    result = selector.run()

        # Should have only second image (first was toggled off)
        assert result is not None
        assert len(result) == 1
        assert sample_images[1] in result

    def test_cancel_during_selection(self, sample_images):
        """Test pressing 'q' during marking stage."""
        selector = ImageSelector(sample_images)

        # Mark some images, then quit before locking
        with patch("sys.stdin.read", side_effect=["y", "\x1b", "[", "B", "y", "q"]):
            with patch.object(selector, "render"):
                with patch.object(selector._preview, "request"):
                    with patch("sys.stdin.fileno", return_value=0):
                        with patch("termios.tcgetattr", return_value=[]):
                            with patch("termios.tcsetattr"):
                                with patch("tty.setraw"):
                                    result = selector.run()

        # Should return None (cancelled)
        assert result is None
        assert selector._selections_locked is False

    def test_cancel_during_locked(self, sample_images):
        """Test pressing 'q' after locking."""
        selector = ImageSelector(sample_images)

        # Mark images, lock, then quit
        with patch("sys.stdin.read", side_effect=["y", "\r", "q"]):
            with patch.object(selector, "render"):
                with patch.object(selector._preview, "request"):
                    with patch("sys.stdin.fileno", return_value=0):
                        with patch("termios.tcgetattr", return_value=[]):
                            with patch("termios.tcsetattr"):
                                with patch("tty.setraw"):
                                    result = selector.run()

        # Should return None (cancelled)
        assert result is None
        assert selector._selections_locked is True  # Lock state persists

    def test_n_key_only_after_lock(self, sample_images):
        """Test that 'n' key requires lock first."""
        selector = ImageSelector(sample_images)

        # Verify 'n' is ignored without lock
        with patch("sys.stdin.read", side_effect=["y", "n", "\r", "n"]):
            with patch.object(selector, "render"):
                with patch.object(selector._preview, "request"):
                    with patch("sys.stdin.fileno", return_value=0):
                        with patch("termios.tcgetattr", return_value=[]):
                            with patch("termios.tcsetattr"):
                                with patch("tty.setraw"):
                                    result = selector.run()

        # Should successfully return (first 'n' ignored, lock happened, second 'n' proceeded)
        assert result is not None
        assert len(result) == 1

    def test_escape_key_cancels(self, sample_images):
        """Test that Escape key cancels selection."""
        selector = ImageSelector(sample_images)

        # Mark images, then press Escape (without arrow key following)
        with patch("sys.stdin.read", side_effect=["y", "\x1b", "x"]):
            with patch.object(selector, "render"):
                with patch.object(selector._preview, "request"):
                    with patch("sys.stdin.fileno", return_value=0):
                        with patch("termios.tcgetattr", return_value=[]):
                            with patch("termios.tcsetattr"):
                                with patch("tty.setraw"):
                                    result = selector.run()

        # Should return None (cancelled by Escape)
        assert result is None

    def test_lock_state_preserved_across_navigation(self, sample_images):
        """Test that lock state is preserved when navigating."""
        selector = ImageSelector(sample_images)

        # Mark, lock, navigate, verify lock persists
        with patch(
            "sys.stdin.read", side_effect=["y", "\r", "\x1b", "[", "B", "\x1b", "[", "A", "n"]
        ):
            with patch.object(selector, "render"):
                with patch.object(selector._preview, "request"):
                    with patch("sys.stdin.fileno", return_value=0):
                        with patch("termios.tcgetattr", return_value=[]):
                            with patch("termios.tcsetattr"):
                                with patch("tty.setraw"):
                                    result = selector.run()

        # Should return selected images, lock should be active
        assert result is not None
        assert selector._selections_locked is True

    def test_uppercase_n_works(self, sample_images):
        """Test that uppercase 'N' works for proceeding."""
        selector = ImageSelector(sample_images)

        # Mark, lock, proceed with uppercase N
        with patch("sys.stdin.read", side_effect=["y", "\r", "N"]):
            with patch.object(selector, "render"):
                with patch.object(selector._preview, "request"):
                    with patch("sys.stdin.fileno", return_value=0):
                        with patch("termios.tcgetattr", return_value=[]):
                            with patch("termios.tcsetattr"):
                                with patch("tty.setraw"):
                                    result = selector.run()

        # Should successfully return
        assert result is not None
        assert len(result) == 1

    def test_multiple_selections_before_lock(self, sample_images):
        """Test marking multiple images before locking."""
        selector = ImageSelector(sample_images)

        # Mark all three images, then lock, then proceed
        with patch("sys.stdin.read", side_effect=["a", "\r", "n"]):
            with patch.object(selector, "render"):
                with patch.object(selector._preview, "request"):
                    with patch("sys.stdin.fileno", return_value=0):
                        with patch("termios.tcgetattr", return_value=[]):
                            with patch("termios.tcsetattr"):
                                with patch("tty.setraw"):
                                    result = selector.run()

        # Should return all images
        assert result is not None
        assert len(result) == 3
        assert set(result) == set(sample_images)

    def test_locked_indices_stored(self, sample_images):
        """Test that locked indices are stored correctly."""
        selector = ImageSelector(sample_images)

        # Mark first and third images, lock
        with patch(
            "sys.stdin.read", side_effect=["y", "\x1b", "[", "B", "\x1b", "[", "B", "y", "\r", "n"]
        ):
            with patch.object(selector, "render"):
                with patch.object(selector._preview, "request"):
                    with patch("sys.stdin.fileno", return_value=0):
                        with patch("termios.tcgetattr", return_value=[]):
                            with patch("termios.tcsetattr"):
                                with patch("tty.setraw"):
                                    result = selector.run()

        # Verify locked indices match selected indices
        assert selector._locked_indices == {0, 2}
        assert len(result) == 2

    def test_unlock_clears_locked_indices(self, sample_images):
        """Test that unlocking clears locked indices."""
        selector = ImageSelector(sample_images)

        # Mark, lock, unlock, quit
        with patch("sys.stdin.read", side_effect=["y", "\r", "\r", "q"]):
            with patch.object(selector, "render"):
                with patch.object(selector._preview, "request"):
                    with patch("sys.stdin.fileno", return_value=0):
                        with patch("termios.tcgetattr", return_value=[]):
                            with patch("termios.tcsetattr"):
                                with patch("tty.setraw"):
                                    selector.run()

        # Verify unlocked state
        assert selector._selections_locked is False
        assert len(selector._locked_indices) == 0

    def test_ctrl_c_during_locked_stage(self, sample_images):
        """Test Ctrl+C during locked stage raises KeyboardInterrupt."""
        selector = ImageSelector(sample_images)

        # Mark, lock, then Ctrl+C
        with patch("sys.stdin.read", side_effect=["y", "\r", "\x03"]):
            with patch.object(selector, "render"):
                with patch.object(selector._preview, "request"):
                    with patch("sys.stdin.fileno", return_value=0):
                        with patch("termios.tcgetattr", return_value=[]):
                            with patch("termios.tcsetattr"):
                                with patch("tty.setraw"):
                                    with pytest.raises(KeyboardInterrupt):
                                        selector.run()

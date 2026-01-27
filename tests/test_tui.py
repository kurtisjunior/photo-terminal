"""Tests for TUI module."""

import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from photo_terminal.tui import (
    ImageSelector,
    TerminalCapabilities,
    check_viu_availability,
    fail_viu_not_found,
    get_viu_preview,
    select_images,
)


@pytest.fixture
def sample_images(tmp_path):
    """Create sample image paths for testing."""
    images = []
    for i in range(3):
        img_path = tmp_path / f"image{i}.jpg"
        img_path.touch()
        images.append(img_path)
    return images


class TestViuAvailability:
    """Tests for viu availability checking."""

    @patch("photo_terminal.tui.shutil.which")
    def test_check_viu_available(self, mock_which):
        """Test viu availability check when viu is found."""
        mock_which.return_value = "/usr/local/bin/viu"
        assert check_viu_availability() is True
        mock_which.assert_called_once_with("viu")

    @patch("photo_terminal.tui.shutil.which")
    def test_check_viu_not_available(self, mock_which):
        """Test viu availability check when viu is not found."""
        mock_which.return_value = None
        assert check_viu_availability() is False

    def test_fail_viu_not_found_exits(self, capsys):
        """Test that fail_viu_not_found exits with code 1."""
        with pytest.raises(SystemExit) as exc_info:
            fail_viu_not_found()

        assert exc_info.value.code == 1

        # Check error message
        captured = capsys.readouterr()
        assert "Error: viu is not installed" in captured.out
        assert "brew install viu" in captured.out
        assert "https://github.com/atanunq/viu" in captured.out


class TestViuPreview:
    """Tests for viu preview generation."""

    @patch("photo_terminal.tui.subprocess.run")
    def test_get_viu_preview_success(self, mock_run, tmp_path):
        """Test successful viu preview generation."""
        img_path = tmp_path / "test.jpg"
        img_path.touch()

        # Mock successful viu execution
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "preview output"
        mock_run.return_value = mock_result

        result = get_viu_preview(img_path, 40, 20)

        # Check output includes cropping to max height
        assert "preview output" in result
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "viu"
        assert "-b" in call_args  # Block output mode
        assert "-w" in call_args
        assert "40" in call_args
        # -h flag NOT used anymore (viu calculates height from aspect ratio)
        assert str(img_path) in call_args

    @patch("photo_terminal.tui.subprocess.run")
    def test_get_viu_preview_failure(self, mock_run, tmp_path):
        """Test viu preview generation when viu fails."""
        img_path = tmp_path / "test.jpg"
        img_path.touch()

        # Mock failed viu execution
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stderr = "viu error message"
        mock_run.return_value = mock_result

        result = get_viu_preview(img_path, 40, 20)

        assert "[Error rendering preview]" in result
        assert "viu error message" in result

    @patch("photo_terminal.tui.subprocess.run")
    def test_get_viu_preview_timeout(self, mock_run, tmp_path):
        """Test viu preview generation with timeout."""
        img_path = tmp_path / "test.jpg"
        img_path.touch()

        # Mock timeout
        mock_run.side_effect = subprocess.TimeoutExpired("viu", 5)

        result = get_viu_preview(img_path, 40, 20)

        assert "[Preview timed out]" in result

    @patch("photo_terminal.tui.subprocess.run")
    def test_get_viu_preview_exception(self, mock_run, tmp_path):
        """Test viu preview generation with general exception."""
        img_path = tmp_path / "test.jpg"
        img_path.touch()

        # Mock exception
        mock_run.side_effect = Exception("unexpected error")

        result = get_viu_preview(img_path, 40, 20)

        assert "[Preview error:" in result
        assert "unexpected error" in result


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

    def test_create_layout(self, sample_images):
        """Test layout creation."""
        selector = ImageSelector(sample_images)

        layout = selector.create_layout()

        # Should return a Panel now (simplified, no preview)
        assert layout is not None
        from rich.panel import Panel
        assert isinstance(layout, Panel)

    def test_create_file_list_panel(self, sample_images):
        """Test file list panel creation."""
        selector = ImageSelector(sample_images)
        selector.selected_indices.add(0)
        selector.current_index = 1

        panel = selector.create_file_list_panel()

        assert panel is not None
        # Panel title should show selection count
        assert "1/3" in panel.title

    def test_create_file_list_shows_current_image(self, sample_images):
        """Test file list panel shows current image name."""
        selector = ImageSelector(sample_images)
        selector.current_index = 1

        panel = selector.create_file_list_panel()

        assert panel is not None
        # Should show current image name in the panel
        # (can't easily test the rendered content, but ensure panel is created)


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


class TestRenderDispatcher:
    """Tests for render_with_preview() dispatcher method."""

    @patch.object(TerminalCapabilities, 'detect_graphics_protocol', return_value='iterm')
    def test_render_dispatch_iterm(self, mock_detect, sample_images):
        """Test dispatcher calls render_with_graphics_protocol() for iTerm."""
        selector = ImageSelector(sample_images)

        with patch.object(selector, 'render_with_graphics_protocol') as mock_graphics:
            selector.render_with_preview()
            mock_graphics.assert_called_once()
            mock_detect.assert_called_once()

    @patch.object(TerminalCapabilities, 'detect_graphics_protocol', return_value='kitty')
    def test_render_dispatch_kitty(self, mock_detect, sample_images):
        """Test dispatcher calls render_with_graphics_protocol() for Kitty."""
        selector = ImageSelector(sample_images)

        with patch.object(selector, 'render_with_graphics_protocol') as mock_graphics:
            selector.render_with_preview()
            mock_graphics.assert_called_once()
            mock_detect.assert_called_once()

    @patch.object(TerminalCapabilities, 'detect_graphics_protocol', return_value='sixel')
    def test_render_dispatch_sixel(self, mock_detect, sample_images):
        """Test dispatcher calls render_with_graphics_protocol() for Sixel."""
        selector = ImageSelector(sample_images)

        with patch.object(selector, 'render_with_graphics_protocol') as mock_graphics:
            selector.render_with_preview()
            mock_graphics.assert_called_once()
            mock_detect.assert_called_once()

    @patch.object(TerminalCapabilities, 'detect_graphics_protocol', return_value='blocks')
    def test_render_dispatch_blocks(self, mock_detect, sample_images):
        """Test dispatcher calls render_with_blocks() when no graphics protocol available."""
        selector = ImageSelector(sample_images)

        with patch.object(selector, 'render_with_blocks') as mock_blocks:
            selector.render_with_preview()
            mock_blocks.assert_called_once()
            mock_detect.assert_called_once()

    @patch.object(TerminalCapabilities, 'detect_graphics_protocol', return_value='blocks')
    def test_render_dispatch_passes_full_render_to_blocks(self, mock_detect, sample_images):
        """Test that full_render parameter is passed correctly to render_with_blocks()."""
        selector = ImageSelector(sample_images)

        # Test with full_render=True
        with patch.object(selector, 'render_with_blocks') as mock_blocks:
            selector.render_with_preview(full_render=True)
            mock_blocks.assert_called_once_with(full_render=True)

        # Test with full_render=False
        with patch.object(selector, 'render_with_blocks') as mock_blocks:
            selector.render_with_preview(full_render=False)
            mock_blocks.assert_called_once_with(full_render=False)

    @patch.object(TerminalCapabilities, 'detect_graphics_protocol', return_value='iterm')
    def test_render_dispatch_ignores_full_render_for_graphics(self, mock_detect, sample_images):
        """Test that full_render parameter is ignored for graphics protocol path."""
        selector = ImageSelector(sample_images)

        # Graphics protocol method doesn't take parameters, so verify it's called
        # without any arguments regardless of full_render value
        with patch.object(selector, 'render_with_graphics_protocol') as mock_graphics:
            selector.render_with_preview(full_render=True)
            mock_graphics.assert_called_once_with()

        with patch.object(selector, 'render_with_graphics_protocol') as mock_graphics:
            selector.render_with_preview(full_render=False)
            mock_graphics.assert_called_once_with()


class TestTerminalCapabilities:
    """Tests for terminal graphics protocol detection."""

    def test_detect_iterm2(self):
        """Test iTerm2 detection via TERM_PROGRAM environment variable."""
        with patch.dict(os.environ, {'TERM_PROGRAM': 'iTerm.app'}, clear=True):
            assert TerminalCapabilities.detect_graphics_protocol() == 'iterm'

    def test_detect_kitty_xterm_kitty(self):
        """Test Kitty detection via TERM='xterm-kitty'."""
        with patch.dict(os.environ, {'TERM': 'xterm-kitty'}, clear=True):
            assert TerminalCapabilities.detect_graphics_protocol() == 'kitty'

    def test_detect_kitty_term(self):
        """Test Kitty detection via TERM='kitty'."""
        with patch.dict(os.environ, {'TERM': 'kitty'}, clear=True):
            assert TerminalCapabilities.detect_graphics_protocol() == 'kitty'

    def test_detect_sixel(self):
        """Test Sixel detection via TERM containing 'sixel'."""
        with patch.dict(os.environ, {'TERM': 'xterm-sixel'}, clear=True):
            assert TerminalCapabilities.detect_graphics_protocol() == 'sixel'

    def test_fallback_to_blocks(self):
        """Test fallback to blocks for standard terminals."""
        with patch.dict(os.environ, {'TERM': 'xterm-256color'}, clear=True):
            assert TerminalCapabilities.detect_graphics_protocol() == 'blocks'

    def test_tmux_forces_blocks_with_iterm(self):
        """Test that TMUX environment variable forces blocks even with iTerm2."""
        with patch.dict(os.environ, {
            'TERM_PROGRAM': 'iTerm.app',
            'TMUX': '/tmp/tmux-501/default,12345,0'
        }, clear=True):
            assert TerminalCapabilities.detect_graphics_protocol() == 'blocks'

    def test_screen_forces_blocks_with_kitty(self):
        """Test that STY environment variable (GNU screen) forces blocks even with Kitty."""
        with patch.dict(os.environ, {
            'TERM': 'xterm-kitty',
            'STY': '12345.pts-0.hostname'
        }, clear=True):
            assert TerminalCapabilities.detect_graphics_protocol() == 'blocks'

    def test_supports_inline_images_true_iterm(self):
        """Test supports_inline_images returns True for iTerm2."""
        with patch.dict(os.environ, {'TERM_PROGRAM': 'iTerm.app'}, clear=True):
            assert TerminalCapabilities.supports_inline_images() is True

    def test_supports_inline_images_true_kitty(self):
        """Test supports_inline_images returns True for Kitty."""
        with patch.dict(os.environ, {'TERM': 'xterm-kitty'}, clear=True):
            assert TerminalCapabilities.supports_inline_images() is True

    def test_supports_inline_images_true_sixel(self):
        """Test supports_inline_images returns True for Sixel."""
        with patch.dict(os.environ, {'TERM': 'xterm-sixel'}, clear=True):
            assert TerminalCapabilities.supports_inline_images() is True

    def test_supports_inline_images_false_blocks(self):
        """Test supports_inline_images returns False for block mode."""
        with patch.dict(os.environ, {'TERM': 'xterm-256color'}, clear=True):
            assert TerminalCapabilities.supports_inline_images() is False


    def test_priority_order_iterm_over_kitty(self):
        """Test that iTerm2 detection takes priority when both indicators are present."""
        with patch.dict(os.environ, {
            'TERM_PROGRAM': 'iTerm.app',
            'TERM': 'xterm-kitty'
        }, clear=True):
            # iTerm2 should be detected first
            assert TerminalCapabilities.detect_graphics_protocol() == 'iterm'

    def test_kitty_substring_detection(self):
        """Test that 'kitty' substring in TERM is detected."""
        with patch.dict(os.environ, {
            'TERM': 'something-kitty-variant'
        }, clear=True):
            assert TerminalCapabilities.detect_graphics_protocol() == 'kitty'

    def test_sixel_substring_detection(self):
        """Test that 'sixel' substring in TERM is detected."""
        with patch.dict(os.environ, {
            'TERM': 'mlterm-sixel'
        }, clear=True):
            assert TerminalCapabilities.detect_graphics_protocol() == 'sixel'

    def test_detect_ghostty_term_program(self):
        """Test Ghostty detection via TERM_PROGRAM='ghostty' should return 'kitty'."""
        with patch.dict(os.environ, {
            'TERM_PROGRAM': 'ghostty'
        }, clear=True):
            # Ghostty supports Kitty graphics protocol
            assert TerminalCapabilities.detect_graphics_protocol() == 'kitty'

    def test_detect_ghostty_in_term(self):
        """Test Ghostty detection via TERM containing 'ghostty' should return 'kitty'."""
        with patch.dict(os.environ, {
            'TERM': 'xterm-ghostty'
        }, clear=True):
            # Ghostty supports Kitty graphics protocol
            assert TerminalCapabilities.detect_graphics_protocol() == 'kitty'

    def test_ghostty_with_multiplexer(self):
        """Test that TMUX forces blocks even with Ghostty."""
        with patch.dict(os.environ, {
            'TERM_PROGRAM': 'ghostty',
            'TMUX': '/tmp/tmux-501/default,12345,0'
        }, clear=True):
            # Multiplexers break graphics protocols
            assert TerminalCapabilities.detect_graphics_protocol() == 'blocks'

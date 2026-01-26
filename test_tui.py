"""Tests for TUI module."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from tui import (
    ImageSelector,
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

    @patch("tui.shutil.which")
    def test_check_viu_available(self, mock_which):
        """Test viu availability check when viu is found."""
        mock_which.return_value = "/usr/local/bin/viu"
        assert check_viu_availability() is True
        mock_which.assert_called_once_with("viu")

    @patch("tui.shutil.which")
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

    @patch("tui.subprocess.run")
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

        assert result == "preview output"
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "viu"
        assert "-w" in call_args
        assert "40" in call_args
        assert "-h" in call_args
        assert "20" in call_args
        assert str(img_path) in call_args

    @patch("tui.subprocess.run")
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

    @patch("tui.subprocess.run")
    def test_get_viu_preview_timeout(self, mock_run, tmp_path):
        """Test viu preview generation with timeout."""
        img_path = tmp_path / "test.jpg"
        img_path.touch()

        # Mock timeout
        mock_run.side_effect = subprocess.TimeoutExpired("viu", 5)

        result = get_viu_preview(img_path, 40, 20)

        assert "[Preview timed out]" in result

    @patch("tui.subprocess.run")
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

    @patch("tui.ImageSelector.create_file_list_panel")
    @patch("tui.ImageSelector.create_preview_panel")
    def test_create_layout(self, mock_preview, mock_file_list, sample_images):
        """Test layout creation."""
        selector = ImageSelector(sample_images)

        mock_file_list.return_value = "file_list_panel"
        mock_preview.return_value = "preview_panel"

        layout = selector.create_layout()

        assert layout is not None
        mock_file_list.assert_called_once()
        mock_preview.assert_called_once()

    def test_create_file_list_panel(self, sample_images):
        """Test file list panel creation."""
        selector = ImageSelector(sample_images)
        selector.selected_indices.add(0)
        selector.current_index = 1

        panel = selector.create_file_list_panel()

        assert panel is not None
        # Panel title should show selection count
        assert "1/3" in panel.title

    @patch("tui.get_viu_preview")
    def test_create_preview_panel(self, mock_viu, sample_images):
        """Test preview panel creation."""
        selector = ImageSelector(sample_images)
        mock_viu.return_value = "preview output"

        panel = selector.create_preview_panel()

        assert panel is not None
        mock_viu.assert_called_once()
        assert "image0.jpg" in panel.title


class TestSelectImages:
    """Tests for select_images function."""

    @patch("tui.check_viu_availability")
    def test_select_images_viu_not_available(self, mock_check, sample_images):
        """Test select_images when viu is not available."""
        mock_check.return_value = False

        with pytest.raises(SystemExit) as exc_info:
            select_images(sample_images)

        assert exc_info.value.code == 1

    @patch("tui.check_viu_availability")
    def test_select_images_no_images(self, mock_check):
        """Test select_images with no images."""
        mock_check.return_value = True

        with pytest.raises(SystemExit) as exc_info:
            select_images([])

        assert exc_info.value.code == 1

    @patch("tui.check_viu_availability")
    @patch("tui.ImageSelector")
    def test_select_images_user_cancels(self, mock_selector_class, mock_check, sample_images):
        """Test select_images when user cancels."""
        mock_check.return_value = True

        # Mock selector to return None (cancelled)
        mock_selector = MagicMock()
        mock_selector.run.return_value = None
        mock_selector_class.return_value = mock_selector

        with pytest.raises(SystemExit) as exc_info:
            select_images(sample_images)

        assert exc_info.value.code == 1

    @patch("tui.check_viu_availability")
    @patch("tui.ImageSelector")
    def test_select_images_success(self, mock_selector_class, mock_check, sample_images):
        """Test successful image selection."""
        mock_check.return_value = True

        # Mock selector to return selected images
        mock_selector = MagicMock()
        selected_images = [sample_images[0], sample_images[2]]
        mock_selector.run.return_value = selected_images
        mock_selector_class.return_value = mock_selector

        result = select_images(sample_images)

        assert result == selected_images

    @patch("tui.check_viu_availability")
    @patch("tui.ImageSelector")
    def test_select_images_keyboard_interrupt(self, mock_selector_class, mock_check, sample_images):
        """Test select_images when user presses Ctrl+C."""
        mock_check.return_value = True

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

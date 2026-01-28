"""Tests for processing configuration UI."""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from photo_terminal.tui import show_processing_config


class TestShowProcessingConfig:
    """Test suite for show_processing_config function."""

    def test_returns_dict_structure(self):
        """Test that function signature and dict structure are correct."""
        # This is a structure test - actual UI testing requires terminal interaction
        locked_images = [Path("/tmp/img1.jpg"), Path("/tmp/img2.jpg")]
        config = {'target_size_kb': 400}

        # We can't easily test the interactive UI without mocking stdin/termios
        # but we can verify the function exists and has correct signature
        assert callable(show_processing_config)

        # Verify docstring exists
        assert show_processing_config.__doc__ is not None
        assert "locked_images" in show_processing_config.__doc__
        assert "config" in show_processing_config.__doc__

    @patch('sys.stdin')
    @patch('termios.tcgetattr')
    @patch('termios.tcsetattr')
    @patch('tty.setraw')
    def test_confirm_returns_valid_dict(self, mock_setraw, mock_tcsetattr,
                                        mock_tcgetattr, mock_stdin):
        """Test that confirming returns a properly structured dict."""
        # Mock terminal settings
        mock_tcgetattr.return_value = []

        # Simulate user pressing Enter immediately (confirm defaults)
        mock_stdin.read = MagicMock(side_effect=['\r'])
        mock_stdin.fileno = MagicMock(return_value=0)

        locked_images = [Path("/tmp/img1.jpg"), Path("/tmp/img2.jpg")]
        config = {'target_size_kb': 500}

        result = show_processing_config(locked_images, config)

        # Verify result structure
        assert isinstance(result, dict)
        assert 'resize' in result
        assert 'target_size_kb' in result
        assert 'preserve_exif' in result

        # Verify default values
        assert result['resize'] is True
        assert result['preserve_exif'] is True
        assert result['target_size_kb'] == 500

    @patch('sys.stdin')
    @patch('termios.tcgetattr')
    @patch('termios.tcsetattr')
    @patch('tty.setraw')
    def test_cancel_returns_none(self, mock_setraw, mock_tcsetattr,
                                  mock_tcgetattr, mock_stdin):
        """Test that pressing 'q' returns None."""
        # Mock terminal settings
        mock_tcgetattr.return_value = []

        # Simulate user pressing 'q' to cancel
        mock_stdin.read = MagicMock(side_effect=['q'])
        mock_stdin.fileno = MagicMock(return_value=0)

        locked_images = [Path("/tmp/img1.jpg")]
        config = {'target_size_kb': 400}

        result = show_processing_config(locked_images, config)

        # Verify None is returned on cancel
        assert result is None

    @patch('sys.stdin')
    @patch('termios.tcgetattr')
    @patch('termios.tcsetattr')
    @patch('tty.setraw')
    def test_back_returns_none(self, mock_setraw, mock_tcsetattr,
                                mock_tcgetattr, mock_stdin):
        """Test that pressing 'b' (back) returns None."""
        # Mock terminal settings
        mock_tcgetattr.return_value = []

        # Simulate user pressing 'b' to go back
        mock_stdin.read = MagicMock(side_effect=['b'])
        mock_stdin.fileno = MagicMock(return_value=0)

        locked_images = [Path("/tmp/img1.jpg")]
        config = {'target_size_kb': 400}

        result = show_processing_config(locked_images, config)

        # Verify None is returned on back
        assert result is None

    @patch('sys.stdin')
    @patch('termios.tcgetattr')
    @patch('termios.tcsetattr')
    @patch('tty.setraw')
    def test_uses_config_target_size(self, mock_setraw, mock_tcsetattr,
                                      mock_tcgetattr, mock_stdin):
        """Test that target_size_kb from config is used correctly."""
        # Mock terminal settings
        mock_tcgetattr.return_value = []

        # Simulate user pressing Enter to confirm
        mock_stdin.read = MagicMock(side_effect=['\r'])
        mock_stdin.fileno = MagicMock(return_value=0)

        locked_images = [Path("/tmp/img1.jpg")]
        custom_size = 600
        config = {'target_size_kb': custom_size}

        result = show_processing_config(locked_images, config)

        # Verify custom target size is included
        assert result['target_size_kb'] == custom_size

    @patch('sys.stdin')
    @patch('termios.tcgetattr')
    @patch('termios.tcsetattr')
    @patch('tty.setraw')
    def test_toggle_options(self, mock_setraw, mock_tcsetattr,
                            mock_tcgetattr, mock_stdin):
        """Test that spacebar toggles options correctly."""
        # Mock terminal settings
        mock_tcgetattr.return_value = []

        # Simulate: Space (toggle resize), Enter (confirm)
        mock_stdin.read = MagicMock(side_effect=[' ', '\r'])
        mock_stdin.fileno = MagicMock(return_value=0)

        locked_images = [Path("/tmp/img1.jpg")]
        config = {'target_size_kb': 400}

        result = show_processing_config(locked_images, config)

        # Verify resize was toggled to False (default is True)
        assert result['resize'] is False
        # preserve_exif should still be True (not toggled)
        assert result['preserve_exif'] is True

"""Tests for the Enter-to-submit final confirmation screen."""

from unittest.mock import patch

import pytest

from photo_terminal.terminal.screens.confirm import confirm_upload


@pytest.fixture
def sample_images(tmp_path):
    images = []
    for i in range(3):
        image = tmp_path / f"test{i}.jpg"
        image.touch()
        images.append(image)
    return images


def test_enter_submits_the_upload(sample_images):
    with patch("builtins.input", return_value=""):
        assert confirm_upload(sample_images, "test-bucket", "japan/tokyo") is True


@pytest.mark.parametrize("answer", ["q", "quit", "cancel", " Q "])
def test_cancel_words_decline_the_upload(sample_images, answer):
    with patch("builtins.input", return_value=answer):
        assert confirm_upload(sample_images, "test-bucket", "japan/tokyo") is False


def test_eof_declines_the_upload(sample_images, capsys):
    with patch("builtins.input", side_effect=EOFError):
        assert confirm_upload(sample_images, "test-bucket", "japan/tokyo") is False

    assert "Upload cancelled." in capsys.readouterr().out


def test_the_summary_is_shown_before_submission(sample_images, capsys):
    with patch("builtins.input", return_value=""):
        confirm_upload(sample_images, "test-bucket", "japan/tokyo")

    output = capsys.readouterr().out
    assert "Upload Confirmation" in output
    assert "Images to upload: 3" in output
    assert "test0.jpg" in output


def test_unrecognised_input_reasks_for_enter(sample_images, capsys):
    with patch("builtins.input", side_effect=["yes", ""]):
        assert confirm_upload(sample_images, "test-bucket", "japan/tokyo") is True

    assert "Press Enter to upload" in capsys.readouterr().out

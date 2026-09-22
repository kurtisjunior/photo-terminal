"""Tests for the confirmation prompt screen.

Declining used to raise ``SystemExit(1)`` from inside a library function, so
every one of these was a ``pytest.raises`` block that could not tell "the user
said no" from "something broke". The screen answers the question instead.
"""

from unittest.mock import patch

import pytest

from photo_terminal.terminal.screens.confirm import confirm_upload


@pytest.fixture
def sample_images(tmp_path):
    """Create sample image paths for testing."""
    images = []
    for i in range(3):
        img_path = tmp_path / f"test{i}.jpg"
        img_path.touch()
        images.append(img_path)
    return images


@pytest.mark.parametrize("answer", ["y", "yes", "Y", "Yes", "  y  "])
def test_an_affirmative_answer_confirms(sample_images, answer):
    with patch("builtins.input", return_value=answer):
        assert confirm_upload(sample_images, "test-bucket", "japan/tokyo/") is True


@pytest.mark.parametrize("answer", ["n", "no", "N", "No"])
def test_a_negative_answer_declines(sample_images, answer):
    with patch("builtins.input", return_value=answer):
        assert confirm_upload(sample_images, "test-bucket", "japan/tokyo/") is False


def test_declining_says_so_and_does_not_exit(sample_images, capsys):
    with patch("builtins.input", return_value="n"):
        result = confirm_upload(sample_images, "test-bucket", "japan/tokyo/")

    assert result is False
    assert "Upload cancelled." in capsys.readouterr().out


def test_eof_is_a_decline_rather_than_a_crash(sample_images, capsys):
    with patch("builtins.input", side_effect=EOFError):
        result = confirm_upload(sample_images, "test-bucket", "japan/tokyo/")

    assert result is False
    assert "Upload cancelled." in capsys.readouterr().out


def test_the_summary_is_shown_before_the_prompt(sample_images, capsys):
    with patch("builtins.input", return_value="y"):
        confirm_upload(sample_images, "test-bucket", "japan/tokyo/")

    out = capsys.readouterr().out
    assert "Upload Confirmation" in out
    assert "Images to upload: 3" in out
    assert "test0.jpg" in out


def test_an_unrecognised_answer_re_asks(sample_images, capsys):
    with patch("builtins.input", side_effect=["invalid", "y"]):
        result = confirm_upload(sample_images, "test-bucket", "japan/tokyo/")

    assert result is True
    assert "Invalid input" in capsys.readouterr().out


def test_it_keeps_re_asking_until_it_gets_an_answer(sample_images, capsys):
    with patch("builtins.input", side_effect=["maybe", "x", "n"]):
        result = confirm_upload(sample_images, "test-bucket", "japan/tokyo/")

    assert result is False
    assert capsys.readouterr().out.count("Invalid input") == 2


def test_an_empty_answer_is_not_a_yes(sample_images, capsys):
    with patch("builtins.input", side_effect=["", "y"]):
        result = confirm_upload(sample_images, "test-bucket", "japan/tokyo/")

    assert result is True
    assert "Invalid input" in capsys.readouterr().out

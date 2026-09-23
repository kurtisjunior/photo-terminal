"""The line-mode yes/no used for the reorder hand-off."""

from unittest.mock import patch

import pytest

from photo_terminal.terminal.screens.prompt import ask_yes_no


@pytest.mark.parametrize("answer", ["y", "Y", "yes", "YES", " yes "])
def test_yes_in_every_spelling(answer):
    with patch("builtins.input", return_value=answer):
        assert ask_yes_no("Reorder? ") is True


@pytest.mark.parametrize("answer", ["n", "N", "no", "NO", " no "])
def test_no_in_every_spelling(answer):
    with patch("builtins.input", return_value=answer):
        assert ask_yes_no("Reorder? ", default=True) is False


def test_an_empty_line_takes_the_default():
    with patch("builtins.input", return_value=""):
        assert ask_yes_no("Reorder? ") is False
        assert ask_yes_no("Reorder? ", default=True) is True


def test_an_unrecognised_answer_takes_the_default():
    with patch("builtins.input", return_value="maybe"):
        assert ask_yes_no("Reorder? ") is False


def test_eof_is_a_default_rather_than_a_crash():
    """Ctrl-D used to raise out of the middle of ``main()``."""
    with patch("builtins.input", side_effect=EOFError):
        assert ask_yes_no("Reorder? ") is False


def test_the_question_is_asked_verbatim():
    with patch("builtins.input", return_value="n") as mock_input:
        ask_yes_no("Reorder images? (y/N): ")

    mock_input.assert_called_once_with("Reorder images? (y/N): ")

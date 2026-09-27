"""Tests for the typed upload-location stage."""

from unittest.mock import patch

from photo_terminal.terminal.screens.destination import enter_upload_location


def test_enter_completes_the_stage_with_a_normalized_location(capsys):
    with patch("builtins.input", return_value="  /newyork/summer-23/  "):
        result = enter_upload_location("two-touch")

    assert result == "newyork/summer-23"
    output = capsys.readouterr().out
    assert "Upload Location" in output
    assert "s3://two-touch/" in output


def test_blank_location_selects_the_bucket_root():
    with patch("builtins.input", return_value=""):
        assert enter_upload_location("two-touch") == ""


def test_eof_cancels_the_stage(capsys):
    with patch("builtins.input", side_effect=EOFError):
        assert enter_upload_location("two-touch") is None

    assert "Upload cancelled." in capsys.readouterr().out

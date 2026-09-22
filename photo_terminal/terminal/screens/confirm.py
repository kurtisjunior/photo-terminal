"""The upload confirmation prompt.

A line-mode screen rather than a full-screen one: it prints a summary and reads
a ``y``/``n`` on the main buffer, so no session, no raw mode and no alternate
screen are involved.

It used to raise ``SystemExit(1)`` from inside ``confirmation.py`` when the
user declined, which made "the user said no" indistinguishable from "something
failed" and put an exit code inside a library module. It now answers the
question it was asked - ``True`` or ``False`` - and the caller decides.
"""

from pathlib import Path

from photo_terminal.confirmation import build_confirmation_prompt, build_confirmation_summary

__all__ = ["confirm_upload"]


def confirm_upload(images: list[Path], bucket: str, prefix: str) -> bool:
    """Display the upload summary and prompt for confirmation.

    Args:
        images: List of image paths to upload
        bucket: S3 bucket name
        prefix: S3 prefix/folder path (may be empty string for root)

    Returns:
        True if the user confirmed, False if they declined or sent EOF.
    """
    print(build_confirmation_summary(images, bucket, prefix))
    print()

    prompt = build_confirmation_prompt(images, bucket, prefix)

    while True:
        try:
            response = input(prompt).strip().lower()
        except EOFError:
            # Ctrl-D is a decline, not a crash.
            print()
            print("Upload cancelled.")
            return False

        if response in ("y", "yes"):
            print()
            return True

        if response in ("n", "no"):
            print()
            print("Upload cancelled.")
            return False

        print("Invalid input. Please enter 'y' or 'n'.")

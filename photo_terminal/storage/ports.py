"""What the layers above need from storage.

One port, stated once. The S3 browser screen is handed a :class:`FolderLister`
and asks it what is under a prefix; the pipeline hands it the boto3
implementation from :mod:`photo_terminal.storage.s3`. That is what keeps the
AWS SDK out of the terminal package, and it is what lets the browser's tests
drive a real ``run()`` loop against a dictionary of folder names.

The port carries no imports beyond ``typing``, so depending on it costs a
caller nothing - importing this module does not import boto3.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

__all__ = ["FolderLister"]


@runtime_checkable
class FolderLister(Protocol):
    """Answers "what folders are directly under this prefix?"."""

    def list_folders(self, prefix: str) -> list[str]:
        """The folder names directly under ``prefix``, sorted.

        Args:
            prefix: An S3 prefix ending in ``/``, or ``""`` for the bucket root.

        Returns:
            Folder names, without the prefix path and without trailing slashes.

        Raises:
            PhotoTerminalError: If the listing could not be made.
        """
        ...

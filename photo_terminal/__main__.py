#!/usr/bin/env python3
"""Photo upload manager CLI entry point.

Terminal-based image upload manager with inline preview and batch JPEG
optimization for S3 uploads.

Usage:
    photo-upload <folder_path> [--prefix <s3_prefix>] [options]

Example:
    photo-upload ./images --prefix japan/tokyo --target-size 500 --dry-run

This module is argv in, exit code out, and nothing else. It used to be 373
lines, 285 of them a single ``main()``; what it did now lives in
:mod:`photo_terminal.app.cli` and :mod:`photo_terminal.app.pipeline`.
"""

import sys

from photo_terminal.app.cli import run


def main() -> int:
    """Run the CLI over ``sys.argv`` and return the process exit code."""
    return run(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())

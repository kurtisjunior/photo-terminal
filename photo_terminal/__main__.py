#!/usr/bin/env python3
"""Photo upload manager CLI.

Terminal-based image upload manager with inline preview and batch JPEG
optimization for S3 uploads.

Usage:
    photo_upload.py <folder_path> --prefix <s3_prefix> [options]

Example:
    photo_upload.py ./images --prefix japan/tokyo --target-size 500 --dry-run
"""

import argparse
import logging
import os
import sys
from pathlib import Path

from photo_terminal.config import load_config
from photo_terminal.scanner import scan_folder
from photo_terminal.tui import select_images
from photo_terminal.s3_browser import browse_s3_folders
from photo_terminal.confirmation import confirm_upload
from photo_terminal.dry_run import dry_run_upload
from photo_terminal.duplicate_checker import check_for_duplicates, DuplicateFilesError
from photo_terminal.processor import process_images, ProcessingError, InsufficientDiskSpaceError
from photo_terminal.uploader import upload_images, UploadError
from photo_terminal.summary import show_completion_summary


def validate_folder_path(folder_path: str) -> Path:
    """Validate that folder path exists and is a directory.

    Args:
        folder_path: Path to validate

    Returns:
        Path object if valid

    Raises:
        SystemExit: If path doesn't exist or is not a directory
    """
    path = Path(folder_path).resolve()

    if not path.exists():
        print(f"Error: Folder does not exist: {folder_path}")
        raise SystemExit(1)

    if not path.is_dir():
        print(f"Error: Path is not a directory: {folder_path}")
        raise SystemExit(1)

    return path


def print_effective_config(cfg, args, folder_path: Path) -> None:
    """Print the effective configuration that will be used.

    Args:
        cfg: Config object
        args: Parsed command-line arguments
        folder_path: Validated folder path
    """
    print("Photo Upload Manager")
    print("=" * 50)
    print()
    print("Configuration:")
    print(f"  Source folder:  {folder_path}")
    print(f"  S3 bucket:      {cfg.bucket}")
    print(f"  S3 prefix:      {args.prefix if args.prefix else '(root)'}")
    print(f"  AWS profile:    {cfg.aws_profile}")
    print(f"  Target size:    {cfg.target_size_kb} KB")
    print(f"  Dry-run mode:   {'Yes' if args.dry_run else 'No'}")
    print()

    if args.prefix:
        s3_target = f"s3://{cfg.bucket}/{args.prefix}/"
    else:
        s3_target = f"s3://{cfg.bucket}/"

    print(f"Upload target: {s3_target}")
    print()


def main():
    """Main CLI entry point."""
    # Enable debug logging if environment variable is set
    if os.environ.get('PHOTO_TERMINAL_DEBUG'):
        logging.basicConfig(
            filename='/tmp/photo_terminal_debug.log',
            level=logging.DEBUG,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            force=True
        )
        # Also log to console
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        logging.getLogger().addHandler(console_handler)

        logging.info("=== Photo Terminal Debug Mode ===")
        logging.info(f"Terminal: {os.environ.get('TERM', 'unknown')}")
        logging.info(f"TERM_PROGRAM: {os.environ.get('TERM_PROGRAM', 'unknown')}")

    # Load configuration from YAML file
    try:
        cfg = load_config()
    except SystemExit:
        # Config loading already printed error message
        return 1

    # Set up argument parser
    parser = argparse.ArgumentParser(
        description='Upload and optimize photos to S3 with inline preview',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s ./images --prefix japan/tokyo
  %(prog)s ./photos --prefix italy/trapani --target-size 500
  %(prog)s ./vacation --prefix spain/barcelona --dry-run

Configuration:
  Edit ~/.photo-uploader.yaml to change default settings.
  CLI arguments override config file values.
        """
    )

    # Required positional argument
    parser.add_argument(
        'folder_path',
        help='Path to folder containing images'
    )

    # Optional arguments
    parser.add_argument(
        '--prefix',
        help='S3 prefix/folder path (e.g., "japan/tokyo")',
        default=None
    )

    parser.add_argument(
        '--target-size',
        type=int,
        metavar='KB',
        help=f'Target file size in KB (default: {cfg.target_size_kb})'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview without uploading'
    )

    # Parse arguments
    args = parser.parse_args()

    # Validate folder path (fail-fast)
    try:
        folder_path = validate_folder_path(args.folder_path)
    except SystemExit:
        return 1

    # Apply CLI overrides to config
    if args.target_size:
        cfg.target_size_kb = args.target_size

    # Print effective configuration
    print_effective_config(cfg, args, folder_path)

    # Scan folder for valid images (fail-fast)
    try:
        valid_images = scan_folder(folder_path)
    except SystemExit:
        return 1

    # Interactive image selection with two-pane TUI (fail-fast)
    try:
        selected_images = select_images(valid_images)
    except SystemExit:
        return 1

    # Display selected images count
    print()
    print(f"Selected {len(selected_images)} image(s):")
    for img in selected_images:
        print(f"  - {img.name}")
    print()

    # S3 folder browser (Task #5)
    # Skip browser if --prefix was provided via CLI
    try:
        selected_prefix = browse_s3_folders(
            cfg.bucket,
            cfg.aws_profile,
            args.prefix  # None if not provided, which triggers interactive browser
        )
    except SystemExit:
        return 1

    # Display selected S3 prefix
    print()
    if selected_prefix:
        print(f"Upload target: s3://{cfg.bucket}/{selected_prefix}")
    else:
        print(f"Upload target: s3://{cfg.bucket}/ (root)")
    print()

    # Selection confirmation with count display (Task #6)
    try:
        confirm_upload(selected_images, cfg.bucket, selected_prefix)
    except SystemExit:
        return 1

    # Check if dry-run mode is enabled
    if args.dry_run:
        # Run dry-run mode (shows sizes, exits without uploading)
        try:
            dry_run_upload(
                selected_images,
                cfg.bucket,
                selected_prefix,
                cfg.target_size_kb,
                cfg.aws_profile
            )
        except SystemExit as e:
            # dry_run_upload always exits - return its exit code
            return e.code if e.code is not None else 0

    # Check for duplicates in S3 (fail-fast before processing)
    print("Checking for duplicate files in S3...")
    try:
        check_for_duplicates(
            selected_images,
            cfg.bucket,
            selected_prefix,
            cfg.aws_profile
        )
        print("No duplicates found - proceeding with upload")
        print()
    except DuplicateFilesError as e:
        # Print the detailed error message from DuplicateFilesError
        print()
        print(str(e))
        return 1
    except SystemExit:
        # AWS credential/permission errors already printed
        return 1

    # Process images (optimize with temp file management)
    print("Processing images...")
    print()
    try:
        temp_dir, processed_images = process_images(
            selected_images,
            cfg.target_size_kb
        )
    except InsufficientDiskSpaceError as e:
        print(f"Error: {e}")
        return 1
    except ProcessingError as e:
        print(f"Error: {e}")
        return 1
    except Exception as e:
        print(f"Unexpected error during image processing: {e}")
        return 1

    # Upload to S3 with progress feedback
    try:
        uploaded_keys = upload_images(
            processed_images,
            cfg.bucket,
            selected_prefix,
            cfg.aws_profile
        )
    except UploadError as e:
        print(f"Error: {e}")
        print()
        print("Upload failed. Temp files preserved for retry.")
        return 1
    except Exception as e:
        print(f"Unexpected error during upload: {e}")
        print()
        print("Upload failed. Temp files preserved for retry.")
        return 1

    # Show completion summary
    try:
        show_completion_summary(
            processed_images,
            uploaded_keys,
            cfg.bucket,
            selected_prefix
        )
    except Exception as e:
        print(f"Warning: Failed to display completion summary: {e}")
        # Don't fail on summary display error
        print()
        print(f"Upload completed successfully: {len(uploaded_keys)} files")
        print()

    # Cleanup temp files on success
    try:
        temp_dir.cleanup()
    except Exception as e:
        # Don't fail on cleanup error, just warn
        print(f"Warning: Failed to cleanup temp files: {e}")

    return 0


if __name__ == '__main__':
    sys.exit(main())

"""Debug version of TUI with logging."""

import logging
import sys
from pathlib import Path
from photo_terminal.tui import ImageSelector, check_viu_availability, fail_viu_not_found

# Set up debug logging
logging.basicConfig(
    filename='/tmp/photo_terminal_debug.log',
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def debug_select_images(images):
    """Debug wrapper for image selection."""
    logging.info("=== Starting debug_select_images ===")
    logging.info(f"Number of images: {len(images)}")

    # Check viu
    logging.info("Checking viu availability...")
    if not check_viu_availability():
        logging.error("viu not available")
        fail_viu_not_found()
    logging.info("viu is available")

    # Create selector
    logging.info("Creating ImageSelector...")
    selector = ImageSelector(images)
    logging.info("ImageSelector created")

    # Try to create file list panel
    logging.info("Creating file list panel...")
    try:
        file_list = selector.create_file_list_panel()
        logging.info(f"File list panel created: {type(file_list)}")
    except Exception as e:
        logging.error(f"Failed to create file list panel: {e}", exc_info=True)
        raise

    # Try to create preview panel
    logging.info("Creating preview panel...")
    try:
        preview = selector.create_preview_panel()
        logging.info(f"Preview panel created: {type(preview)}")
    except Exception as e:
        logging.error(f"Failed to create preview panel: {e}", exc_info=True)
        raise

    # Try to create layout
    logging.info("Creating layout...")
    try:
        layout = selector.create_layout()
        logging.info(f"Layout created: {type(layout)}")
    except Exception as e:
        logging.error(f"Failed to create layout: {e}", exc_info=True)
        raise

    # Try to run
    logging.info("Starting selector.run()...")
    try:
        result = selector.run()
        logging.info(f"Selector completed with result: {result}")
        return result
    except KeyboardInterrupt:
        logging.info("User cancelled with Ctrl+C")
        raise SystemExit(1)
    except Exception as e:
        logging.error(f"Selector failed: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m photo_terminal.tui_debug <image_dir>")
        sys.exit(1)

    image_dir = Path(sys.argv[1]).expanduser()
    images = sorted(list(image_dir.glob("*.jpg")) + list(image_dir.glob("*.JPG")))

    if not images:
        print(f"No images found in {image_dir}")
        sys.exit(1)

    print(f"Found {len(images)} images")
    print("Debug log: /tmp/photo_terminal_debug.log")
    print("Run: tail -f /tmp/photo_terminal_debug.log")
    print()

    try:
        selected = debug_select_images(images)
        print(f"\nSelected {len(selected)} images")
    except Exception as e:
        print(f"\nError: {e}")
        print("Check /tmp/photo_terminal_debug.log for details")
        sys.exit(1)

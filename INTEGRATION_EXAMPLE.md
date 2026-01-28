# Processing Configuration Integration Example

This document shows how to integrate the `show_processing_config` function into the main workflow.

## Current Implementation Location

The `show_processing_config` function is located in `/Users/kurtis/tinker/photo-terminal/photo_terminal/tui.py` after the `ImageSelector` class definition.

## Function Signature

```python
def show_processing_config(locked_images: List[Path], config: dict) -> dict:
    """Show processing configuration screen for locked images.

    Args:
        locked_images: List of selected image paths
        config: Configuration dict from ~/.photo-uploader.yaml

    Returns:
        Processing configuration dict with user's choices, or None if cancelled
    """
```

## Integration Example

### In `__main__.py`:

```python
from photo_terminal.tui import select_images, show_processing_config

# After image selection (line 178):
try:
    selected_images = select_images(valid_images)
except SystemExit:
    return 1

# NEW: Show processing configuration stage
try:
    # Convert Config object to dict for the UI
    config_dict = {
        'target_size_kb': cfg.target_size_kb,
        'aws_profile': cfg.aws_profile,
        'bucket': cfg.bucket
    }

    processing_config = show_processing_config(selected_images, config_dict)

    if processing_config is None:
        # User cancelled or went back
        print("\nProcessing configuration cancelled")
        return 1

    # Use processing_config later in the workflow
    # processing_config contains:
    # {
    #     'resize': True/False,
    #     'target_size_kb': int,
    #     'preserve_exif': True/False
    # }

except KeyboardInterrupt:
    print("\nCancelled by user")
    return 1

# Continue with existing workflow (display selected images, etc.)
```

## Return Values

- **Success (Enter pressed)**: Returns a dict with processing options:
  ```python
  {
      'resize': True/False,
      'target_size_kb': int from config,
      'preserve_exif': True/False
  }
  ```

- **Cancel (q/Esc pressed)**: Returns `None`
- **Back (b pressed)**: Returns `None`
- **Keyboard Interrupt (Ctrl+C)**: Raises `KeyboardInterrupt`

## UI Features

1. **Header**: Shows number of locked images
2. **Options Table**:
   - Resize images (with target size from config)
   - Preserve EXIF data (camera, date, GPS)
3. **Navigation**: Arrow keys to move between options
4. **Toggle**: Spacebar to toggle checkboxes
5. **Actions**:
   - Enter: Confirm and proceed
   - b: Go back to image selection
   - q/Esc: Cancel operation
6. **Color Coding**: Selected option highlighted in cyan

## Test Coverage

See `/Users/kurtis/tinker/photo-terminal/tests/test_processing_config.py` for comprehensive test suite covering:
- Basic structure validation
- Confirm action
- Cancel action
- Back action
- Config value propagation
- Option toggling

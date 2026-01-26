# Two-Pane TUI Implementation

## Overview

Implemented an interactive two-pane TUI for image selection with live viu preview, following the requirements from SPEC.md step 4.

## Files Created

### `/Users/kurtis/tinker/photo-terminal/tui.py`
Main TUI module with the following components:

- **`check_viu_availability()`**: Checks if viu is installed on the system
- **`fail_viu_not_found()`**: Fail-fast with installation instructions if viu not found
- **`get_viu_preview()`**: Generates viu preview output for an image
- **`ImageSelector`**: Main TUI class with two-pane layout
- **`select_images()`**: Public API for image selection

### `/Users/kurtis/tinker/photo-terminal/test_tui.py`
Comprehensive test suite with 24 tests covering:
- viu availability checks
- viu preview generation (success, failure, timeout, exceptions)
- ImageSelector initialization and navigation
- Selection toggling and retrieval
- Panel creation
- User cancellation and keyboard interrupts
- Navigation boundary conditions

## Integration

### Updated Files

**`photo_upload.py`**:
- Imported `select_images` from tui module
- Calls `select_images()` after folder scanning
- Displays count of selected images
- Handles SystemExit on user cancellation

**`test_photo_upload.py`** and **`test_integration.py`**:
- Added mocks for `check_viu_availability` and `ImageSelector.run`
- All existing tests updated to work with TUI integration

## Features Implemented

### Two-Pane Layout
- Left pane: File list with checkboxes (40% width)
- Right pane: Live viu preview (60% width)
- Responsive to terminal size

### Keyboard Controls
- **↑/↓ Arrow keys**: Navigate through file list
- **Spacebar**: Toggle selection (checkbox)
- **Enter**: Confirm selection and proceed
- **q or Escape**: Cancel and exit
- **Ctrl+C**: Interrupt and exit

### Visual Feedback
- Checkboxes: `[ ]` unchecked, `[✓]` checked
- Current selection highlighted in cyan with `►` indicator
- Selection counter in panel title: "Images (2/5 selected)"
- Control hints displayed at bottom of file list

### viu Integration
- Hard requirement: Checks for viu on startup
- Fail-fast with clear installation instructions
- Calls viu with appropriate flags:
  - `-w`: width in columns
  - `-h`: height in rows
  - `-t`: transparent background
- 5-second timeout for preview rendering
- Graceful error messages for rendering failures

### Error Handling
- viu not found: Clear error with install instructions
- Empty image list: Fail with error message
- No images selected: Exit with message
- User cancellation: Clean exit via SystemExit(1)
- Keyboard interrupt (Ctrl+C): Handled gracefully

## Testing

All 59 tests pass, including:
- 24 TUI-specific tests
- 35 existing tests (updated with mocks)

Test coverage includes:
- Mock viu availability checks
- Navigation and selection logic
- Cancellation behavior
- viu command construction
- Integration with main CLI

## Usage

```python
from tui import select_images
from scanner import scan_folder

# Scan folder for valid images
valid_images = scan_folder("/path/to/images")

# Show interactive TUI
selected_images = select_images(valid_images)

# Returns list of selected Path objects
print(f"Selected {len(selected_images)} images")
```

## Implementation Notes

### Technology Choice
Used `rich` library (already in requirements.txt):
- Lightweight and well-suited for terminal UI
- Provides Layout, Panel, Table, and Live rendering
- Better than `textual` for this use case (simpler, more direct control)

### Terminal Compatibility
- Requires terminal with 256+ colors
- Raw mode terminal input for key capture
- Proper terminal settings restoration on exit
- Works with standard Unix terminals (macOS, Linux)

### Python 3.8+ Compatibility
- Type hints using `typing.List` and `typing.Optional`
- No Python 3.9+ features used
- Compatible with project requirements

### Fail-Fast Philosophy
- Pre-validates viu availability before showing UI
- Exits immediately on user cancellation
- No retry logic or graceful degradation
- Clear error messages with actionable instructions

## Next Steps

As noted in photo_upload.py, the next task is:
- Task #5: Implement interactive S3 folder browser

The TUI module can be extended or used as a reference for the S3 folder browser interface.

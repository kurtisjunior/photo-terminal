# Processing Configuration UI - Task #17

## Overview

The processing configuration UI is displayed after the user presses 'n' in the image selection stage. It allows users to configure how their images will be processed before upload.

## Visual Layout

```
┌─────────────────────────────────────────────────────────────┐
│ Processing Configuration                                    │
│ Configure processing for 5 locked image(s)                  │
└─────────────────────────────────────────────────────────────┘

┌─ Processing Options ─────────────────────────────────────────┐
│                                                               │
│     Option                Description                  Value │
│                                                               │
│  ►  Resize images         Optimize to ~400KB           [x]   │
│     Preserve EXIF data    Keep camera, date, GPS info  [x]   │
│                                                               │
└───────────────────────────────────────────────────────────────┘

↑/↓: Navigate  Space: Toggle  Enter: Confirm  b: Go Back  q/Esc: Cancel
```

## Features

### 1. Header Panel
- Title: "Processing Configuration"
- Shows count of locked images from previous stage

### 2. Options Table
Two configuration options with checkboxes:

#### Resize Images
- **Default**: Enabled `[x]`
- **Description**: Shows target size from config (e.g., "Optimize to ~400KB")
- **Effect**: When enabled, images are optimized to target file size

#### Preserve EXIF Data
- **Default**: Enabled `[x]`
- **Description**: "Keep camera, date, GPS info"
- **Effect**: When enabled, preserves camera metadata during processing

### 3. Navigation
- **Arrow Up/Down**: Move between options
- **Current option**: Highlighted in cyan with `►` indicator
- **Color coding**: Selected options shown in bold cyan

### 4. Controls
- **Space**: Toggle checkbox for current option
- **Enter**: Confirm selections and proceed to next stage
- **b**: Go back to image selection stage
- **q/Esc**: Cancel entire operation

## Technical Details

### Function Location
`/Users/kurtis/tinker/photo-terminal/photo_terminal/tui.py`

### Function Signature
```python
def show_processing_config(locked_images: List[Path], config: dict) -> dict:
    """Show processing configuration screen for locked images.

    Args:
        locked_images: List of selected image paths
        config: Configuration dict from ~/.photo-uploader.yaml

    Returns:
        Processing configuration dict with user's choices
    """
```

### Input
- `locked_images`: List of Path objects for selected images
- `config`: Dict with at least `target_size_kb` key

### Output

**On confirmation (Enter):**
```python
{
    'resize': True,              # User's choice
    'target_size_kb': 400,       # From config
    'preserve_exif': True        # User's choice
}
```

**On cancel/back (q, Esc, b):**
```python
None
```

### Error Handling
- **KeyboardInterrupt (Ctrl+C)**: Raises KeyboardInterrupt (caught by caller)
- **Terminal restore**: Always restores cursor and terminal settings in finally block

## Implementation Details

### Rich Components Used
- `Console`: Main console for rendering
- `Panel`: Container for header and options table
- `Table`: Structured display of options
- `Text`: Styled text elements with color coding

### Terminal Handling
- Uses `tty` and `termios` for raw terminal mode
- Hides cursor during interaction
- Restores terminal state on exit (success or failure)

### State Management
- Internal `options` dict tracks checkbox states
- `current_option` index tracks highlighted row
- No persistence between sessions

## Integration Flow

```
Image Selection (TUI)
         |
         | User presses 'n'
         |
         v
Processing Config (This UI)  <--- Task #17
         |
         | User presses Enter
         |
         v
S3 Folder Browser
         |
         v
Confirmation
         |
         v
Processing & Upload
```

## Testing

Test suite location: `/Users/kurtis/tinker/photo-terminal/tests/test_processing_config.py`

Coverage:
- ✅ Function signature validation
- ✅ Confirm action returns valid dict
- ✅ Cancel action returns None
- ✅ Back action returns None
- ✅ Config values propagated correctly
- ✅ Option toggling with spacebar

Run tests:
```bash
python -m pytest tests/test_processing_config.py -v
```

## Future Enhancements

Potential additions (not in current scope):
- Format conversion options (JPEG, PNG, WEBP)
- Quality presets (high, medium, low)
- Custom EXIF field selection
- Watermark options
- Batch rename patterns

# Bug Fixes Summary - Photo Terminal TUI

**Date:** 2026-01-27
**Test Results:** 286/286 tests passing
**Primary File Modified:** `photo_terminal/tui.py`

---

## Executive Summary

Four critical bugs in the TUI image preview system were identified and fixed to improve code quality, debugging capability, terminal compatibility, and user experience. These fixes addressed violations of project requirements (AGENT.md), hardcoded dimensions causing poor terminal responsiveness, hidden error messages hampering debugging, and visual flicker during navigation.

### Why These Bugs Mattered

1. **Fail-fast philosophy violation** - The viu fallback contradicted the project's core requirement to "fail fast" rather than silently degrade functionality
2. **Poor terminal responsiveness** - Hardcoded dimensions (100x50) didn't adapt to actual terminal size, causing overflow and poor UX
3. **Hidden debugging information** - stderr being discarded to /dev/null made it impossible to diagnose viu failures
4. **Degraded user experience** - Full screen clears on every keystroke caused visible flicker and made navigation feel sluggish

---

## Bug Fixes

### Task #15: Fixed AGENT.md Violation - Removed viu Fallback

**What was wrong:**

The code contained a graceful fallback when viu was not available, printing a warning message and continuing without image preview. This directly violated AGENT.md's core requirement: "viu installed and working (no fallback mode)" and the fail-fast philosophy: "No retry logic on errors."

**Before (lines 486-489):**
```python
# Check viu availability
if not check_viu_availability():
    print("Warning: viu not found. Install with: brew install viu")
    print("Continuing without image preview...")
    import time
    time.sleep(2)
```

**After (lines 486-487):**
```python
# Check viu availability
if not check_viu_availability():
    fail_viu_not_found()
```

**Why it mattered:**

This fallback created a degraded experience that silently continued, violating the project's explicit requirement to fail fast with clear error messages. Users might not realize viu was missing and would struggle with a broken TUI.

**How it was fixed:**

- Removed the graceful fallback logic
- Changed to call `fail_viu_not_found()` which prints clear installation instructions and exits with code 1
- This ensures users immediately know viu is required and how to install it
- Aligns with AGENT.md: "viu availability on startup" pre-flight check requirement

---

### Task #16: Fixed Hardcoded Dimensions - Responsive Terminal Sizing

**What was wrong:**

Image preview dimensions were hardcoded to 100x50 characters, which is enormous for most terminals. On a typical 120x40 terminal, this would cause:
- Horizontal overflow (100 columns when only ~58 are available)
- Vertical overflow (50 lines when only ~35 are available)
- Poor layout that obscured the file list

**Before (lines 309-313):**
```python
# Fixed dimensions
file_list_column = 1   # Start file list at column 1 (left)
image_column = 70      # Start image at column 70 (right)
image_width = 100      # Large width - blocks are inherently low-res
image_height = 50      # Large height - blocks are inherently low-res
```

**After (lines 317-324):**
```python
# Calculate dimensions dynamically based on terminal size
terminal_size = os.get_terminal_size()
file_list_column = 1   # Start file list at column 1 (left)
file_list_width = 55
image_column = file_list_width + 5  # Start image after file list with spacing
image_width = max(20, min(terminal_size.columns - image_column - 2, 60))
image_height = max(10, min(terminal_size.lines - 5, 35))
```

**Why it mattered:**

Hardcoded dimensions made the TUI unusable on smaller terminals and wasteful on larger ones. The image would overflow, overlap with file list, or get clipped by the terminal edges. Users couldn't see both panels properly.

**How it was fixed:**

- Added dynamic terminal size detection using `os.get_terminal_size()`
- Image dimensions now adapt to available space after accounting for file list (55 columns)
- Added safety constraints: minimum 20x10 to prevent tiny images, maximum 60x35 to prevent overwhelming displays
- Maintains 5-column spacing between file list and image for clean layout
- On a 120x40 terminal: file list gets 55 columns, image gets ~58x35 (vs hardcoded 100x50 overflow)

---

### Task #17: Fixed stderr Handling - Visible viu Error Messages

**What was wrong:**

In the graphics protocol rendering path (`render_with_graphics_protocol()`), stderr from viu was being discarded to `/dev/null`. When viu failed (wrong protocol, missing file, etc.), errors were silently swallowed, making debugging impossible.

**Before (lines 423-428):**
```python
try:
    subprocess.run(
        ["viu", "-w", str(image_width), "-h", str(image_height), str(current_image)],
        stdout=sys.stdout,  # Direct stream
        stderr=subprocess.DEVNULL,  # Errors discarded!
        timeout=5
    )
```

**After (lines 423-432):**
```python
try:
    result = subprocess.run(
        ["viu", "-w", str(image_width), "-h", str(image_height), str(current_image)],
        stdout=sys.stdout,  # Direct stream
        stderr=subprocess.PIPE,  # Capture errors
        timeout=5
    )
    if result.returncode != 0 and result.stderr:
        error_msg = result.stderr.decode('utf-8', errors='replace').strip()
        sys.stdout.write(f"\n[Preview error: {error_msg}]\n")
        sys.stdout.flush()
```

**Why it mattered:**

Debugging terminal graphics protocol issues was impossible. When testing different terminals (iTerm2, Kitty, Ghostty) or when viu encountered problems, users saw nothing - just a blank space where the image should be. This violated the fail-fast philosophy and made troubleshooting extremely difficult.

**How it was fixed:**

- Changed `stderr=subprocess.DEVNULL` to `stderr=subprocess.PIPE`
- Captured the subprocess result to check return code
- If viu fails (returncode != 0), decode and display the error message
- Error messages are now visible in the TUI for immediate debugging
- Maintains timeout and exception handling for robustness

---

### Task #19: Applied Anti-Flicker Optimization to Block Renderer

**What was wrong:**

Every time the user pressed an arrow key to navigate images, the entire screen was cleared and redrawn from scratch. This caused visible flicker - the file list and image would disappear momentarily before reappearing. Navigation felt sluggish and jarring.

**Before (lines 304-305):**
```python
def render_with_blocks(self, full_render: bool = True):
    """Render the TUI using block mode..."""
    # Clear screen and move to top
    sys.stdout.write('\033[2J\033[H')  # Always full clear!
    sys.stdout.flush()
```

**After (lines 305-313):**
```python
def render_with_blocks(self, full_render: bool = True):
    """Render the TUI using block mode..."""
    # Anti-flicker optimization: only clear screen on first render
    if self._first_render:
        # First render: Clear entire screen
        sys.stdout.write('\033[2J\033[H')
        self._first_render = False
    else:
        # Subsequent renders: Move cursor to home without clearing
        sys.stdout.write('\033[H')
    sys.stdout.flush()
```

**Why it mattered:**

The constant flickering degraded the user experience significantly. When rapidly navigating through images (holding down arrow key), the screen would flash repeatedly, making it hard to see the content and causing eye strain. This is a common terminal UI anti-pattern.

**How it was fixed:**

- Added `_first_render` flag to `ImageSelector.__init__()` (initialized to `True`)
- On first render: perform full screen clear (`\033[2J\033[H`)
- On subsequent renders: only move cursor to home position (`\033[H`) without clearing
- Content overwrites old content in-place rather than clearing then redrawing
- Reduces flicker while maintaining correct display updates
- This optimization was already implemented in `render_with_graphics_protocol()` and is now consistent across both renderers

---

## Test Results

All 286 tests pass after these fixes:

```
============================= 286 passed in 16.07s =============================
```

### Test Coverage

- **TUI tests:** 46 tests covering viu availability, preview generation, navigation, selection, rendering dispatch, and terminal capability detection
- **Scanner tests:** 24 tests for image format validation and folder scanning
- **Uploader tests:** 32 tests for S3 uploads, progress display, and error handling
- **Config tests:** 10 tests for YAML configuration and CLI overrides
- **Optimizer tests:** 31 tests for JPEG optimization and EXIF preservation
- **Summary tests:** 12 tests for completion display formatting
- And more covering integration scenarios

---

## Files Modified

### `photo_terminal/tui.py`

**Lines Modified:**

1. **Lines 305-313** - Anti-flicker optimization in `render_with_blocks()`
   - Added conditional screen clearing logic
   - Full clear only on first render, cursor repositioning for subsequent renders

2. **Lines 317-324** - Dynamic terminal sizing in `render_with_blocks()`
   - Replaced hardcoded dimensions (100x50) with responsive calculation
   - Added `os.get_terminal_size()` detection
   - Implemented min/max constraints for safety

3. **Lines 423-432** - stderr handling in `render_with_graphics_protocol()`
   - Changed `stderr=subprocess.DEVNULL` to `stderr=subprocess.PIPE`
   - Added error message display logic
   - Captures and shows viu failures for debugging

4. **Lines 486-487** - viu availability check in `run()`
   - Removed fallback warning + sleep logic
   - Changed to strict `fail_viu_not_found()` call
   - Enforces AGENT.md fail-fast requirement

---

## Technical Details

### Terminal Size Detection

Uses Python's `os.get_terminal_size()` which returns a named tuple with `.columns` and `.lines` attributes. This works reliably across POSIX systems and provides accurate dimensions for the current terminal window.

### ANSI Escape Codes Used

- `\033[2J` - Clear entire screen
- `\033[H` - Move cursor to home position (1,1)
- `\033[{row};{col}H` - Move cursor to specific row/column

### Flicker Reduction Strategy

The anti-flicker optimization uses a common pattern in terminal UIs:
1. First render: establish the full screen layout
2. Subsequent renders: overwrite content in-place
3. This works because terminal content is persistent until explicitly cleared or overwritten

### Error Message Format

Error messages from viu are decoded with `errors='replace'` to handle any non-UTF-8 bytes gracefully, stripped of whitespace, and displayed in a user-friendly format: `[Preview error: {message}]`

---

## Before and After Comparison

### Behavior Before Fixes

1. **Missing viu:** Printed warning, waited 2 seconds, continued with broken TUI
2. **Terminal sizing:** Used 100x50 regardless of terminal size (overflow/clipping issues)
3. **viu errors:** Silently swallowed, blank preview space with no explanation
4. **Navigation flicker:** Full screen flash on every arrow key press

### Behavior After Fixes

1. **Missing viu:** Immediately exits with code 1, shows installation instructions
2. **Terminal sizing:** Adapts to actual terminal size (e.g., 58x35 on 120x40 terminal)
3. **viu errors:** Displays error message: "[Preview error: unsupported protocol]"
4. **Navigation flicker:** Smooth in-place updates, no visible flashing

---

## Verification Steps

To verify these fixes:

1. **Test viu requirement:**
   ```bash
   # Temporarily rename viu to make it unavailable
   which viu  # Note the location
   sudo mv /opt/homebrew/bin/viu /opt/homebrew/bin/viu.bak
   python -m photo_terminal ~/Pictures
   # Should exit immediately with installation instructions
   sudo mv /opt/homebrew/bin/viu.bak /opt/homebrew/bin/viu
   ```

2. **Test terminal sizing:**
   ```bash
   # Resize terminal to 120x40, then 80x24, then 200x60
   python -m photo_terminal ~/Pictures
   # Image should adapt to available space in each case
   ```

3. **Test error visibility:**
   ```bash
   # Try with an invalid image path or corrupted file
   # Should see "[Preview error: ...]" instead of blank space
   ```

4. **Test flicker reduction:**
   ```bash
   python -m photo_terminal ~/Pictures
   # Hold down arrow key and navigate rapidly
   # Should see smooth transitions, not screen flashing
   ```

---

## Impact Assessment

### Code Quality
- **Improved:** Removed fallback logic that violated project requirements
- **Improved:** Made dimensions adaptive instead of hardcoded magic numbers
- **Improved:** Made error handling visible for debugging

### User Experience
- **Improved:** Immediate failure feedback when viu is missing
- **Improved:** Better layout on all terminal sizes
- **Improved:** Clear error messages when preview fails
- **Improved:** Smooth navigation without flicker

### Maintainability
- **Improved:** Code now matches AGENT.md requirements exactly
- **Improved:** Dynamic sizing makes code robust to different terminals
- **Improved:** Visible errors make debugging easier for future development

---

## Related Documentation

- **AGENT.md** - Project requirements (fail-fast philosophy, viu requirement)
- **bug-fixes.md** - Original bug investigation and fix planning
- **hd-preview-feature.md** - Future enhancement for graphics protocol support
- **SPEC.md** - Complete project specification

---

## Notes

- The `_first_render` flag is initialized in `ImageSelector.__init__()` and tracked per instance
- Dynamic sizing respects the existing 55-column file list width for consistent layout
- Error handling maintains 5-second timeout to prevent hanging on slow operations
- All fixes maintain backward compatibility with existing tests (286/286 passing)

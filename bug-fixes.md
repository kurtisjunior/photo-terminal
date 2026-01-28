# Fix TUI Image Preview Issues

## Problem Statement

Three issues with the current TUI image preview:

1. **Photos are too big** - Current dimensions (100x50) take up too much screen space
2. **Photos are very pixelated** - Using block mode (`-b`) produces low-resolution output
3. **Navigation disappears during updates** - Full screen clear causes flicker when switching images

## Root Cause Analysis

### Issue 1: Image Size
- **Location:** `photo_terminal/tui.py:212-213`
- **Current code:**
  ```python
  image_width = 100      # Large width - blocks are inherently low-res
  image_height = 50      # Large height - blocks are inherently low-res
  ```
- **Problem:** Hardcoded dimensions are too large for typical terminal windows

### Issue 2: Pixelation
- **Location:** `photo_terminal/tui.py:221-226`
- **Current code:**
  ```python
  result = subprocess.run(
      ["viu", "-b", "-w", str(image_width), "-h", str(image_height), str(current_image)],
      ...
  )
  ```
- **Problem:** The `-b` (blocks) flag forces low-resolution Unicode block rendering.
- **Evidence in repo:** `render_with_preview()` decodes stdout and `splitlines()` (`photo_terminal/tui.py:229`), which assumes line-based block output. This makes block mode the only confirmed-compatible rendering path in the current implementation.
- **Note:** There is no repo evidence of the terminal in use or that a graphics protocol path will work end-to-end with the current line-splitting renderer.

### Issue 3: Navigation Flicker
- **Location:** `photo_terminal/tui.py:202-204, 333`
- **Current code:**
  ```python
  # Clear entire screen
  sys.stdout.write('\033[2J\033[H')
  sys.stdout.flush()

  # ... later, after every keystroke ...
  self.render_with_preview()  # Full re-render
  ```
- **Problem:** Entire screen is cleared on every navigation event, causing the file list to disappear momentarily

## Solution Design

### Fix 1: Reduce Image Dimensions

**Change image size from 100x50 to responsive dimensions:**

```python
# Calculate responsive dimensions based on terminal size
terminal_size = os.get_terminal_size()
terminal_width = terminal_size.columns
terminal_height = terminal_size.lines

# Keep file list width aligned with the existing render width (55 cols)
# Evidence: file list is rendered via Console(width=55) in photo_terminal/tui.py:235
file_list_width = 55
image_start_column = file_list_width + 5  # 5-char gap

# Clamp to avoid negative or tiny sizes on small terminals
image_width = max(20, min(terminal_width - image_start_column - 2, 60))
image_height = max(10, min(terminal_height - 5, 35))
```

**Specific dimensions for typical terminal (120x40):**
- File list: 55 columns
- Image: ~58 columns x 35 rows (much smaller than current 100x50)

### Fix 2: Be Explicit About Rendering Mode

**What the code actually supports today**
- The renderer captures `viu` output and splits it into lines (`photo_terminal/tui.py:229`). This is compatible with block output but may not work with graphics-protocol output (which is not line-based).
- Tests currently assert `-b` is used in `get_viu_preview()` (`tests/test_tui.py:61-83`).

**Corrected guidance**
- **Do not remove `-b` by default** unless you also change the rendering path to stream `viu` output directly to the terminal (no `capture_output`, no `splitlines`).
- If you want to experiment with graphics protocols, add an explicit flag/config (e.g., `--viu-protocol`) and update the renderer + tests accordingly.

**Documentation updates (accurate for current code)**
- Keep the comment that block mode is forced.
- If protocol support is added later, update the comment and the renderer together.

### Fix 3: Reduce Flicker Without Breaking Navigation

**Current flow:**
```
Keystroke → Clear entire screen → Re-render file list → Re-render image → Flush
```

**New flow (corrected):**
```
Keystroke → Clear image area → Re-render file list (highlight moves) → Re-render image → Flush
```

**Implementation strategy:**

1. **First render:** Draw both panes (initial display)
2. **On navigation:** Redraw file list (so the highlight moves) and redraw the image pane
3. **On selection toggle:** Redraw file list; image can be re-rendered for simplicity

**Code changes:**

```python
def render_with_preview(self, full_render=True):
    """Render the TUI with side-by-side layout.

    Args:
        full_render: If True, clear screen and render both panes.
                    If False, skip full-screen clear but still re-render both panes.
    """
    if full_render:
        # Clear entire screen and render both panes
        sys.stdout.write('\033[2J\033[H')
    else:
        # Clear only the image area to reduce flicker
        self._clear_image_area(image_column, image_width, image_height)

    # Always render the file list on navigation so the highlight moves
    self._render_file_list()
    self._render_image_preview()

    sys.stdout.flush()

def _clear_image_area(self, image_column: int, image_width: int, image_height: int):
    """Clear only the image preview area without touching file list."""
    for row in range(1, image_height + 2):  # +2 for panel borders
        sys.stdout.write(f'\033[{row};{image_column}H')
        sys.stdout.write(' ' * (image_width + 4))  # Clear with spaces

def _render_file_list(self):
    """Render just the file list panel."""
    # Move to column 1, render file list panel
    # (extract from current render_with_preview)

def _render_image_preview(self):
    """Render just the image preview."""
    # Run viu, position at image_column
    # (extract from current render_with_preview)
```

**Update navigation handlers:**

```python
elif arrow == 'A':  # Up arrow
    self.move_up()
    self.render_with_preview(full_render=False)  # Image + list (highlight)

elif arrow == 'B':  # Down arrow
    self.move_down()
    self.render_with_preview(full_render=False)  # Image + list (highlight)

elif char == ' ':  # Spacebar (toggle selection)
    self.toggle_selection()
    self.render_with_preview(full_render=True)  # Full re-render (checkbox changed)
```

## Implementation Steps

### Step 1: Add Dynamic Terminal Size Detection
**File:** `photo_terminal/tui.py`

1. Import `os` (already imported)
2. In `render_with_preview()`, replace hardcoded dimensions (lines 209-213) with:
   ```python
   # Get terminal dimensions dynamically
   terminal_size = os.get_terminal_size()
   terminal_width = terminal_size.columns
   terminal_height = terminal_size.lines

   # Calculate responsive layout
   file_list_column = 1
   file_list_width = 55
   image_column = file_list_width + 5
   image_width = max(20, min(terminal_width - image_column - 2, 60))  # Max 60 cols
   image_height = max(10, min(terminal_height - 5, 35))  # Max 35 rows
   ```

### Step 2: Keep Block Mode Unless the Renderer Changes
**File:** `photo_terminal/tui.py`

1. **Line 221-226:** Keep `-b` in the viu command until the renderer is updated to support non-line-based output.
2. **Lines 215-220:** Keep the comment that blocks are forced; if protocol support is added later, update this comment alongside the renderer.
3. **Lines 67-70 in get_viu_preview():** Keep the comment describing block output (matches current behavior and tests).

### Step 3: Implement Selective Re-rendering
**File:** `photo_terminal/tui.py`

1. **Refactor render_with_preview() into three methods:**

   a. Add helper method to clear image area only:
   ```python
   def _clear_image_area(self, image_column: int, image_width: int, image_height: int) -> None:
       """Clear only the image preview area."""
       for row in range(1, image_height + 2):
           sys.stdout.write(f'\033[{row};{image_column}H')
           sys.stdout.write(' ' * (image_width + 4))
   ```

   b. Keep render_with_preview() but add parameter:
   ```python
   def render_with_preview(self, full_render: bool = True):
       """Render the TUI with side-by-side layout.

       Args:
           full_render: If True, clear screen and render both panes.
                       If False, skip full-screen clear but still redraw both panes.
       """
   ```

   c. Implement conditional rendering logic:
   ```python
   if full_render:
       # Clear entire screen
       sys.stdout.write('\033[2J\033[H')
       sys.stdout.flush()
   else:
       # Only clear image area
       self._clear_image_area(image_column, image_width, image_height)

   # Get current image (always needed)
   current_image = self.images[self.current_index]

   # Run viu to get image preview
   # ... (existing viu subprocess code)

   # Render file list (highlight changes on navigation)
   # ... (existing file list rendering code)

   # Always render image preview
   # ... (existing image positioning code)

   sys.stdout.flush()
   ```

2. **Update main event loop (lines 293-333):**
   ```python
   # Initial render - full
   self.render_with_preview(full_render=True)

   while True:
       char = sys.stdin.read(1)

       if char == '\x1b':  # ESC
           next_char = sys.stdin.read(1)
           if next_char == '[':
               arrow = sys.stdin.read(1)
               if arrow == 'A':  # Up arrow
                   self.move_up()
                   self.render_with_preview(full_render=False)  # Image + list
               elif arrow == 'B':  # Down arrow
                   self.move_down()
                   self.render_with_preview(full_render=False)  # Image + list

       elif char == ' ':  # Spacebar - checkbox changed
           self.toggle_selection()
           self.render_with_preview(full_render=True)  # Full re-render

       # ... rest of handlers
   ```

### Step 4: Keep get_viu_preview() Consistent With Block Rendering
**File:** `photo_terminal/tui.py`

`get_viu_preview()` currently uses `-b` and tests assert that behavior. Only remove `-b` if the renderer is redesigned and tests are updated accordingly.

### Step 5: Update Tests (Only If Rendering Mode Changes)
**File:** `tests/test_tui.py`

1. **If `-b` is removed intentionally,** update the assertions to match the new behavior. Today the tests explicitly expect `-b` to be present.

2. Add test for selective re-rendering:
   ```python
   def test_render_with_preview_selective(self, sample_images):
       """Test that selective rendering only clears image area."""
       selector = ImageSelector(sample_images)

       # Mock subprocess to avoid actual viu calls
       with patch('photo_terminal.tui.subprocess.run'):
           with patch('photo_terminal.tui.check_viu_availability', return_value=True):
               # Full render should clear entire screen
               with patch('sys.stdout.write') as mock_write:
                   selector.render_with_preview(full_render=True)
                   # Check that full clear was called
                   calls = [str(c) for c in mock_write.call_args_list]
                   assert any('\033[2J\033[H' in str(c) for c in calls)

               # Selective render should NOT clear entire screen
               with patch('sys.stdout.write') as mock_write:
                   selector.render_with_preview(full_render=False)
                   # Check that full clear was NOT called
                   calls = [str(c) for c in mock_write.call_args_list]
                   assert not any('\033[2J\033[H' in str(c) for c in calls)
   ```

## Critical Files to Modify

1. **`photo_terminal/tui.py`** - Main implementation (lines 200-254, 67-99)
   - Modify `render_with_preview()` method
   - Add `_clear_image_area()` helper
   - Keep `-b` unless the renderer changes to support protocol output
   - Modify event loop to use selective rendering

2. **`tests/test_tui.py`** - Update test assertions
   - Add selective rendering test

## Expected Results

### Before (Current State):
- **Size:** Image takes 100x50 characters (huge)
- **Quality:** Pixelated Unicode blocks (▄ characters)
- **Flicker:** Entire screen clears and redraws on each arrow key press

### After (Fixed):
- **Size:** Image takes ~58x35 characters (fits better in typical 120-column terminal)
- **Quality:** Still block-rendered unless the renderer is upgraded for graphics protocols
- **Flicker:** Reduced (no full-screen clear), while navigation highlight still updates

## Verification Steps

1. **Test with real images:**
   ```bash
   cd /Users/kurtis/tinker/photo-terminal
   PHOTO_TERMINAL_DEBUG=1 python -m photo_terminal ~/Desktop/new-post/Oct
   ```

2. **Check image quality:**
   - With block mode, expect pixelation (this is a known limitation)
   - If you implement protocol rendering later, verify clarity then

3. **Check image size:**
   - Image preview should fit in right pane without overwhelming the screen
   - Should be able to see both file list and image comfortably

4. **Check navigation smoothness:**
   - Press arrow keys to navigate between images
   - File list should remain visible (no flicker)
   - No full-screen clear; list and image update smoothly
   - Checkbox indicators should stay stable

5. **Verify fallback:**
   - Block mode is the default today, so fallback is not in play
   - If protocol rendering is added, verify fallback explicitly

## Risks and Mitigations

### Risk 1: Graphics Protocol Not Working
**Mitigation:** Only attempt protocol rendering if the renderer is updated to support non-line-based output; otherwise stick with `-b`.

### Risk 2: Terminal Too Small
**Mitigation:** Added min/max constraints on dimensions (min 20x10, max 60x35).

### Risk 3: Selective Rendering Causes Artifacts
**Mitigation:** Clear image area with spaces before re-rendering. File list is still re-rendered so the highlight moves.

### Risk 4: Performance
**Mitigation:** Avoiding full-screen clears reduces flicker; perf impact should be comparable to current behavior. viu subprocess still runs per navigation.

## References

- [viu GitHub Repository](https://github.com/atanunq/viu) - Terminal image viewer documentation
- [Terminal Integration | atanunq/viu | DeepWiki](https://deepwiki.com/atanunq/viu/5-terminal-integration) - Graphics protocol support details
- [viu command examples](https://commandmasters.com/commands/viu-common/) - Usage examples and flags

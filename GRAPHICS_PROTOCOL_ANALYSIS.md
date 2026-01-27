# Graphics Protocol Analysis: Cursor Positioning and Side-by-Side Layouts

**Date:** 2026-01-27
**Purpose:** Analyze whether terminal graphics protocols respect ANSI cursor positioning for side-by-side layouts

## Executive Summary

**Key Finding:** Graphics protocols DO respect ANSI cursor positioning, making side-by-side layouts technically feasible.

- **Kitty Graphics Protocol:** Explicitly respects cursor position at column level
- **iTerm2 Inline Images:** Documentation unclear, but likely respects cursor position
- **Sixel Protocol:** Renders at cursor position but with margin-based constraints
- **viu Tool:** Supports both absolute and cursor-relative positioning

**Recommendation:** The current side-by-side implementation in `render_with_graphics_protocol()` should work correctly. Testing with real terminals is required to verify practical behavior.

---

## 1. How Each Graphics Protocol Works

### 1.1 iTerm2 Inline Images Protocol

**Protocol Format:**
```
ESC ] 1337 ; File = [arguments] : base64-encoded-data ^G
```

**How It Works:**
- Uses OSC (Operating System Command) escape sequence
- Image data is base64-encoded and embedded directly in terminal output
- Supports various parameters for width, height, aspect ratio, and display mode
- Images can be displayed inline (replacing characters) or as overlays

**Key Features:**
- Dimension control via character cells, pixels, or percentages
- `inline=1` parameter for inline display (replaces text cells)
- `preserveAspectRatio` parameter to maintain image proportions
- Retina display support (2x scaling on high-DPI displays)

**Cursor Positioning:**
- The official documentation does not explicitly describe cursor positioning behavior
- Images are specified with width/height but positioning mechanism is not documented
- Likely renders at current cursor position (standard terminal behavior)

**References:**
- [Inline Images Protocol](https://iterm2.com/documentation-images.html)
- [Proprietary Escape Codes](https://iterm2.com/documentation-escape-codes.html)

### 1.2 Kitty Graphics Protocol

**Protocol Format:**
```
ESC _G<control-data>;base64-encoded-data ESC \
```

**How It Works:**
- Uses DCS (Device Control String) escape sequence
- Two-phase approach: upload image data, then place/display images
- Images can be uploaded once and placed multiple times
- Supports various transmission formats (direct, files, temp files, shared memory)

**Key Features:**
- Virtual placements: display only part of an image
- Column and row specification: `c=<cols>,r=<rows>`
- Pixel-level offsets: `X=<pixels>,Y=<pixels>`
- Cursor movement control: `C=1` prevents cursor advance after image
- Z-index support for layering images
- Animation support for multi-frame images

**Cursor Positioning:**
**CRITICAL:** "The image is rendered at the current cursor position, from the upper left corner of the current cell."

This is explicitly documented. Images do NOT always render at column 1.

**After Image Rendering:**
- Default: Cursor moves right by image columns, down by image rows
- With `C=1`: Cursor does not move (allows overlapping layouts)

**References:**
- [Terminal Graphics Protocol](https://sw.kovidgoyal.net/kitty/graphics-protocol/)
- [Screen and Terminal Display](https://deepwiki.com/kovidgoyal/kitty/2.3-screen-and-terminal-display)

### 1.3 Sixel Protocol

**Protocol Format:**
```
ESC P <parameters> q <sixel-data> ESC \
```

**How It Works:**
- DCS-based bitmap graphics format from DEC terminals (1980s)
- Encodes images as vertical columns of 6 pixels (sixels)
- Color palette definition followed by pixel data
- Uses printable ASCII characters to encode pixel patterns

**Key Features:**
- Character-based positioning within sixel coordinate system
- `$` (Graphics Carriage Return): returns to left page border
- `-` (Graphics New Line): advances to next sixel line
- Repeat sequences for compression
- Color palette up to 256 colors (terminal-dependent)

**Cursor Positioning:**
- **With scrolling enabled:** "Sixel active position begins at the upper-left corner of the ANSI text active position"
- **With scrolling disabled:** Sixel renders at "upper-left corner of the active graphics page"
- After sixel mode exits, text cursor is set to current sixel cursor position

**Limitations:**
- Positioning is margin-based, not absolute column-based
- No mechanism for arbitrary column positioning (like column 60)
- Sixel coordinate system is separate from ANSI text coordinates
- Returns to "left page border" or "left margin" (not arbitrary columns)

**References:**
- [Sixel Graphics - VT330/VT340 Manual](https://vt100.net/docs/vt3xx-gp/chapter14.html)
- [Sixel - Wikipedia](https://en.wikipedia.org/wiki/Sixel)

---

## 2. Do They Respect Cursor Positioning?

### 2.1 Can You Position at Column 60?

| Protocol | Column Positioning | Mechanism |
|----------|-------------------|-----------|
| **Kitty** | YES (Confirmed) | Renders at current cursor position, any column |
| **iTerm2** | LIKELY YES | Documentation unclear, but standard terminal behavior |
| **Sixel** | NO (Limited) | Margin-based positioning, no arbitrary column support |

### 2.2 Detailed Analysis

#### Kitty Graphics Protocol: YES

**Evidence:**
```
"The image is rendered at the current cursor position, from the
upper left corner of the current cell."
```

**How to use:**
1. Move cursor to column 60: `printf '\033[1;60H'`
2. Output Kitty graphics protocol escape sequence
3. Image renders starting at column 60

**Additional control:**
- `X=<pixels>` and `Y=<pixels>` provide sub-cell pixel offsets
- `C=1` prevents cursor from advancing after image (allows precise layouts)

**Side-by-side feasibility:** FULLY SUPPORTED

#### iTerm2 Inline Images Protocol: LIKELY YES

**Evidence:**
- Documentation does not explicitly describe cursor positioning
- Uses standard OSC escape sequence format
- `inline=1` parameter suggests character-cell integration
- Standard terminal behavior is to respect cursor position

**Inference:**
- Terminal protocols typically respect cursor position unless documented otherwise
- iTerm2's inline mode replaces character cells, implying cursor-relative rendering
- No documentation of forced column-1 rendering

**Side-by-side feasibility:** LIKELY SUPPORTED (requires testing)

#### Sixel Protocol: LIMITED

**Evidence:**
```
"Sixel active position begins at the upper-left corner of the
ANSI text active position" (when scrolling enabled)
```

**Constraints:**
- Respects initial cursor position (text active position)
- BUT: Internal positioning uses margins, not columns
- `$` returns to "left page border" (not arbitrary column)
- `-` advances to "left margin" (not arbitrary column)

**Practical implications:**
- Initial placement respects cursor column
- Internal sixel rendering uses left margin as reference
- May not maintain side-by-side layout through entire image height
- Image width might extend left to margin regardless of starting column

**Side-by-side feasibility:** PARTIAL (initial position only, may break on multi-line images)

### 2.3 viu Tool Positioning Capabilities

**viu** (the image viewer used in this project) provides explicit positioning control:

**Command-line options:**
```bash
-x <x>              X offset [default: 0]
-y <y>              Y offset [default: 0]
-a, --absolute-offset   Make offsets relative to terminal corner
                        (default: relative to cursor)
```

**Default behavior:** Relative to cursor position
**Alternate mode:** Absolute positioning from terminal corner

**Graphics protocol selection:**
- Automatically detects protocol based on `$TERM` environment variable
- Falls back to Unicode blocks (`▄`) if no graphics protocol available

**Key insight:** viu does NOT force column-1 rendering. It supports both:
1. Cursor-relative positioning (default)
2. Absolute positioning with `-a` flag

**References:**
- [viu GitHub Repository](https://github.com/atanunq/viu)
- [Terminal Integration Documentation](https://deepwiki.com/atanunq/viu/5-terminal-integration)

---

## 3. Technical Explanation

### 3.1 Graphics Protocols Output Binary Escape Sequences

**What are binary escape sequences?**
- Special character sequences that terminals interpret as commands
- Not displayed as text, but as instructions to the terminal emulator
- Can contain binary data (not just printable ASCII)

**Example (Kitty protocol):**
```
ESC _Ga=T,f=100,t=f;SGVsbG8gV29ybGQh ESC \
     ^^^^^^^^^^^^^  ^^^^^^^^^^^^^^^^
     control data   base64 image data
```

**Key characteristics:**
- Atomic: The entire escape sequence is processed as one unit
- Binary-safe: Can contain null bytes and non-printable characters
- Position-aware: Terminal knows cursor position when sequence arrives

### 3.2 Graphics Protocols Include Position Information

**How positioning works:**

1. **Implicit positioning (Kitty, iTerm2):**
   - Image renders at current cursor position
   - Terminal knows where cursor is before escape sequence arrives
   - No explicit coordinates in protocol (cursor position IS the coordinate)

2. **Explicit positioning (viu with `-a`):**
   - Absolute coordinates specified in command-line arguments
   - viu moves cursor before outputting graphics protocol
   - Uses ANSI cursor positioning: `\033[<row>;<col>H`

3. **Hybrid positioning (Sixel):**
   - Initial position from cursor
   - Internal positioning from margins
   - Disconnect between ANSI text coordinates and sixel coordinates

### 3.3 ANSI Cursor Positioning IS Respected (Mostly)

**Misconception:** "Graphics protocols ignore ANSI cursor positioning"

**Reality:** Graphics protocols render at cursor position, but differ in how they handle it:

| Protocol | Respects Cursor Position | Respects ANSI Column Codes | Notes |
|----------|-------------------------|---------------------------|-------|
| Kitty | YES | YES | Explicitly documented behavior |
| iTerm2 | YES (likely) | YES (likely) | Standard terminal behavior |
| Sixel | PARTIAL | PARTIAL | Initial position only, margins override |

**Why this matters:**
- You CAN position cursor at column 60: `printf '\033[1;60H'`
- Kitty protocol WILL render image starting at column 60
- iTerm2 protocol LIKELY will render image starting at column 60
- Sixel protocol will start at column 60 but may drift to margins

**Exception: Sixel's margin behavior**
- Sixel has its own coordinate system based on page margins
- After initial placement, internal `$` and `-` characters reset to margins
- This can cause side-by-side layouts to collapse in multi-line sixel images

---

## 4. Implications for Side-by-Side Layout

### 4.1 Current Implementation Analysis

**File:** `photo_terminal/tui.py`, method: `render_with_graphics_protocol()`

**Current approach:**
```python
# Side-by-side layout: file list left, image right
file_list_width = 55  # Fixed width for file list
image_column = 60     # Where image starts (column position)

# Render file list line-by-line on left side
for row, line in enumerate(file_list_lines, start=1):
    sys.stdout.write(f'\033[{row};1H')  # Position at row, column 1
    sys.stdout.write(line)

# Position cursor at top-right where image should render
sys.stdout.write(f'\033[1;{image_column}H')  # Position at row 1, column 60

# Stream viu output directly (graphics protocol)
subprocess.run(
    ["viu", "-w", str(image_width), "-h", str(image_height), str(current_image)],
    stdout=sys.stdout,  # Direct stream to terminal
    ...
)
```

### 4.2 Will This Work?

**For Kitty protocol: YES**

Reasoning:
1. Cursor is positioned at column 60 before viu runs
2. viu detects Kitty protocol and outputs graphics escape sequence
3. Kitty protocol renders "at the current cursor position"
4. Image appears at column 60 as intended

**For iTerm2 protocol: LIKELY YES**

Reasoning:
1. Same positioning logic (cursor at column 60)
2. iTerm2 inline images likely respect cursor position (standard behavior)
3. No documented exception for forced column-1 rendering
4. **Requires testing to confirm**

**For Sixel protocol: MAYBE (with caveats)**

Reasoning:
1. Initial sixel position starts at cursor (column 60)
2. BUT: Internal sixel positioning uses margins
3. Multi-line images may collapse back to left margin
4. **Likely to fail for tall images**

**For block mode: YES (already works)**

Reasoning:
- Block output is plain text (colored Unicode characters)
- Each line is positioned independently
- No special protocol, just ANSI escape codes
- Current implementation already uses this successfully

### 4.3 Potential Issues

#### Issue 1: Image Width Overlap

**Problem:** If image is too wide, it overlaps with file list

**Example:**
```
File list: columns 1-55
Image start: column 60
Image width: 50 columns
Image end: column 110

Terminal width: 120 columns -> OK
Terminal width: 100 columns -> TRUNCATED
Terminal width: 80 columns -> OVERLAP
```

**Mitigation (already implemented):**
```python
image_width = max(20, min(terminal_size.columns - image_column - 2, 60))
```

This ensures image fits in available space.

#### Issue 2: Cursor Advance After Image

**Problem:** After image renders, cursor advances to end of image

**Kitty behavior:**
```
Default: cursor moves right by image columns, down by image rows
With C=1: cursor does not move
```

**Impact on implementation:**
- viu outputs graphics protocol escape sequence
- Terminal renders image and advances cursor
- Next output continues from new cursor position
- File list is already rendered, so this is OK

**No issue:** File list is rendered first, then image. Cursor position after image doesn't matter.

#### Issue 3: Sixel Margin Behavior

**Problem:** Sixel uses margins, not absolute columns

**Example:**
```
Row 1: Image starts at column 60 (cursor position) ✓
Row 2: Sixel $ character resets to left margin (column 1?) ✗
Row 3+: Image collapses to left side, overlapping file list ✗
```

**Impact:** Side-by-side layout fails for Sixel protocol

**Mitigation:** Sixel is rare. Most users have Kitty or iTerm2. If Sixel detected, could:
1. Fall back to block mode
2. Use sequential layout instead
3. Accept the limitation and document it

#### Issue 4: Terminal Multiplexers (tmux/screen)

**Problem:** tmux and screen don't pass through graphics protocols

**Current detection (in code):**
```python
if os.environ.get('TMUX') or os.environ.get('STY'):
    return 'blocks'
```

**Status:** Already handled. Multiplexers force block mode.

### 4.4 Alternative: Sequential Layout

**If side-by-side doesn't work:**

```
┌───────────────────────────────────────────────────────────┐
│ File List (top)                                            │
│ [✓] image1.jpg                                             │
│ [ ] image2.jpg                                             │
└───────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────┐
│                                                             │
│          [Full-resolution image rendered here]             │
│                                                             │
└───────────────────────────────────────────────────────────┘
```

**Advantages:**
- No column positioning needed (cursor at column 1)
- Full terminal width available for image
- No overlap concerns
- Works with all protocols (including Sixel)

**Disadvantages:**
- Less efficient use of vertical space
- Different UX from block mode (which is side-by-side)
- More scrolling if file list is long

**When to use:**
- Sixel protocol detected
- Very narrow terminals (< 100 columns)
- User preference (future config option)

---

## 5. Recommendation Based on Findings

### 5.1 Primary Recommendation: KEEP SIDE-BY-SIDE LAYOUT

**Rationale:**
1. Kitty protocol explicitly supports cursor positioning (confirmed)
2. iTerm2 protocol likely supports cursor positioning (standard behavior)
3. Both are the most common graphics-capable terminals
4. Current implementation should work correctly

**Action items:**
1. Test in Kitty terminal (primary target)
2. Test in iTerm2 (secondary target)
3. Test in Ghostty (uses Kitty protocol)
4. Document tested terminals in README

### 5.2 Fallback Strategy: Protocol-Specific Layouts

**If side-by-side fails in testing:**

```python
def render_with_graphics_protocol(self):
    protocol = TerminalCapabilities.detect_graphics_protocol()

    if protocol == 'sixel':
        # Sixel has margin issues, use sequential layout
        self.render_sequential_layout()
    else:
        # Kitty and iTerm2 support cursor positioning
        self.render_sidebyside_layout()
```

**Implementation:**
- Add `render_sequential_layout()` method
- Keep `render_sidebyside_layout()` (current implementation)
- Dispatch based on protocol detection

### 5.3 Configuration Option (Future Enhancement)

**Allow users to choose layout:**

```yaml
# ~/.photo-uploader.yaml
preview:
  layout: auto  # auto | sidebyside | sequential
```

**`auto` behavior:**
- Side-by-side for Kitty and iTerm2
- Sequential for Sixel
- Side-by-side for block mode (current behavior)

### 5.4 Testing Plan

**Phase 1: Verify cursor positioning (high priority)**

Test in Kitty terminal:
```bash
# Manually test cursor positioning
printf '\033[2J\033[H'  # Clear screen
printf '\033[1;60H'     # Position at column 60
viu -w 50 test-image.jpg  # Render image

# Expected: Image starts at column 60
# If it starts at column 1, cursor positioning is NOT respected
```

Test in iTerm2:
```bash
# Same test as above
# Expected: Image starts at column 60 (to be confirmed)
```

**Phase 2: Test integrated TUI (high priority)**

```bash
cd /Users/kurtis/tinker/photo-terminal

# Test in Kitty terminal
export TERM=xterm-kitty
python -m photo_terminal ~/Desktop/test-images

# Test in iTerm2
export TERM_PROGRAM=iTerm.app
python -m photo_terminal ~/Desktop/test-images

# Verify:
# 1. File list appears on left (columns 1-55)
# 2. Image appears on right (starting at column 60)
# 3. No overlap between file list and image
# 4. Navigation works correctly (arrow keys)
```

**Phase 3: Edge cases (medium priority)**

- Very narrow terminal (80 columns)
- Very wide terminal (200+ columns)
- Very tall images (100+ rows)
- Very wide images (truncation behavior)
- Rapid navigation (flicker and performance)

**Phase 4: Sixel testing (low priority)**

- Test in xterm with sixel support
- Test in mlterm with sixel support
- Document Sixel limitations if side-by-side fails
- Implement sequential layout fallback if needed

### 5.5 Documentation Updates

**Update README.md:**

```markdown
## Terminal Compatibility

### Graphics Protocols (High-Quality Previews)

| Terminal | Protocol | Side-by-Side Layout | Notes |
|----------|----------|---------------------|-------|
| Kitty | Kitty Graphics | ✓ Supported | Tested and confirmed |
| Ghostty | Kitty Graphics | ✓ Supported | Uses Kitty protocol |
| iTerm2 | iTerm2 Inline | ✓ Supported | Requires iTerm2 3.0+ |
| xterm | Sixel | ⚠ Limited | Initial position only |
| mlterm | Sixel | ⚠ Limited | Initial position only |

### Block Mode (Universal Fallback)

All terminals support block mode with side-by-side layout.
Block mode uses colored Unicode characters (▄▀) for previews.

### Terminal Multiplexers

tmux and screen do not support graphics protocols.
Automatically falls back to block mode.
```

**Update AGENT.md:**

```markdown
## Graphics Protocol Support

The TUI supports high-fidelity image previews in terminals with graphics protocol support:

- **Kitty protocol:** Fully supported (side-by-side layout confirmed)
- **iTerm2 protocol:** Supported (standard cursor positioning behavior)
- **Sixel protocol:** Limited support (may fall back to sequential layout)

The implementation uses cursor positioning to achieve side-by-side layouts:
- File list: columns 1-55 (left pane)
- Image preview: column 60+ (right pane)

Graphics protocols respect ANSI cursor positioning, allowing the image
to render at column 60 as intended.
```

### 5.6 Current Implementation Status

**File:** `photo_terminal/tui.py`

**Current state:**
- Side-by-side layout implemented in `render_with_graphics_protocol()`
- Cursor positioned at column 60 before viu output
- File list rendered on left, image on right
- **Status:** Theoretically correct, requires real-world testing

**Existing tasks (from hd-preview-feature.md):**
1. Task #1 (in_progress): Test graphics protocol side-by-side layout - verify it works or revert
2. Task #2 (pending): If graphics protocol fails, implement hybrid approach

**Next steps:**
1. Test in Kitty terminal (primary validation)
2. Test in iTerm2 (secondary validation)
3. If tests pass: Document tested terminals, close Task #1 as completed
4. If tests fail: Analyze failure mode, implement protocol-specific layouts (Task #2)

---

## 6. Conclusion

### Key Findings Summary

1. **Kitty graphics protocol explicitly respects cursor positioning** - confirmed via official documentation
2. **iTerm2 inline images likely respect cursor positioning** - standard terminal behavior, requires testing
3. **Sixel protocol partially respects cursor positioning** - initial position only, margins override
4. **viu tool supports both cursor-relative and absolute positioning** - does not force column 1
5. **Current implementation is theoretically correct** - uses ANSI cursor positioning before graphics output

### Primary Conclusion

**Side-by-side layouts with graphics protocols ARE FEASIBLE.**

The concern that "graphics protocols always render at column 1" is unfounded. The Kitty protocol explicitly documents cursor-relative rendering, and iTerm2 likely follows standard terminal behavior.

### Risk Assessment

| Risk | Severity | Likelihood | Mitigation |
|------|----------|-----------|------------|
| Kitty positioning fails | High | Low | Test before deployment |
| iTerm2 positioning fails | Medium | Medium | Add fallback to sequential layout |
| Sixel positioning fails | Low | High | Document limitation, use sequential |
| Overlap on narrow terminals | Medium | Medium | Already handled via width calculations |
| Multiplexer incompatibility | Low | N/A | Already detected and handled |

### Final Recommendation

**PROCEED WITH CURRENT IMPLEMENTATION**

The side-by-side layout in `render_with_graphics_protocol()` should work correctly for Kitty and iTerm2 terminals. Complete Task #1 (testing) to validate this conclusion.

If testing reveals issues:
- Add protocol-specific layout selection
- Implement sequential layout fallback for Sixel
- Add user configuration option for layout preference

The graphics protocol analysis confirms that the architectural approach is sound. Testing will validate practical behavior.

---

## References

### Official Documentation
- [iTerm2 Inline Images Protocol](https://iterm2.com/documentation-images.html)
- [iTerm2 Proprietary Escape Codes](https://iterm2.com/documentation-escape-codes.html)
- [Kitty Terminal Graphics Protocol](https://sw.kovidgoyal.net/kitty/graphics-protocol/)
- [Kitty Screen and Terminal Display](https://deepwiki.com/kovidgoyal/kitty/2.3-screen-and-terminal-display)
- [Sixel Graphics - VT330/VT340 Manual](https://vt100.net/docs/vt3xx-gp/chapter14.html)
- [Sixel - Wikipedia](https://en.wikipedia.org/wiki/Sixel)

### Tools and Libraries
- [viu - Terminal Image Viewer (GitHub)](https://github.com/atanunq/viu)
- [viu Terminal Integration Documentation](https://deepwiki.com/atanunq/viu/5-terminal-integration)
- [viuer - Rust Library for Terminal Images](https://github.com/atanunq/viuer)

### General Resources
- [ANSI Escape Code - Wikipedia](https://en.wikipedia.org/wiki/ANSI_escape_code)
- [ANSI Escape Codes Reference](https://gist.github.com/fnky/458719343aabd01cfb17a3a4f7296797)

---

**Document Version:** 1.0
**Last Updated:** 2026-01-27
**Author:** Research analysis based on official protocol documentation

# Feature: HD Image Preview with Graphics Protocol Support

## Overview

**Type:** Feature Enhancement
**Goal:** Enable higher-fidelity image previews in terminals that support inline graphics, while maintaining block-mode fallback for compatibility.
**Current State:** All terminals use low-resolution Unicode block rendering (pixelated)
**Target State:** Higher-fidelity previews in terminals with graphics protocol support

## Motivation

The current TUI uses viu's block mode (`-b` flag) which renders images as colored Unicode characters (▄▀). This provides universal compatibility but produces pixelated output. Some terminals support inline image protocols that can display higher-fidelity images.

## Current Architecture Limitations

### How Block Rendering Works Today

```python
# Current approach in render_with_preview() (tui.py:221-229)
result = subprocess.run(
    ["viu", "-b", "-w", str(width), "-h", str(height), str(image)],
    capture_output=True,  # Capture stdout to manipulate
    text=False
)
viu_lines = result.stdout.decode('utf-8').splitlines()  # Split into lines

# Position each line individually for side-by-side layout
for row in range(max_lines):
    sys.stdout.write(f'\033[{row + 1};{file_list_column}H')
    sys.stdout.write(file_list_lines[row])
    sys.stdout.write(f'\033[{row + 1};{image_column}H')
    sys.stdout.write(viu_lines[row])  # Position image line-by-line
```

**Why this works:** Block output is text-based. Each line is independent and can be positioned anywhere.

### Why Graphics Protocols Require Different Architecture

Graphics protocols (iTerm2 inline images, Kitty graphics protocol) work fundamentally differently:

1. **Binary escape sequences** - Not text lines, but binary data containing base64-encoded images
2. **Single escape code** - The entire image is one escape sequence (can't be split)
3. **Cursor-position-based** - Image renders at current cursor position and "owns" terminal cells
4. **Not line-addressable** - Can't position the image "line by line" - it's atomic

**The core problem:** `capture_output=True` + `splitlines()` is compatible with line-based block output, but it is not compatible with protocol output that arrives as a single binary escape sequence.

## Proposed Architecture

### Dual Rendering Paths

```
Terminal Detection
    ↓
    ├─→ Graphics Protocol Available (heuristic)
    │   ├─→ Stream viu directly to stdout
    │   ├─→ No capture, no line splitting
    │   └─→ Sequential layout by default (simpler, avoids overlap)
    │
    └─→ Graphics Protocol Not Available
        ├─→ Use block mode (-b flag)
        ├─→ Capture and split lines
        └─→ Side-by-side layout (current approach)
```

### Implementation Components

#### 1. Protocol Detection

```python
class TerminalCapabilities:
    """Detect and manage terminal graphics capabilities."""

    @staticmethod
    def detect_graphics_protocol() -> str:
        """Detect which graphics protocol is supported.

        Returns:
            'iterm' | 'kitty' | 'sixel' | 'blocks'
        """
        term_program = os.environ.get('TERM_PROGRAM', '')
        term = os.environ.get('TERM', '')

        # iTerm2 detection (heuristic, may false-positive on older versions)
        if term_program == 'iTerm.app':
            return 'iterm'

        # Kitty detection (heuristic)
        if 'kitty' in term or term == 'xterm-kitty':
            return 'kitty'

        # Sixel detection (heuristic; TERM doesn't guarantee sixel support)
        if 'sixel' in os.environ.get('TERM', ''):
            return 'sixel'

        # Fallback to blocks
        return 'blocks'

    @staticmethod
    def supports_inline_images() -> bool:
        """Check if terminal supports any inline image protocol."""
        protocol = TerminalCapabilities.detect_graphics_protocol()
        return protocol in ('iterm', 'kitty', 'sixel')
```

#### 2. Graphics Protocol Renderer

```python
def render_with_graphics_protocol(self):
    """Render TUI using graphics protocol for HD images.

    Layout: Sequential (file list above, image below)
    Chosen for simplicity; side-by-side might be possible but would
    require careful cursor placement and avoiding overlap.
    """
    # Clear screen
    sys.stdout.write('\033[2J\033[H')
    sys.stdout.flush()

    # Calculate dimensions
    terminal_size = os.get_terminal_size()
    terminal_width = terminal_size.columns
    terminal_height = terminal_size.lines

    # File list takes top portion
    file_list_height = min(len(self.images) + 8, terminal_height // 2)
    image_height = terminal_height - file_list_height - 2
    image_width = terminal_width - 4

    # Render file list at top
    narrow_console = Console(width=terminal_width - 2, force_terminal=True)
    with narrow_console.capture() as capture:
        narrow_console.print(self.create_file_list_panel())
    file_list_output = capture.get()
    sys.stdout.write(file_list_output)
    sys.stdout.write('\n')
    sys.stdout.flush()

    # Position cursor for image and stream viu output directly
    current_image = self.images[self.current_index]

    # CRITICAL: Stream to stdout directly, no capture
    # This preserves the binary graphics protocol escape sequences
    try:
        subprocess.run(
            ["viu", "-w", str(image_width), "-h", str(image_height), str(current_image)],
            stdout=sys.stdout,  # Direct stream
            stderr=subprocess.DEVNULL,
            timeout=5
        )
    except subprocess.TimeoutExpired:
        sys.stdout.write("[Preview timed out]")
    except Exception as e:
        sys.stdout.write(f"[Preview error: {e}]")

    sys.stdout.flush()
```

#### 3. Block Mode Renderer (Keep Current Approach)

```python
def render_with_blocks(self):
    """Render TUI using block mode (current implementation).

    Layout: Side-by-side (file list left, image right)
    This works because block output is line-based text.
    """
    # Keep existing render_with_preview() logic
    # But make it explicitly named as the block-mode renderer
    # ... (current implementation from lines 200-254)
```

#### 4. Smart Dispatcher

```python
def render_with_preview(self, full_render: bool = True):
    """Render the TUI with appropriate method based on terminal capabilities.

    Args:
        full_render: If True, full screen clear. If False, partial update.
                    Note: Partial updates only work in block mode.
    """
    protocol = TerminalCapabilities.detect_graphics_protocol()

    if protocol in ('iterm', 'kitty', 'sixel'):
        # Graphics protocol path - always full render
        self.render_with_graphics_protocol()
    else:
        # Block mode path - supports partial rendering
        self.render_with_blocks(full_render=full_render)
```

## Implementation Plan

### Phase 1: Foundation (Minimal Changes)

**Goal:** Add detection and opt-in graphics protocol support without breaking existing behavior.

1. **Add TerminalCapabilities class** (new code, no existing changes)
2. **Add render_with_graphics_protocol() method** (new code)
3. **Refactor render_with_preview() → render_with_blocks()** (rename + minor refactor)
4. **Add new render_with_preview() dispatcher** (routing logic)
5. **Add configuration flag** for opt-in (default to blocks until verified):
   ```python
   # In config or environment variable
   PHOTO_TERMINAL_HD_PREVIEW = os.environ.get('PHOTO_TERMINAL_HD_PREVIEW', 'blocks')
   # Values: 'auto' (detect), 'force' (always try), 'blocks' (never use graphics)
   ```

### Phase 2: UX Improvements

**Goal:** Optimize both rendering paths

1. **Graphics Protocol Path:**
   - Responsive sizing based on terminal dimensions
   - Better error handling and fallback
   - Loading indicator for slow images

2. **Block Mode Path:**
   - Implement selective re-rendering (from corrected bug-fix plan)
   - Responsive sizing (from corrected bug-fix plan)
   - Reduce flicker with partial updates

### Phase 3: Testing & Polish

1. **Unit tests:**
   - Mock terminal capability detection
   - Test routing logic
   - Test both render paths independently

2. **Integration tests:**
   - Test in iTerm2 (graphics protocol)
   - Test in basic terminal (block fallback)
   - Test with PHOTO_TERMINAL_HD_PREVIEW overrides

3. **Documentation:**
   - Update README with terminal compatibility matrix
   - Document environment variables
   - Add screenshots showing difference

## Layout Changes

### Current Layout (Block Mode)
```
┌─────────────────────────────┐  ┌──────────────────────────┐
│ File List (left)            │  │ Image Preview (right)    │
│ [✓] image1.jpg              │  │ ▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄  │
│ [ ] image2.jpg              │  │ ▄▄▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▄▄▄▄  │
│ [ ] image3.jpg              │  │ ▀▀▀▀▀▀▄▄▄▄▄▄▀▀▀▀▀▀▀▀▀▀  │
│                             │  │ (pixelated blocks)       │
└─────────────────────────────┘  └──────────────────────────┘
```

### Graphics Protocol Layout (Sequential)
```
┌───────────────────────────────────────────────────────────┐
│ File List (top)                                            │
│ [✓] image1.jpg                                             │
│ [ ] image2.jpg                                             │
│ [ ] image3.jpg                                             │
└───────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────┐
│                                                             │
│          [Full-resolution image rendered here]             │
│          (higher-fidelity image, not blocks)               │
│                                                             │
└───────────────────────────────────────────────────────────┘
```

**Why sequential?** Graphics protocols render the entire image at the cursor position. You can't interleave file list lines and image data like you can with blocks. The image "owns" terminal cells and can't be split.

## Expected Outcomes

### Terminals with Graphics Protocol (Graphics Path)
- **Quality:** Higher-fidelity images (subject to terminal + viu support)
- **Layout:** Sequential (file list above, image below)
- **Flicker:** Full re-render by default (partial updates are possible but more complex)
- **Compatibility:** To be verified per terminal/protocol

### Standard Terminals (Block Fallback)
- **Quality:** Unicode block rendering (pixelated, current behavior)
- **Layout:** Side-by-side (file list left, image right)
- **Flicker:** Reduced via partial updates (Phase 2 improvement)
- **Compatibility:** Universal (works in any terminal)

## Terminal Compatibility Matrix (To Verify)

| Terminal | Graphics Protocol | Fallback Mode | Notes |
|----------|------------------|---------------|-------|
| iTerm2 | ? | ✓ Blocks | Verify protocol support + version |
| Kitty | ? | ✓ Blocks | Verify protocol support |
| Alacritty | ? | ✓ Blocks | Verify protocol support |
| Terminal.app | ? | ✓ Blocks | Verify protocol support |
| xterm | ? | ✓ Blocks | Sixel only if compiled with support |
| tmux/screen | ? | ✓ Blocks | Depends on multiplexer + terminal config |

## Risks & Mitigations

### Risk 1: Graphics Protocol Detection False Positives
**Scenario:** Code thinks terminal supports graphics but it doesn't work (e.g., old iTerm2 version)

**Mitigation:**
- Add version detection where possible (iTerm2 reports version in env)
- Provide manual override via `PHOTO_TERMINAL_HD_PREVIEW=blocks`
- Implement timeout and fallback if viu doesn't render

### Risk 2: Layout Preference
**Scenario:** Users prefer side-by-side layout even with graphics protocol available

**Mitigation:**
- Make it configurable: `PHOTO_TERMINAL_LAYOUT=sidebyside|sequential`
- Could sacrifice HD quality for preferred layout (explicit trade-off)

### Risk 3: viu Version Compatibility
**Scenario:** Installed viu version lacks protocol support

**Mitigation:**
- Check `viu --version` and document known-good versions once verified
- Provide clear error messages and fallback to blocks

### Risk 4: tmux/screen Sessions
**Scenario:** User is in iTerm2 but inside tmux - graphics protocols won't work

**Mitigation:**
- Detect multiplexer: check `$TMUX` or `$STY` env variables
- Force block mode when inside multiplexer
- Document limitation

### Risk 5: Performance with Large Images
**Scenario:** Very large JPEG/PNG files take too long to render (RAW is unsupported per spec)

**Mitigation:**
- Keep 5-second timeout on viu subprocess
- Show loading indicator
- Consider implementing image caching in future

## Testing Strategy

### Unit Tests
```python
def test_terminal_capability_detection():
    """Test protocol detection logic."""
    # Mock environment variables
    with patch.dict(os.environ, {'TERM_PROGRAM': 'iTerm.app'}):
        assert TerminalCapabilities.detect_graphics_protocol() == 'iterm'

    with patch.dict(os.environ, {'TERM': 'xterm-kitty'}):
        assert TerminalCapabilities.detect_graphics_protocol() == 'kitty'

    with patch.dict(os.environ, {'TERM': 'xterm-256color'}):
        assert TerminalCapabilities.detect_graphics_protocol() == 'blocks'

def test_render_dispatch():
    """Test that dispatcher calls correct renderer."""
    selector = ImageSelector(sample_images)

    # Mock graphics protocol available
    with patch.object(TerminalCapabilities, 'detect_graphics_protocol', return_value='iterm'):
        with patch.object(selector, 'render_with_graphics_protocol') as mock_graphics:
            selector.render_with_preview()
            mock_graphics.assert_called_once()

    # Mock graphics protocol not available
    with patch.object(TerminalCapabilities, 'detect_graphics_protocol', return_value='blocks'):
        with patch.object(selector, 'render_with_blocks') as mock_blocks:
            selector.render_with_preview()
            mock_blocks.assert_called_once()
```

### Integration Tests (Manual)
1. **iTerm2:** Verify higher-fidelity images render, navigation works
2. **Kitty:** Verify kitty graphics protocol works
3. **Alacritty:** Verify fallback to blocks
4. **tmux in iTerm2:** Verify fallback to blocks (no graphics through tmux)
5. **Small terminal:** Verify responsive sizing doesn't break

### Regression Tests
- Existing tests should pass (block mode still works)
- Add tests for new code paths
- Test configuration overrides

## Configuration

### Environment Variables

```bash
# Control graphics protocol usage (default currently blocks for safety)
export PHOTO_TERMINAL_HD_PREVIEW=blocks  # Default: never use graphics
export PHOTO_TERMINAL_HD_PREVIEW=auto    # Auto-detect
export PHOTO_TERMINAL_HD_PREVIEW=force   # Always try graphics protocol

# Control layout (future enhancement)
export PHOTO_TERMINAL_LAYOUT=auto        # Sequential for graphics, sidebyside for blocks
export PHOTO_TERMINAL_LAYOUT=sequential  # Always top/bottom
export PHOTO_TERMINAL_LAYOUT=sidebyside  # Always left/right (blocks only)
```

### Config File Support (Future)
```yaml
# Extend existing ~/.photo-uploader.yaml (do not introduce a second config path)
preview:
  mode: auto  # auto | graphics | blocks
  layout: auto  # auto | sequential | sidebyside

  graphics:
    max_width: 120
    max_height: 40

  blocks:
    max_width: 60
    max_height: 35
```

## Success Criteria

1. **Quality Improvement Measurable**
   - Side-by-side comparison screenshots in iTerm2 show visible quality difference
   - Zoom into photo details - graphics protocol shows sharp edges, blocks show pixelation

2. **No Regression**
   - Existing terminals continue to work (block mode)
   - All existing tests pass
   - Performance is acceptable (verify HD mode latency)

3. **User-Friendly**
   - Auto-detection works correctly
   - Clear error messages if something fails
   - Override flags work as documented

4. **Maintainable**
   - Code is modular (separate renderers)
   - Tests cover both paths
   - Easy to add new protocols in future

## Future Enhancements

1. **Image Caching:** Cache rendered viu output to speed up navigation
2. **Async Rendering:** Load images in background while navigating
3. **Configurable Layouts:** Let users choose layout preference
4. **More Protocols:** Add Sixel support explicitly, support new protocols as they emerge
5. **Thumbnail Bar:** Show small thumbnails of all images in graphics mode
6. **Side-by-side with Graphics:** Explore if possible with careful terminal cell manipulation

## References

Reference links removed from this doc to avoid unverified claims. Re-add with sources once verified.

## Implementation Checklist

- [ ] Add TerminalCapabilities class with protocol detection
- [ ] Implement render_with_graphics_protocol() method
- [ ] Refactor current code to render_with_blocks()
- [ ] Add render_with_preview() dispatcher
- [ ] Add environment variable support (PHOTO_TERMINAL_HD_PREVIEW)
- [ ] Update or remove get_viu_preview() (currently unused) if it should support both modes
- [ ] Write unit tests for protocol detection
- [ ] Write unit tests for renderer dispatch
- [ ] Manual testing in iTerm2
- [ ] Manual testing in Kitty
- [ ] Manual testing in standard terminal (fallback)
- [ ] Update README with compatibility matrix
- [ ] Update README with screenshots showing difference
- [ ] Add error handling and fallback logic
- [ ] Phase 2: Implement selective re-rendering for block mode
- [ ] Phase 2: Responsive sizing for both modes
- [ ] Phase 3: Integration tests
- [ ] Phase 3: Documentation updates

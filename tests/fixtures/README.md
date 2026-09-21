# Test fixtures

Real inputs for the suite. Before these existed the render tests ran against
three zero-byte files created with `Path.touch()`, which no renderer can open -
every render failed inside a worker thread and no assertion ever noticed.

## Images

Regenerate with:

```sh
nix develop -c uv run --extra dev python tests/fixtures/generate.py
```

The generator is deterministic, so a re-run on a clean tree produces no diff.

| File | Size | Why it exists |
|---|---|---|
| `portrait_3x4.jpg` | 300x400 | Known 3:4 aspect. The reference case for "the requested rectangle matches the source aspect". |
| `landscape_4x3.jpg` | 400x300 | The same assertion with the axes swapped. |
| `tiny_40x30.png` | 40x30 | Smaller than any preview box at any terminal size. Must never be upscaled. |
| `photo_2400x1800.jpg` | 2400x1800 | Above the optimizer's 1920px max dimension and above 400KB at quality 95, so both the resize and the quality-iteration loop run. Replaces the absolute `/Users/kurtis/tinker/photo-terminal/test.jpeg` path that made `test_optimizer_integration.py` skip everywhere. |

## `viu_block_capture.bin`

Real `viu` 1.6.1 output, captured with stdout on a pipe - the exact shape
`ImageSelector._render_preview_output` produces today:

```sh
env -i TERM=xterm-ghostty TERM_PROGRAM=ghostty COLORTERM=truecolor \
    viu -w 116 -h 56 tests/fixtures/portrait_3x4.jpg > tests/fixtures/viu_block_capture.bin
```

`116x56` cells is what the current graphics path asks for on a 178x58 terminal,
which is the window in the bug-report screenshot. The capture is what it is
because a pipe cannot answer viu's Kitty capability handshake:

- it opens with the 35-byte Kitty capability probe, followed by the `\x1b[c`
  DA1 fallback - both of which the app then replays to the live terminal, which
  genuinely answers them on the raw-mode stdin the input loop is polling;
- it contains no `a=T` placement anywhere, because the block printer was
  selected;
- it continues as 56 rows of 116 half-block cells separated by `\r\n`. The `\r`
  is the bug: replayed from a single `\033[1;60H` anchor, only row 1 lands in
  the preview column.

`tests/test_preview_invariants.py` replays this file so the defect is pinned
deterministically on a machine with no `viu` installed. It is deleted along with
the rest of the `viu` dependency in phase 2.

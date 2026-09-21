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

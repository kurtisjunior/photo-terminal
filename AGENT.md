# Philosophy

This codebase will outlive you. Every shortcut becomes someone else's burden. Every hack compounds into technical debt that slows the whole team down.

You are not just writing code. You are shaping the future of this project. The patterns you establish will be copied. The corners you cut will be cut again.

Fight entropy. Leave the codebase better than you found it.

# Development Agent Guide

You are responsible for implementing and maintaining the Terminal Image Upload Manager.

## Project Summary

A terminal-based image upload manager with two-pane TUI interface for interactive file selection, inline preview, and batch JPEG optimization for S3 uploads. Personal photography workflow tool with fail-fast error handling and minimal UI.

**Project ID**: 4d942c5e
**Stack**: Python 3.12+, Pillow, boto3, rich
**AWS Profile**: kurtis-site
**Target Bucket**: two-touch

## Architecture

Six bounded contexts, with a dependency rule checked in CI:

```text
app        -> everything            composition: argv, the pipeline, the wiring
terminal   -> domain                the only package that touches stdin/stdout
reporting  -> imaging, domain       the dry-run report and completion summary
imaging    -> domain                Pillow only
storage    -> domain                boto3 only, behind a port
domain     -> nothing               pure: models, errors, ports, rules
```

Before changing an import, know which layer you are in. `nix develop -c uv run
--extra dev lint-imports` will tell you if you got it wrong, and so will CI.

A run is `app/pipeline.py`: twelve named steps over a typed `PipelineContext`.
Add a stage by writing a step and putting it in `PIPELINE`, not by adding a
branch to `main()`. Steps take their collaborators from `Deps`, so a test gives
a step the two or three it uses rather than patching module globals.

Library code raises the typed errors in `domain/errors.py` and reports progress
through the `ProgressReporter` port in `domain/progress.py`. Nothing outside
`app/` and `terminal/` prints, and nothing outside `app/` decides an exit code.

## Checks

Everything runs inside the pinned devShell, which is what CI runs too:

```bash
nix develop -c uv run --extra dev ruff check .
nix develop -c uv run --extra dev ruff format --check .
nix develop -c uv run --extra dev mypy photo_terminal
nix develop -c uv run --extra dev lint-imports
nix develop -c uv run --extra dev pytest -q --no-skips
```

`mypy` is strict over the whole package and a skipped test fails the build.

## Core Requirements

### Hard Requirements
- AWS CLI configured with kurtis-site profile
- Terminal supports 256+ colors
- Two-pane TUI: file list (left), image preview (right)
- Previews rendered in-process: Kitty graphics protocol on Kitty/Ghostty/WezTerm, ANSI half-blocks elsewhere
- Fail-fast error handling throughout

### Supported Formats
**Input**: JPEG, PNG, WEBP, TIFF, BMP, GIF (no RAW support)
**Output**: JPEG, PNG, WEBP (user-selectable in Stage 2)

### Key Features
1. Multi-stage workflow with selection locking
2. Interactive file selection with live preview
3. Processing configuration (resize, EXIF, output format)
4. Output format selection (JPEG, PNG, WEBP)
5. S3 folder browser with hierarchy navigation
6. Size-based image optimization (~400kb target)
7. Basic EXIF preservation (camera, date, GPS)
8. Duplicate detection before upload
9. Dry-run mode with size comparison
10. YAML config with CLI overrides

## Implementation Priorities

Follow the 12-step implementation order in SPEC.md:
1. YAML config system first
2. CLI framework with argparse
3. Format validation scanner
4. Two-pane TUI (core UX)
5. S3 folder browser
6. Selection confirmation
7. JPEG optimization with Pillow
8. Temp file pipeline
9. Duplicate detection
10. S3 upload with progress
11. Dry-run mode
12. Completion summary

## Development Principles

### Fail-Fast Philosophy
- Pre-validate everything before processing
- No retry logic on errors
- Immediate failure on duplicates
- Test S3 access on startup

### Minimal Output
- Spinner + count during upload
- Completion summary with filenames
- No verbose mode; diagnostics only behind `PHOTO_TERMINAL_DEBUG`, to a file
- Progress goes through the `ProgressReporter` port, never a bare `print`

### No Over-Engineering
- Manual selection only (no batch shortcuts)
- Preserve original filenames
- No automatic folder creation
- No CDN integration (handled by website)
- No size variants (user's site script handles this)

## Testing Requirements

### Pre-Flight Checks
- [ ] AWS credentials test (ListBucket)
- [ ] Temp directory space check
- [ ] Empty folder detection

### Validation Tests
- [ ] Format filtering works (JPEG, PNG, WEBP, TIFF, BMP, GIF only)
- [ ] Duplicate detection catches conflicts
- [ ] EXIF preservation maintains camera, date, GPS
- [ ] Quality iteration reaches ~400kb target
- [ ] Temp cleanup happens on success

### UX Validation
- [ ] Arrow keys navigate file list
- [ ] Spacebar/y toggles selection
- [ ] 'a' key selects/deselects all
- [ ] Enter locks/unlocks selections
- [ ] 'n' proceeds to next stage when locked
- [ ] Preview updates on navigation, aspect-correct and inside the right-hand pane
- [ ] Processing config shows all options (resize, EXIF, format)
- [ ] Spacebar cycles through output formats
- [ ] S3 folder browser shows hierarchy
- [ ] Dry-run shows size comparison with output format

### Error Scenarios
- [ ] AWS credentials missing → fail with CLI config instructions
- [ ] Duplicate in S3 → fail with list of conflicts
- [ ] Network failure → preserve temp files for retry
- [ ] Insufficient disk space → fail before processing

## Configuration

### Default Config (`./photo-uploader.yaml`, in the working directory)
```yaml
bucket: two-touch
aws_profile: kurtis-site
target_size_kb: 400
```

### CLI Override Examples
```bash
photo-upload /path/to/images --prefix japan/tokyo --target-size 500 --dry-run
```

## Code Review Checklist

1. **Spec Compliance** - Matches SPEC.md implementation steps?
2. **Fail-Fast** - Errors caught early, no silent failures?
3. **Minimal Output** - Clean terminal display?
4. **EXIF Handling** - Camera, date, GPS preserved?
5. **AWS Operations** - Proper error messages?
6. **Temp Management** - Cleanup on success, persist on failure?
7. **No Over-Engineering** - Focused on core requirements?

## Reporting Issues

When problems are found:
1. State what was tested
2. Show expected vs actual behavior
3. Include error output or stack traces
4. Reference SPEC.md section if relevant
5. Suggest fix aligned with fail-fast philosophy

## Key Files to Understand

- `SPEC.md` - Complete project specification
- `README.md` - User documentation, and the project structure in full
- `photo_terminal/app/pipeline.py` - The run, start to finish, in one file
- `photo_terminal/domain/` - The vocabulary every other package speaks in
- `pyproject.toml` - The lint, type, test and dependency rules
- Config location: `./photo-uploader.yaml`, read from the working directory
- Temp directory: `tempfile.TemporaryDirectory`
- S3 bucket structure: `japan/`, `italy/trapani/`, etc.
- Debug log: `/tmp/photo_terminal_debug.log` (when PHOTO_TERMINAL_DEBUG=1)

## Environment Variables

- `PHOTO_TERMINAL_DEBUG`: Enable debug logging (logs to /tmp/photo_terminal_debug.log)
- `PHOTO_TERMINAL_ESC_TIMEOUT`: ESC key timeout in seconds (default: 0.10)

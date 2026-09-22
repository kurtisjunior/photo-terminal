# Terminal Image Upload Manager with Inline Preview

## Overview

A terminal-based image upload manager with two-pane TUI interface, providing interactive file selection, inline preview, and batch JPEG optimization for S3 uploads.

**Project ID**: 4d942c5e
**Created**: 2026-01-24
**Type**: Feature

## Scope

### Included Features

- Multi-stage workflow with selection locking (Stage 1: select, Stage 2: configure, Stage 3: browse)
- Two-pane TUI with file list (left) and in-process image preview (right) for image selection
- Asynchronous preview rendering with loading indicator on cache misses
- Processing configuration screen (resize, EXIF preservation, output format)
- Output format selection (JPEG, PNG, WEBP) with format-specific optimization
- Interactive S3 folder browser with hierarchy navigation (existing bucket structure)
- Batch image conversion with size-based optimization (~400kb target, configurable)
- Basic EXIF preservation (camera, date taken, GPS) using Pillow
- Temp file processing with automatic cleanup
- YAML configuration with CLI argument overrides
- Minimal progress feedback (spinner + count) with fail-fast error handling
- Dry-run mode showing file list, size changes, and output format
- Format validation and duplicate detection
- Debug mode with environment variable control

### Explicitly Excluded

- Multiple size variant generation (handled by user's site script)
- RAW image format support (CR2, NEF, ARW)
- Multiple cloud provider support
- Database integration
- Web interface or API
- Batch selection shortcuts (manual curation only)
- iTerm2 inline-image and Sixel emitters (both terminals get the half-block preview)

## Assumptions

- User has AWS CLI configured with profile (kurtis-site) and credentials
- Terminal supports 256+ colors. Previews are rendered in-process: the [Kitty graphics protocol](https://sw.kovidgoyal.net/kitty/graphics-protocol/) on Kitty, Ghostty and WezTerm, ANSI half-blocks everywhere else. No external binary is required.
- Source images are in standard web formats only: JPEG, PNG, WEBP, TIFF, BMP, GIF
- Target S3 bucket (two-touch) exists with location-based folder structure (japan/, italy/, etc.)
- AWS permissions configured for ListBucket and PutObject operations
- Python 3.12+ with Pillow, boto3, and TUI libraries available
- Sufficient local disk space in temp directory for batch processing
- Primary use case is personal photography workflow (speed, UX, reliability prioritized)
- User's website handles generation of size variants (_medium, _small, _thumb) and WEBP conversion

## Implementation Steps

1. **Create YAML configuration system with auto-initialization and CLI override support**
   - Establish configuration foundation (bucket, profile, target_size defaults) before CLI parsing
   - Auto-create ./photo-uploader.yaml in the working directory on first run, with sensible defaults

2. **Build CLI framework with argparse supporting config overrides and dry-run mode**
   - Support folder path input, --prefix, --target-size, --dry-run flags
   - CLI arguments override config file values for flexibility

3. **Implement folder scanner with format validation (JPEG, PNG, WEBP, TIFF, BMP, GIF)**
   - Pre-validate and filter images before UI starts
   - Fail-fast on empty folders
   - Only show valid, processable images to user

4. **Build two-pane TUI with file list (left) and image preview (right)**
   - Core UX requirement: navigable list with checkboxes, live preview on right
   - Preview rendering is asynchronous with a loading indicator on cache misses
   - Arrow keys navigate, spacebar toggles selection, enter confirms

5. **Implement interactive S3 folder browser with hierarchy navigation**
   - Query existing S3 structure (japan/, italy/trapani/, etc.) using boto3 ListBuckets
   - Allow drilling into subdirectories to select upload target

6. **Add selection confirmation with count display**
   - After marking images, show "Upload X images? [y/n]" before processing starts
   - Minimal confirmation aligned with fail-fast philosophy

7. **Implement size-based JPEG optimization using Pillow quality iteration**
   - Target ~400kb (configurable) by iteratively adjusting JPEG quality (95→85→75...)
   - Preserve aspect ratio and basic EXIF (camera, date, GPS)

8. **Build temp file processing pipeline with automatic cleanup**
   - Save processed images to tempfile.TemporaryDirectory for reliability
   - Enables retry on upload failure without reprocessing
   - Auto-cleanup on exit

9. **Implement duplicate detection in target S3 prefix**
   - Before upload, check if filename exists in target folder using HeadObject
   - Fail immediately on conflict to prevent accidental overwrites

10. **Add S3 upload with minimal progress feedback (spinner + count)**
    - Use boto3 upload_file with spinner showing "⠋ Uploading... (12/15)"
    - No retry logic. Fail immediately on errors for fast feedback.

11. **Implement dry-run mode showing file list and size changes**
    - Display original → processed sizes for each selected image without uploading
    - Preview operation impact before committing

12. **Add completion summary with count, total size, and uploaded filenames**
    - Verify successful uploads with minimal output
    - List filenames for user confirmation

## Risks and Mitigations

### Terminal does not support a graphics protocol
**Mitigation**: Detect the protocol from the environment and render half-blocks when there is no Kitty support, including inside tmux and screen. Both paths are in-process, so there is nothing to install and nothing to fail at startup. A preview box under 20 columns or 10 rows is suppressed with a message rather than drawn as a few unreadable cells.

### Large high-resolution images may cause slow preview rendering
**Mitigation**: Pillow resizes the source to exactly the placement rectangle, which is a whole number of terminal cells, so the terminal has nothing left to scale. Preview rendering is asynchronous with a loading indicator, so navigation remains responsive and the preview updates when ready.

### Reorder interface preview lag
**Mitigation**: Reorder previews use the same asynchronous rendering path with a loading indicator to keep navigation responsive.

### Temp directory fills up with large batch processing
**Mitigation**: Use Python tempfile.TemporaryDirectory for automatic cleanup. Check available disk space before processing starts. Fail-fast if insufficient space.

### AWS credential or permission errors prevent S3 operations
**Mitigation**: Test S3 access early (ListBucket on startup during folder browser). Fail-fast with clear error message pointing to AWS CLI configuration.

### Network failure during upload loses processed images
**Mitigation**: Temp files persist until successful upload completion. User can retry operation without reprocessing since temp cleanup only happens on success or manual exit.

### Duplicate filename exists in S3 target folder
**Mitigation**: Pre-check all selected filenames with HeadObject before starting processing. Fail immediately with list of conflicting files. No partial uploads.

### EXIF data loss or corruption during JPEG recompression
**Mitigation**: Use Pillow's exif parameter in save() to preserve selected fields (camera, date, GPS). Test with sample images from user's camera models.

### Quality iteration fails to reach target file size
**Mitigation**: Set minimum quality threshold (e.g., 60). If target size unreachable, save at minimum quality and warn user about size. Consider adding --force flag to upload anyway.

## Design Decisions

### Package Architecture

Six bounded contexts with a one-line dependency rule, enforced in CI by
`import-linter` rather than described in a comment:

```text
app        -> everything            composition: argv, the pipeline, the wiring
terminal   -> domain                the only package that touches stdin/stdout
reporting  -> imaging, domain       the dry-run report and completion summary
imaging    -> domain                Pillow only
storage    -> domain                boto3 only, behind a port
domain     -> nothing               pure: models, errors, ports, rules
```

A run is `app/pipeline.py`: twelve named steps over a typed
`PipelineContext`, each taking its collaborators as a value so it can be tested
on its own. Library code raises typed errors carrying an exit code and reports
progress through a `ProgressReporter` port; deciding what a failure looks like
and what the process exits with happens once, in the pipeline.

### Image Formats
Standard web formats only (JPEG, PNG, WEBP, TIFF, BMP, GIF). No RAW support.

### AWS Credentials
Use AWS CLI configuration with profile 'kurtis-site'. Region from CLI config.

### Resize Strategy
Size-based optimization targeting ~400kb (configurable). Format-specific strategies:
- JPEG/WEBP: Pillow quality iteration (95→60)
- PNG: Maximum compression (lossless, cannot reach target size)

### S3 Organization
Interactive folder browser for existing bucket structure. Navigate hierarchy (japan/, italy/trapani/). No automatic folder creation or date-based organization.

### EXIF Preservation
Basic fields only (camera, date taken, GPS). Leave date empty if missing from original. No fallback to file modification time.

### Dry-Run Support
Enabled; shows selected files with original → processed size comparison. No actual upload or S3 operations performed.

### Logging Output
Minimal: spinner with count during upload, completion summary with filenames. No verbose mode. Diagnostic logging is off unless `PHOTO_TERMINAL_DEBUG` is set, and goes to a file rather than the screen.

### CDN Integration
None; the tool handles upload to S3 only. User's website generates size variants and manages CDN separately.

### Selection UI
Two-pane TUI with checkbox-style indicators and multi-stage workflow:
1. Mark images with y/Space (shows [x])
2. Lock selections with Enter (prevents accidental changes)
3. Proceed with 'n' to processing configuration
Manual selection only, with 'a' key for select/deselect all. Arrow keys navigate, spacebar/y toggles, enter locks, 'n' proceeds. Preview rendering is asynchronous with a loading indicator on cache misses to keep navigation responsive.

### Error Handling
Fail-fast philosophy throughout. No retry logic, immediate error on duplicates, pre-validation before processing starts.

### File Naming
Preserve original filenames. No sanitization, timestamps, or renaming options.

### Configuration
YAML file (`./photo-uploader.yaml`, in the working directory) auto-created with defaults. CLI args override config values.

### Temp Processing
Python tempfile.TemporaryDirectory for processed images. Automatic cleanup on success. Persistence on failure enables retry without reprocessing.

### Dependencies
No external binaries. Pillow for processing and preview rendering, boto3 for S3, rich for the non-interactive reports, PyYAML for config. Previews are emitted from Python: the Kitty graphics protocol on Kitty/Ghostty/WezTerm, ANSI half-blocks elsewhere.

### Output Formats
User selects output format in Stage 2 (Processing Configuration):
- JPEG: Lossy compression, smallest size, quality-based optimization
- PNG: Lossless compression, transparency support, max compression level
- WEBP: Modern format, lossy compression, balanced size/quality

### Environment Variables
- PHOTO_TERMINAL_DEBUG: Enable debug logging to /tmp/photo_terminal_debug.log
- PHOTO_TERMINAL_ESC_TIMEOUT: ESC key detection timeout in seconds (default: 0.10)

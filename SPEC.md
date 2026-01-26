# Terminal Image Upload Manager with Inline Preview

## Overview

A terminal-based image upload manager with two-pane TUI interface, providing interactive file selection, inline preview, and batch JPEG optimization for S3 uploads.

**Project ID**: 4d942c5e
**Created**: 2026-01-24
**Type**: Feature

## Scope

### Included Features

- Two-pane TUI with file list (left) and viu preview (right) for image selection
- Interactive S3 folder browser with hierarchy navigation (existing bucket structure)
- Batch JPEG conversion with size-based optimization (~400kb target, configurable)
- Basic EXIF preservation (camera, date taken, GPS) using Pillow
- Temp file processing with automatic cleanup
- YAML configuration with CLI argument overrides
- Minimal progress feedback (spinner + count) with fail-fast error handling
- Dry-run mode showing file list and size changes
- Format validation and duplicate detection

### Explicitly Excluded

- Multiple size variant generation (handled by user's site script)
- RAW image format support (CR2, NEF, ARW)
- Multiple cloud provider support
- Database integration
- Web interface or API
- Batch selection shortcuts (manual curation only)
- Graceful degradation without viu (hard requirement)

## Assumptions

- User has AWS CLI configured with profile (kurtis-site) and credentials
- Terminal supports 256+ colors and viu is installed (hard requirement) - [viu](https://github.com/atanunq/viu)
- Source images are in standard web formats only: JPEG, PNG, WEBP, TIFF, BMP, GIF
- Target S3 bucket (two-touch) exists with location-based folder structure (japan/, italy/, etc.)
- AWS permissions configured for ListBucket and PutObject operations
- Python 3.8+ with Pillow, boto3, and TUI libraries available
- Sufficient local disk space in temp directory for batch processing
- Primary use case is personal photography workflow (speed, UX, reliability prioritized)
- User's website handles generation of size variants (_medium, _small, _thumb) and WEBP conversion

## Implementation Steps

1. **Create YAML configuration system with auto-initialization and CLI override support**
   - Establish configuration foundation (bucket, profile, target_size defaults) before CLI parsing
   - Auto-create ~/.photo-uploader.yaml on first run with sensible defaults

2. **Build CLI framework with argparse supporting config overrides and dry-run mode**
   - Support folder path input, --prefix, --target-size, --dry-run flags
   - CLI arguments override config file values for flexibility

3. **Implement folder scanner with format validation (JPEG, PNG, WEBP, TIFF, BMP, GIF)**
   - Pre-validate and filter images before UI starts
   - Fail-fast on empty folders
   - Only show valid, processable images to user

4. **Build two-pane TUI with file list (left) and viu preview (right)**
   - Core UX requirement - navigable list with checkboxes, live preview on right
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
    - No retry logic - fail immediately on errors for fast feedback

11. **Implement dry-run mode showing file list and size changes**
    - Display original → processed sizes for each selected image without uploading
    - Preview operation impact before committing

12. **Add completion summary with count, total size, and uploaded filenames**
    - Verify successful uploads with minimal output
    - List filenames for user confirmation

## Risks and Mitigations

### viu not installed or terminal incompatibility
**Mitigation**: Check for viu availability on startup with clear error message and installation instructions. No fallback since visual preview is core requirement.

### Large high-resolution images may cause slow preview rendering
**Mitigation**: viu handles scaling automatically. Add loading indicator while rendering preview. User can navigate away if render is slow.

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

### Image Formats
Standard web formats only (JPEG, PNG, WEBP, TIFF, BMP, GIF). No RAW support.

### AWS Credentials
Use AWS CLI configuration with profile 'kurtis-site'. Region from CLI config.

### Resize Strategy
Size-based optimization targeting ~400kb (configurable). Pillow quality iteration rather than dimension-based resizing.

### S3 Organization
Interactive folder browser for existing bucket structure. Navigate hierarchy (japan/, italy/trapani/). No automatic folder creation or date-based organization.

### EXIF Preservation
Basic fields only (camera, date taken, GPS). Leave date empty if missing from original. No fallback to file modification time.

### Dry-Run Support
Yes - show selected files with original → processed size comparison. No actual upload or S3 operations performed.

### Logging Output
Minimal - spinner with count during upload, completion summary with filenames. No verbose mode or debug logging.

### CDN Integration
None - tool handles upload to S3 only. User's website generates size variants and manages CDN separately.

### Selection UI
Two-pane TUI with checkbox-style indicators. Manual selection only, no batch shortcuts. Arrow keys navigate, spacebar toggles, enter confirms.

### Error Handling
Fail-fast philosophy throughout. No retry logic, immediate error on duplicates, pre-validation before processing starts.

### File Naming
Preserve original filenames. No sanitization, timestamps, or renaming options.

### Configuration
YAML file (~/.photo-uploader.yaml) auto-created with defaults. CLI args override config values.

### Temp Processing
Python tempfile.TemporaryDirectory for processed images. Automatic cleanup on success. Persistence on failure enables retry without reprocessing.

### Dependencies
viu is hard requirement (no fallback mode). Pillow for processing, boto3 for S3, rich/textual for TUI.

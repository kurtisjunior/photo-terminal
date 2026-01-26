# Development Agent Guide

You are responsible for implementing and maintaining the Terminal Image Upload Manager.

## Project Summary

A terminal-based image upload manager with two-pane TUI interface for interactive file selection, inline preview, and batch JPEG optimization for S3 uploads. Personal photography workflow tool with fail-fast error handling and minimal UI.

**Project ID**: 4d942c5e
**Stack**: Python 3.8+, Pillow, boto3, viu, rich/textual
**AWS Profile**: kurtis-site
**Target Bucket**: two-touch

## Core Requirements

### Hard Requirements
- viu installed and working (no fallback mode)
- AWS CLI configured with kurtis-site profile
- Terminal supports 256+ colors
- Two-pane TUI: file list (left), viu preview (right)
- Fail-fast error handling throughout

### Supported Formats
JPEG, PNG, WEBP, TIFF, BMP, GIF (no RAW support)

### Key Features
1. Interactive file selection with live preview
2. S3 folder browser with hierarchy navigation
3. Size-based JPEG optimization (~400kb target)
4. Basic EXIF preservation (camera, date, GPS)
5. Duplicate detection before upload
6. Dry-run mode with size comparison
7. YAML config with CLI overrides

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
- No verbose mode or debug logging

### No Over-Engineering
- Manual selection only (no batch shortcuts)
- Preserve original filenames
- No automatic folder creation
- No CDN integration (handled by website)
- No size variants (user's site script handles this)

## Testing Requirements

### Pre-Flight Checks
- [ ] viu availability on startup
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
- [ ] Spacebar toggles selection
- [ ] Enter confirms and proceeds
- [ ] viu preview updates on navigation
- [ ] S3 folder browser shows hierarchy
- [ ] Dry-run shows size comparison

### Error Scenarios
- [ ] viu not installed → clear error + install instructions
- [ ] AWS credentials missing → fail with CLI config instructions
- [ ] Duplicate in S3 → fail with list of conflicts
- [ ] Network failure → preserve temp files for retry
- [ ] Insufficient disk space → fail before processing

## Configuration

### Default Config (~/.photo-uploader.yaml)
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
- Config location: `~/.photo-uploader.yaml`
- Temp directory: `tempfile.TemporaryDirectory`
- S3 bucket structure: `japan/`, `italy/trapani/`, etc.

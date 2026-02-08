# Terminal Image Upload Manager

A terminal-based image upload manager with two-pane TUI interface, providing interactive file selection, high-quality image previews that automatically adapt to your terminal capabilities, and batch JPEG optimization for S3 uploads.

**Project ID**: 4d942c5e

## Features

- **Two-Pane TUI**: File list (left) with live image preview (right) for image selection
- **Responsive Preview Rendering**: Asynchronous preview generation with a loading indicator on cache misses
- **Interactive Image Reordering**: Grab-and-drop interface to control upload order with numeric prefixes
- **Interactive S3 Folder Browser**: Navigate existing S3 bucket structure to select upload target
- **Automatic Image Resizing**: Resizes to 1920px (configurable) for optimal web size
- **Size-Based JPEG Optimization**: Target ~400KB file size (configurable)
- **EXIF Preservation**: Maintains camera model, date taken, and GPS coordinates
- **Duplicate Detection**: Pre-checks S3 to prevent accidental overwrites
- **Dry-Run Mode**: Preview size changes without uploading
- **Fail-Fast Error Handling**: Immediate feedback on errors with no silent failures
- **Minimal Output**: Clean terminal display with progress feedback
- **Temp File Pipeline**: Automatic cleanup on success, persistence on failure for retry

## Requirements

### System Requirements

- **Python 3.8+**
- **AWS CLI** configured with credentials
- Terminal supporting 256+ colors

### Python Dependencies

- Pillow (image processing)
- boto3 (AWS S3)
- PyYAML (configuration)

## Installation

### 1. Install Package

Clone the repository and install in development mode:

```bash
git clone <repository-url>
cd photo-terminal
pip install -e .
```

Or install just the dependencies:

```bash
pip install -r requirements.txt
```

### 2. Configure AWS CLI

```bash
aws configure --profile kurtis-site
```

Enter your AWS credentials when prompted. Make sure your profile has permissions for:
- `s3:ListBucket` (to browse folders and check duplicates)
- `s3:PutObject` (to upload images)


## Configuration

On first run, a configuration file will be created at `photo-uploader.yaml` with defaults:

```yaml
bucket: two-touch
aws_profile: kurtis-site
target_size_kb: 400
```

### Configuration Options

- **bucket**: S3 bucket name for uploads
- **aws_profile**: AWS CLI profile name to use
- **target_size_kb**: Target file size in kilobytes for JPEG optimization

All configuration values can be overridden via command-line arguments.

## Usage

### Basic Usage

After installation with `pip install -e .`, you can use the `photo-upload` command:

```bash
photo-upload /path/to/images --prefix japan/tokyo
```

Or run as a Python module:

```bash
python -m photo_terminal /path/to/images --prefix japan/tokyo
```

### Command-Line Options

```
photo-upload <folder_path> [options]

Required Arguments:
  folder_path              Path to folder containing images

Optional Arguments:
  --prefix PREFIX          S3 prefix/folder path (e.g., "japan/tokyo")
                          If omitted, interactive S3 browser will launch
  --target-size KB         Target file size in KB (default: 400)
  --dry-run               Preview without uploading
```

### Examples

**Upload with specific prefix**:
```bash
photo-upload ./vacation-photos --prefix italy/trapani
```

**Upload with interactive folder browser**:
```bash
photo-upload ./vacation-photos
# Launches interactive S3 folder browser
```

**Use custom target size**:
```bash
photo-upload ./photos --prefix spain/barcelona --target-size 500
```

**Dry-run to preview changes**:
```bash
photo-upload ./photos --prefix france/paris --dry-run
```

## Workflow

The application follows this multi-stage workflow:

1. **Load Configuration**: Reads `photo-uploader.yaml`
2. **Parse CLI Arguments**: Overrides config values if specified
3. **Scan Folder**: Validates images (JPEG, PNG, WEBP, TIFF, BMP, GIF)
4. **Stage 1 - Select Images**: Two-pane TUI with live preview (asynchronous rendering)
   - Mark images with `y` or `Space` (shows `[x]`)
   - Lock selections with `Enter` (prevents accidental changes)
   - Proceed to next stage with `n`
5. **Stage 2 - Configure Processing**: Interactive configuration screen
   - Choose whether to resize images
   - Choose whether to preserve EXIF data
   - Confirm with `Enter` or go back with `b`
6. **Browse S3 Folders**: Interactive folder browser (if --prefix not specified)
7. **Confirm Upload**: Shows count and target location
8. **Reorder Images** (Optional): Interactive grab-and-drop interface
   - Navigate with `↑↓` or `j/k`
   - Press `Space` to grab/drop images
   - Press `r` to reset to original order
   - Press `Enter` to confirm order
   - Images uploaded with numeric prefixes (01_, 02_, 03_)
9. **Dry-Run Check**: If --dry-run flag set, shows preview and exits
10. **Check Duplicates**: Pre-validates no files exist in S3 target
11. **Process Images**: Resizes to 1920px and optimizes with JPEG quality iteration
12. **Upload to S3**: Batch upload with progress spinner
13. **Show Summary**: Displays completion statistics
14. **Cleanup**: Removes temp files on success

## Multi-Stage Workflow Example

Here's a typical workflow when using the photo upload manager:

### 1. Start the application
```bash
photo-upload /path/to/photos --prefix japan/tokyo
```

### 2. Select images (Stage 1)
- Navigate through images with arrow keys
- Press `y` or `Space` to mark images you want to upload (they show `[x]`)
- Preview appears on the right side as you navigate, with a loading indicator on cache misses
- Select multiple images by marking each one
- Press `Enter` to lock your selections (green confirmation appears)
- Press `n` to proceed to processing configuration

### 3. Configure processing (Stage 2)
- Three options appear: "Resize images", "Preserve EXIF data", and "Output format"
- Resize and EXIF preservation are enabled by default

### 4. Reorder images (Optional)
When prompted "Reorder images? (y/N):", press `y` to enter the interactive reordering interface:

```
┌─ Reorder Images (3 selected) ──────────────────────────┐
│                                                         │
│  →  1. IMG_2027.JPG          Preview:                  │
│     2. IMG_2032.JPG          [████████████]            │
│     3. IMG_2033.JPG          [████ image ████]         │
│                                                         │
│  Final upload names:                                   │
│  01_IMG_2027.JPG → 02_IMG_2032.JPG → 03_IMG_2033.JPG  │
│                                                         │
│  SPACE to grab/drop  •  ↑↓ or j/k to move  •  r reset │
│  ENTER when done                                       │
└─────────────────────────────────────────────────────────┘
```

**Keyboard Controls:**
- `↑↓` or `j/k`: Navigate through images
- `Space`: Grab current image (press again to drop)
- `r`: Reset to original order
- `Enter`: Confirm order and continue
- `q`: Cancel reordering

**How it works:**
1. Navigate to the image you want to move
2. Press `Space` to "grab" it (highlights in green)
3. Use arrow keys to move it up or down
4. Press `Space` again to "drop" it in the new position
5. Repeat for other images
6. Press `Enter` when done

Images will be uploaded with numeric prefixes (01_, 02_, 03_, etc.) to maintain the order you specified on S3.

Preview rendering in the reorder interface is asynchronous to keep navigation responsive. When a preview is not cached, a short "[Loading preview...]" indicator appears while the render completes.
- Output format defaults to JPEG
- Use arrow keys to navigate between options
- Press `Space` to toggle options on/off, or cycle through output formats (JPEG → PNG → WEBP)
- Press `Enter` to confirm and proceed
- Or press `b` to go back and change your image selection

### 4. Browse S3 folders (Stage 3, if --prefix not specified)
- Navigate through existing S3 folder structure
- Press `Enter` to select a folder or go deeper
- Press `Backspace` to go up one level

### 5. Confirm and upload
- Review the summary of selected images and target location
- Confirm to start processing and upload
- Watch the progress spinner as images are optimized and uploaded

### 6. View completion summary
- See statistics: file count, original size, processed size, savings
- View list of uploaded files with their S3 paths

## Dry-Run Mode

Use `--dry-run` to preview what would happen without actually uploading:

```bash
photo-upload ./photos --prefix test --dry-run
```

Output shows:
- Files to be processed
- Original → Processed sizes
- Reduction percentages
- S3 keys that would be created
- Summary statistics

No S3 operations are performed in dry-run mode.

## Interactive TUI Controls

### Stage 1: Image Selection Screen

The image selection uses a multi-step workflow to prevent accidental uploads:

1. **Mark images**: Use `y` or `Space` to mark images with `[x]`
2. **Lock selections**: Press `Enter` to lock your selections (prevents accidental changes)
3. **Proceed**: Press `n` to move to the processing configuration stage

**Keyboard Controls**:
- **Arrow Keys** (↑/↓): Navigate file list
- **y** or **Space**: Toggle selection checkbox `[x]`
- **a**: Select/deselect all images at once
- **Enter**: Lock/unlock selections
  - When unlocked: Locks your current selections
  - When locked: Unlocks to allow changes
- **n**: Proceed to next stage (only available when selections are locked)
- **q** or **Esc**: Cancel and quit

Preview rendering is asynchronous to keep navigation responsive. When a preview is not cached, a short "[Loading preview...]" indicator appears while the render completes.

### Stage 2: Processing Configuration Screen

After locking your selections, configure how images will be processed:

**Options**:
- **Resize images**: Optimize images to target file size (default: enabled)
- **Preserve EXIF data**: Keep camera, date, and GPS metadata (default: enabled)
- **Output format**: Choose output file format - JPEG, PNG, or WEBP (default: JPEG)
  - **JPEG**: Lossy compression, smallest size
  - **PNG**: Lossless, larger size, supports transparency
  - **WEBP**: Modern format, balanced size/quality

**Keyboard Controls**:
- **Arrow Keys** (↑/↓): Navigate options
- **Space**: Toggle option on/off, or cycle through output formats
- **Enter**: Confirm configuration and proceed
- **b**: Go back to image selection stage
- **q** or **Esc**: Cancel and quit

### Stage 3: S3 Folder Browser

If `--prefix` was not specified on the command line, an interactive browser appears:

**Keyboard Controls**:
- **Arrow Keys** (↑/↓): Navigate folders
- **Enter**: Select folder / Navigate into subfolder
- **Backspace**: Go up one level
- **q**: Cancel and exit

## Supported Image Formats

### Input Formats (what you can upload)
- JPEG (.jpg, .jpeg)
- PNG (.png)
- WEBP (.webp)
- TIFF (.tif, .tiff)
- BMP (.bmp)
- GIF (.gif)

**Note**: RAW formats (CR2, NEF, ARW) are not supported.

### Output Formats (what gets saved to S3)

You can choose the output format during processing configuration (Stage 2):

**JPEG** (default)
- Lossy compression with quality-based optimization
- Smallest file sizes
- Best for photographs
- EXIF support (camera, date, GPS preserved)
- Transparency removed (composited on white background)

**PNG**
- Lossless compression
- Larger file sizes
- Best for graphics, logos, or images requiring transparency
- Transparency preserved (RGBA support)
- Cannot optimize to target size (uses maximum compression)

**WEBP**
- Modern format with lossy compression
- Balanced file size and quality
- Good browser support for modern web
- EXIF support (camera, date, GPS preserved)
- Transparency removed (composited on white background)

## Error Handling

The application follows a fail-fast philosophy:

### Common Errors

**AWS credentials missing**:
```
Error: Failed to initialize AWS session with profile 'kurtis-site'
Make sure AWS CLI is configured with: aws configure --profile kurtis-site
```

**Duplicate files in S3**:
```
Error: The following files already exist in s3://two-touch/japan/tokyo/:
  - image1.jpg
  - image2.jpg

Aborting to prevent overwrites. No files were uploaded.
```

**Insufficient disk space**:
```
Error: Insufficient disk space for processing.
Needed: 150.0MB, Available: 50.0MB
```

**Upload failure**:
```
Error: Failed to upload 'image.jpg' to s3://two-touch/test/image.jpg
AWS Error [AccessDenied]: Access Denied

Upload failed. Temp files preserved for retry.
```

### Retry After Failure

If an upload fails, temp files are preserved in `/tmp/photo_upload_*`. You can retry by running the same command again. Processing will be skipped if temp files exist from a previous run.

## Completion Summary

After successful upload, a summary is displayed:

```
UPLOAD COMPLETE
═══════════════════════════════════════════════

Files uploaded:    15
Original size:     72.5 MB
Processed size:    5.8 MB
Total savings:     66.7 MB (92.0%)

Location: s3://two-touch/japan/tokyo/

Uploaded files:
  - image1.jpg → japan/tokyo/image1.jpg
  - image2.jpg → japan/tokyo/image2.jpg
  - ...
```

## EXIF Preservation

The optimizer preserves the following EXIF fields when using JPEG or WEBP output formats:
- **Make**: Camera manufacturer
- **Model**: Camera model
- **DateTimeOriginal**: Date photo was taken
- **DateTime**: Date file was modified
- **DateTimeDigitized**: Date photo was digitized
- **GPSInfo**: GPS coordinates

Other EXIF data may be lost during recompression.

**Note**: PNG has limited EXIF support. While the optimizer attempts to preserve EXIF data, PNG files typically do not store camera metadata.

## Optimization Strategy

The optimizer uses different strategies based on the output format:

### JPEG and WEBP (Lossy Formats)
Iterative quality adjustment to reach target file size:

1. Checks if original is already smaller than target → uses quality 95
2. Otherwise, tries quality levels: 95, 90, 85, 80, 75, 70, 65, 60
3. Stops at first quality level that reaches target size
4. If target not reached even at quality 60, saves at minimum quality with warning

Images are converted to RGB if necessary (e.g., RGBA with transparency composited on white background).

### PNG (Lossless Format)
Maximum compression without quality loss:

1. Uses compression level 9 (maximum)
2. Cannot optimize to target size (lossless format)
3. Preserves transparency (RGBA support)
4. Warns if final size exceeds target

Image mode is preserved when possible (RGB, RGBA, grayscale).

## Testing

Run the test suite:

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_photo_upload.py -v

# Run with coverage
pytest --cov=photo_terminal --cov-report=html
```

## Environment Variables

The following environment variables can be used to customize behavior:

### PHOTO_TERMINAL_DEBUG
Enable debug logging for troubleshooting:
```bash
export PHOTO_TERMINAL_DEBUG=1
photo-upload ./images --prefix test
```

Debug logs are written to `/tmp/photo_terminal_debug.log` and include:
- Terminal capabilities detection
- TUI rendering events
- Key press handling
- Image caching operations

### PHOTO_TERMINAL_ESC_TIMEOUT
Adjust the timeout for ESC key detection (default: 0.10 seconds):
```bash
export PHOTO_TERMINAL_ESC_TIMEOUT=0.15
photo-upload ./images
```

This controls how long the system waits to distinguish between a lone ESC press and escape sequences (like arrow keys). Increase if you experience issues with arrow key detection on slower terminals.

## Troubleshooting

### AWS permission errors

**Check AWS configuration**:
```bash
aws s3 ls s3://two-touch/ --profile kurtis-site
```

**Verify IAM permissions** for your AWS user:
- `s3:ListBucket` on bucket
- `s3:PutObject` on bucket
- `s3:GetObject` on bucket (for duplicate checking)

### Images not appearing in scan

**Check supported formats**: Only JPEG, PNG, WEBP, TIFF, BMP, GIF are supported.

**Check file permissions**: Make sure images are readable.

### Upload is slow

**Large images**: Processing high-resolution images takes time. The optimizer must iteratively test different JPEG quality levels.

**Network speed**: Upload speed depends on your internet connection and AWS region.

**Parallel uploads**: Currently uploads are sequential. This is intentional for fail-fast behavior.

## Development

### Project Structure

```
photo-terminal/
├── README.md                 # Main project documentation
├── AGENT.md                  # Development agent guide
├── SPEC.md                   # Project specification
├── LICENSE                   # MIT License
├── pyproject.toml            # Package configuration
├── requirements.txt          # Python dependencies
├── photo_terminal/           # Source code package
│   ├── __init__.py
│   ├── __main__.py          # CLI entry point
│   ├── config.py            # YAML configuration management
│   ├── scanner.py           # Image format validation
│   ├── tui.py               # Two-pane image selector with multi-stage workflow
│   ├── input_utils.py       # Keyboard input utilities
│   ├── s3_browser.py        # Interactive S3 folder browser
│   ├── confirmation.py      # Upload confirmation prompt
│   ├── optimizer.py         # Multi-format image optimization
│   ├── processor.py         # Batch processing pipeline
│   ├── duplicate_checker.py # S3 duplicate detection
│   ├── uploader.py          # S3 upload with progress
│   ├── dry_run.py           # Dry-run mode
│   └── summary.py           # Completion summary display
└── tests/                   # Test suite
    └── test_*.py            # Test files
```

### Running Tests

```bash
# Run all tests with verbose output
pytest -v

# Run specific module tests
pytest tests/test_summary.py -v

# Run integration tests
pytest tests/test_photo_upload.py::test_full_workflow_success -v

# Run with coverage
pytest --cov=photo_terminal --cov-report=html
```

## Design Philosophy

### Fail-Fast

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

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

The MIT License is a permissive open source license that allows commercial use, modification, and distribution with minimal restrictions. It only requires attribution and inclusion of the license notice.

## Credits

Built with:
- [Pillow](https://python-pillow.org/) - Image processing
- [boto3](https://boto3.amazonaws.com/) - AWS SDK
- [PyYAML](https://pyyaml.org/) - Configuration management

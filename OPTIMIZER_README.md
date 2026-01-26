# Image Optimizer Module

Size-based JPEG optimization with EXIF preservation for the photo upload tool.

## Overview

The optimizer module provides intelligent image optimization that:
- Targets specific file sizes (default: ~400KB)
- Preserves aspect ratio (no dimension changes)
- Preserves basic EXIF data (camera model, date taken, GPS)
- Converts all input formats to JPEG output
- Uses iterative quality adjustment for optimal compression
- Follows fail-fast philosophy for corrupted images
- Best-effort EXIF preservation (warns but doesn't fail)

## Features

### Size-Based Optimization
- Iteratively adjusts JPEG quality to reach target file size
- Quality steps: 95 → 90 → 85 → 80 → 75 → 70 → 65 → 60
- Minimum quality threshold: 60 (prevents over-compression)
- Warns if target size cannot be reached at minimum quality

### EXIF Preservation
- Extracts and preserves important EXIF fields:
  - Camera manufacturer (Make)
  - Camera model (Model)
  - Date photo was taken (DateTimeOriginal)
  - Date file was modified (DateTime)
  - Date photo was digitized (DateTimeDigitized)
  - GPS coordinates (GPSInfo)
- Best-effort approach: warns but doesn't fail if EXIF missing
- Uses Pillow's native EXIF handling

### Format Support
- **Input formats**: JPEG, PNG, WEBP, TIFF, BMP, GIF
- **Output format**: JPEG (all inputs converted)
- Automatic color space conversion:
  - RGBA → RGB (composites on white background)
  - Grayscale → RGB
  - Other modes → RGB

### Error Handling
- **Fail-fast**: Immediate failure on corrupted images
- **Best-effort EXIF**: Warns if EXIF cannot be preserved
- **Clear messages**: Detailed error information for debugging
- **Size warnings**: Notifies if target size unreachable

## Usage

### Basic Example

```python
from pathlib import Path
from optimizer import optimize_image

input_path = Path("photo.jpg")
output_path = Path("/tmp/optimized.jpg")

result = optimize_image(
    input_path=input_path,
    output_path=output_path,
    target_size_kb=400
)

print(f"Original: {result['original_size'] / 1024:.1f} KB")
print(f"Optimized: {result['final_size'] / 1024:.1f} KB")
print(f"Quality: {result['quality_used']}")
print(f"Warnings: {result['warnings']}")
```

### Return Value

The `optimize_image()` function returns a dictionary with:

```python
{
    'original_size': 5428224,      # Original file size in bytes
    'final_size': 409600,          # Final file size in bytes
    'quality_used': 75,            # JPEG quality level used (60-95)
    'format': 'JPEG',              # Original image format
    'warnings': []                 # List of warning messages
}
```

### Warnings

The optimizer may return these warnings:

- **`no_exif_data`**: No EXIF data found in image (not an error)
- **`exif_preservation_failed`**: EXIF extraction failed (continues without EXIF)
- **`target_size_not_reached`**: Minimum quality reached but target size exceeded

Example warning:
```python
['target_size_not_reached: Could not reach target size of 400KB at minimum quality 60. Final size: 433.1KB']
```

## Integration

### With Config System

```python
from config import load_config
from optimizer import optimize_image

config = load_config()

result = optimize_image(
    input_path=Path("photo.jpg"),
    output_path=Path("/tmp/optimized.jpg"),
    target_size_kb=config.target_size_kb  # From config file
)
```

### With Temp File Pipeline (Task #8)

The optimizer is designed to be used in the temp file processing pipeline:

```python
import tempfile
from pathlib import Path
from optimizer import optimize_image

# Create temp directory
with tempfile.TemporaryDirectory() as temp_dir:
    temp_path = Path(temp_dir)

    # Process each selected image
    for image_path in selected_images:
        output_path = temp_path / f"optimized_{image_path.name}"
        result = optimize_image(image_path, output_path, target_size_kb=400)

        # Handle warnings
        if result['warnings']:
            for warning in result['warnings']:
                print(f"Warning: {warning}")
```

## Testing

The module includes comprehensive tests covering:

### Basic Optimization
- Large images requiring compression
- Small images already under target size
- Quality iteration behavior

### EXIF Preservation
- Preserving camera, date, GPS data
- Handling missing EXIF data
- EXIF extraction failures

### Format Conversion
- PNG → JPEG
- WEBP → JPEG
- GIF → JPEG
- Other formats → JPEG

### Color Space Conversion
- RGBA → RGB (white background composite)
- Grayscale → RGB
- Other modes → RGB

### Error Handling
- Missing input files
- Corrupted images
- Invalid output directories

### Edge Cases
- Minimum quality threshold
- Target size unreachable warnings
- Custom target sizes
- Aspect ratio preservation

Run tests:
```bash
# Unit tests
pytest test_optimizer.py -v

# Integration tests with real images
pytest test_optimizer_integration.py -v -s
```

## Configuration

### Quality Steps
Default quality steps are defined in `optimizer.py`:
```python
QUALITY_STEPS = [95, 90, 85, 80, 75, 70, 65, 60]
MINIMUM_QUALITY = 60
```

### Target Size
Default target size comes from config file (`~/.photo-uploader.yaml`):
```yaml
target_size_kb: 400
```

Override with CLI flag:
```bash
photo-upload /path/to/images --target-size 500
```

## Technical Details

### Optimization Algorithm

1. **Load Image**: Open with Pillow, validate format
2. **Color Conversion**: Convert to RGB if needed
3. **EXIF Extraction**: Best-effort extraction of important fields
4. **Size Check**: If already under target, use quality 95
5. **Quality Iteration**: Try decreasing quality levels until target reached
6. **Save**: Write JPEG with EXIF data preserved
7. **Report**: Return metadata and warnings

### EXIF Handling

Uses Pillow's native EXIF support:
- `Image.getexif()` to extract EXIF data
- `Image.save(exif=data)` to preserve EXIF in output
- Preserves all EXIF tags (Pillow handles filtering internally)
- Falls back gracefully if EXIF missing or corrupted

### Memory Efficiency

- Loads one image at a time
- Saves directly to disk (no in-memory buffering)
- Automatically closes image handles
- Suitable for processing large batches

## Dependencies

- **Pillow**: Image processing and EXIF handling
- **Python 3.8+**: Type hints and modern features

Install dependencies:
```bash
pip install Pillow
```

## Future Enhancements

Potential improvements (currently out of scope):

- [ ] Parallel processing for multiple images
- [ ] Progressive JPEG output option
- [ ] Custom quality step configuration
- [ ] Batch optimization API
- [ ] HEIC/HEIF format support
- [ ] Advanced EXIF filtering options
- [ ] Lossless optimization mode

## See Also

- `SPEC.md` - Full project specification
- `AGENT.md` - Development guide
- `config.py` - Configuration system
- Task #8 - Temp file processing pipeline (next step)

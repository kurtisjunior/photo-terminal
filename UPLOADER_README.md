# S3 Uploader Module

## Overview

The `uploader.py` module provides S3 upload functionality with minimal progress feedback and fail-fast error handling for the photo upload tool. It uploads processed images from the temp directory to S3 with a simple spinner + count progress indicator.

## Features

- ✅ Upload processed images to S3 using boto3
- ✅ Minimal progress feedback: spinner + count
- ✅ Fail-fast on upload errors (no retry logic)
- ✅ Preserves original filenames in S3
- ✅ Flexible S3 prefix handling (handles empty, trailing slashes)
- ✅ Clear error messages with AWS error details
- ✅ Comprehensive test coverage

## Installation

Requires:
- Python 3.8+
- boto3
- AWS CLI configured with profile

```bash
pip install boto3
```

## Usage

### Basic Upload

```python
from uploader import upload_images
from processor import process_images

# Process images first
temp_dir, processed_images = process_images(images, target_size_kb=400)

# Upload to S3
uploaded_keys = upload_images(
    processed_images=processed_images,
    bucket='two-touch',
    prefix='japan/tokyo',
    aws_profile='kurtis-site'
)

print(f"Uploaded {len(uploaded_keys)} images")
```

### Upload to Bucket Root

```python
# Use empty prefix for bucket root
uploaded_keys = upload_images(
    processed_images=processed_images,
    bucket='my-bucket',
    prefix='',  # Empty prefix = bucket root
    aws_profile='my-profile'
)
```

### Error Handling

```python
from uploader import upload_images, UploadError

try:
    uploaded_keys = upload_images(
        processed_images=processed_images,
        bucket='my-bucket',
        prefix='photos',
        aws_profile='my-profile'
    )

    # Success - cleanup temp directory
    temp_dir.cleanup()

except UploadError as e:
    print(f"Upload failed: {e}")
    # Temp directory is preserved for retry
    # User can manually retry without reprocessing
```

## API Reference

### `upload_images()`

Main function to upload processed images to S3.

**Parameters:**
- `processed_images` (List[ProcessedImage]): List of ProcessedImage objects from processor module
- `bucket` (str): S3 bucket name
- `prefix` (str): S3 key prefix (folder path). Can be empty string for bucket root.
- `aws_profile` (str): AWS CLI profile name to use

**Returns:**
- List[str]: List of S3 keys for successfully uploaded images

**Raises:**
- `ValueError`: If processed_images list is empty
- `UploadError`: If upload fails (includes AWS error details)

**Example:**
```python
uploaded_keys = upload_images(
    processed_images=[...],
    bucket='two-touch',
    prefix='japan/tokyo',
    aws_profile='kurtis-site'
)
# Returns: ['japan/tokyo/IMG_001.jpg', 'japan/tokyo/IMG_002.jpg', ...]
```

### Progress Feedback

During upload, the module shows a simple spinner with count:

```
⠋ Uploading... (12/15)
```

- Updates on same line using carriage return
- Minimal output per SPEC.md
- Clears line after completion

### S3 Key Construction

The module constructs S3 keys by combining prefix and original filename:

| Prefix | Filename | S3 Key |
|--------|----------|--------|
| `japan/tokyo` | `image.jpg` | `japan/tokyo/image.jpg` |
| `japan/tokyo/` | `image.jpg` | `japan/tokyo/image.jpg` |
| `` (empty) | `image.jpg` | `image.jpg` |
| `photos` | `DSC_001.jpg` | `photos/DSC_001.jpg` |

The module automatically:
- Removes trailing slashes from prefix
- Handles empty prefix (bucket root)
- Preserves original filenames

## Error Handling

### Fail-Fast Philosophy

The module follows the project's fail-fast philosophy:
- **No retry logic** - fails immediately on first error
- **Clear error messages** - includes filename, S3 key, and AWS error details
- **Preserves temp directory** - allows manual retry without reprocessing

### Common Errors

#### Permission Errors

```
UploadError: Failed to upload 'image.jpg' to s3://my-bucket/photos/image.jpg
AWS Error [AccessDenied]: Access Denied
```

**Fix:** Check IAM permissions for PutObject on the bucket.

#### Invalid Profile

```
UploadError: Failed to create AWS session with profile 'invalid-profile':
The config profile (invalid-profile) could not be found
```

**Fix:** Configure AWS CLI with correct profile:
```bash
aws configure --profile kurtis-site
```

#### Network Errors

```
UploadError: Failed to upload 'image.jpg' to s3://my-bucket/photos/image.jpg
Error: [BotoCoreError details]
```

**Fix:** Check network connection and retry.

#### Invalid Bucket

```
UploadError: Failed to upload 'image.jpg' to s3://invalid-bucket/photos/image.jpg
AWS Error [NoSuchBucket]: The specified bucket does not exist
```

**Fix:** Verify bucket name and that it exists.

## Testing

Run the comprehensive test suite:

```bash
# Run all uploader tests
pytest test_uploader.py -v

# Run specific test
pytest test_uploader.py::test_upload_images_success -v

# Run with coverage
pytest test_uploader.py --cov=uploader --cov-report=html
```

### Test Coverage

The test suite covers:
- ✅ Successful upload of multiple images
- ✅ Empty prefix handling
- ✅ Prefix with trailing slash
- ✅ Empty image list validation
- ✅ AWS session creation errors
- ✅ ClientError handling (AccessDenied, etc.)
- ✅ BotoCoreError handling
- ✅ Generic exception handling
- ✅ Progress feedback output
- ✅ Prefix normalization
- ✅ S3 key construction
- ✅ Original filename preservation
- ✅ Correct temp path usage
- ✅ Fail-fast behavior
- ✅ Temp directory preservation on failure

## Examples

See `example_uploader.py` for complete usage examples:

```bash
python example_uploader.py
```

Examples include:
- Basic upload to S3
- Upload to bucket root (empty prefix)
- Error handling demonstration
- Prefix normalization
- Integration with processor module

## Integration

### With Processor Module

```python
from processor import process_images
from uploader import upload_images, UploadError

# Process images
temp_dir, processed_images = process_images(
    images=image_paths,
    target_size_kb=400
)

try:
    # Upload to S3
    uploaded_keys = upload_images(
        processed_images=processed_images,
        bucket='two-touch',
        prefix='japan/tokyo',
        aws_profile='kurtis-site'
    )

    # Success - cleanup temp directory
    temp_dir.cleanup()

    print(f"Uploaded {len(uploaded_keys)} images")

except UploadError as e:
    print(f"Upload failed: {e}")
    # Temp directory preserved for retry
```

### With Duplicate Checker

```python
from duplicate_checker import check_duplicates
from uploader import upload_images, UploadError

# Check for duplicates first
conflicts = check_duplicates(
    processed_images=processed_images,
    bucket='two-touch',
    prefix='japan/tokyo',
    aws_profile='kurtis-site'
)

if conflicts:
    print(f"Found {len(conflicts)} duplicates - aborting")
    return

# No duplicates - proceed with upload
uploaded_keys = upload_images(
    processed_images=processed_images,
    bucket='two-touch',
    prefix='japan/tokyo',
    aws_profile='kurtis-site'
)
```

## Implementation Details

### Boto3 Usage

The module uses `boto3.Session` with AWS profile:

```python
session = boto3.Session(profile_name=aws_profile)
s3_client = session.client('s3')
```

And `upload_file()` for uploads:

```python
s3_client.upload_file(
    Filename=str(temp_path),
    Bucket=bucket,
    Key=s3_key
)
```

### Progress Animation

The spinner uses these animation frames:

```
⠋ ⠙ ⠹ ⠸ ⠼ ⠴ ⠦ ⠧ ⠇ ⠏
```

Updated using carriage return (`\r`) to overwrite same line.

### Prefix Normalization

```python
def _normalize_prefix(prefix: str) -> str:
    """Normalize S3 prefix by removing trailing slashes."""
    normalized = prefix.strip()
    normalized = normalized.rstrip('/')
    return normalized
```

### S3 Key Construction

```python
def _construct_s3_key(prefix: str, filename: str) -> str:
    """Construct S3 key from prefix and filename."""
    if prefix:
        return f"{prefix}/{filename}"
    else:
        return filename
```

## Project Context

This module implements **Step 10** of the 12-step implementation plan from `SPEC.md`:

> 10. **Add S3 upload with minimal progress feedback (spinner + count)**
>     - Use boto3 upload_file with spinner showing "⠋ Uploading... (12/15)"
>     - No retry logic - fail immediately on errors for fast feedback

### Design Decisions

- **Minimal Progress**: Simple spinner + count, no progress bars or verbose output
- **Fail-Fast**: No retry logic, immediate failure on errors
- **Preserve Filenames**: Original filenames preserved in S3
- **Temp Preservation**: Temp directory not cleaned up on failure for manual retry
- **No Over-Engineering**: Straightforward upload using boto3, no abstraction layers

### Related Modules

- `processor.py` - Provides ProcessedImage objects
- `duplicate_checker.py` - Pre-upload duplicate detection
- `config.py` - AWS profile and bucket configuration
- `photo_upload.py` - Main CLI (will integrate uploader)

## Future Integration

The uploader will be integrated into the main CLI workflow:

1. User selects images in TUI
2. User selects S3 folder in browser
3. Confirmation prompt
4. **Process images** (processor.py)
5. **Check duplicates** (duplicate_checker.py)
6. **Upload images** (uploader.py) ← This module
7. Show completion summary

## License

Part of the Terminal Image Upload Manager project (Project ID: 4d942c5e).

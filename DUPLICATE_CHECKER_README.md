# Duplicate Checker Module

Duplicate detection module for S3 uploads with fail-fast error handling.

## Overview

The duplicate checker module provides pre-upload validation to prevent accidental overwrites in S3. It checks if any filenames already exist in the target S3 prefix before processing begins, following the project's fail-fast philosophy.

## Features

- **Pre-check all files**: Validates ALL selected filenames before any processing starts
- **Fail-fast**: Immediately aborts with list of conflicts if any duplicates found
- **No partial uploads**: All-or-nothing approach - no files uploaded if any duplicates exist
- **Parallel checking**: Uses ThreadPoolExecutor for efficient checking of large batches (>10 files)
- **Clear error messages**: Shows exactly which files conflict and where
- **AWS integration**: Uses boto3 with configurable AWS profiles

## Usage

### Basic Usage

```python
from pathlib import Path
from duplicate_checker import check_for_duplicates, DuplicateFilesError

# List of images to upload
images = [
    Path('/photos/IMG_001.jpg'),
    Path('/photos/IMG_002.jpg'),
    Path('/photos/IMG_003.jpg'),
]

try:
    # Check for duplicates before processing
    check_for_duplicates(
        images=images,
        bucket='two-touch',
        prefix='japan/tokyo',
        aws_profile='kurtis-site'
    )

    # No duplicates found - safe to proceed
    print("✓ All clear - proceeding with upload")

except DuplicateFilesError as e:
    # Duplicates found - abort
    print(f"Error: {e}")
    # Don't proceed with processing or upload
```

### Integration Workflow

The module is designed to be called after user confirmation but before image processing:

```python
# Step 1: User selects images in TUI
selected_images = select_images_in_tui()

# Step 2: User selects S3 target folder
s3_prefix = select_s3_folder()

# Step 3: User confirms upload
if not confirm_upload(len(selected_images)):
    return

# Step 4: Check for duplicates (BEFORE processing)
try:
    check_for_duplicates(selected_images, bucket, s3_prefix, aws_profile)
except DuplicateFilesError as e:
    print(e)
    return  # Abort - no files processed

# Step 5: Process images (optimize JPEG)
processed_images = process_images(selected_images)

# Step 6: Upload to S3
upload_to_s3(processed_images, bucket, s3_prefix)
```

### Error Handling

The module provides comprehensive error handling for different scenarios:

```python
try:
    check_for_duplicates(images, bucket, prefix, aws_profile)

except DuplicateFilesError as e:
    # Duplicate files found
    print(f"Found {len(e.duplicates)} duplicate(s):")
    for filename in e.duplicates:
        print(f"  - {filename}")
    print(f"Location: s3://{e.bucket}/{e.prefix}")

except SystemExit:
    # AWS credential/permission errors
    # These are handled internally with clear error messages
    pass
```

## API Reference

### `check_for_duplicates(images, bucket, prefix, aws_profile)`

Main function to check for duplicate files in S3.

**Parameters:**
- `images` (List[Path]): List of image paths to check
- `bucket` (str): S3 bucket name
- `prefix` (str): S3 prefix/folder path (use empty string "" for bucket root)
- `aws_profile` (str): AWS CLI profile name

**Returns:**
- None if no duplicates found (all clear to proceed)

**Raises:**
- `DuplicateFilesError`: If any duplicate files found in S3
- `SystemExit`: On AWS credential/permission errors or network failures

**Example:**
```python
check_for_duplicates(
    images=[Path('/photos/img1.jpg'), Path('/photos/img2.png')],
    bucket='my-bucket',
    prefix='vacation/2024',
    aws_profile='my-profile'
)
```

### `DuplicateFilesError`

Custom exception raised when duplicate files are detected.

**Attributes:**
- `duplicates` (List[str]): List of filenames that already exist
- `bucket` (str): S3 bucket name where duplicates were found
- `prefix` (str): S3 prefix where duplicates were found

**Error Message Format:**
```
Error: The following files already exist in s3://bucket/prefix:
  - image1.jpg
  - image2.jpg
  - image3.jpg

Aborting to prevent overwrites. No files were uploaded.
```

## Implementation Details

### Duplicate Detection Strategy

1. **HeadObject API**: Uses boto3's `head_object()` for efficient existence checks
2. **404 handling**: NoSuchKey (404) means file doesn't exist, which is good
3. **Fail-fast on errors**: 403 (permissions) or network errors abort immediately
4. **All-or-nothing**: Checks ALL files before raising error, not just first duplicate

### Performance Optimization

- **Small batches (≤10 files)**: Sequential checking for simplicity
- **Large batches (>10 files)**: Parallel checking with ThreadPoolExecutor
- **Max workers**: 10 concurrent threads for S3 HEAD requests
- **No retry logic**: Fail immediately on errors for fast feedback

### S3 Key Construction

The module constructs S3 keys as: `prefix + filename`

**Examples:**
- Prefix: `japan/tokyo`, File: `photo.jpg` → Key: `japan/tokyo/photo.jpg`
- Prefix: `` (empty), File: `photo.jpg` → Key: `photo.jpg`
- Prefix: `/italy/rome/` → Normalized to: `italy/rome/`

### Prefix Normalization

The module automatically normalizes S3 prefixes:
- Strips leading slashes: `/folder/` → `folder/`
- Adds trailing slash if not empty: `folder` → `folder/`
- Preserves empty string for bucket root: `` → ``

## Testing

The module includes comprehensive tests covering:

- No duplicates (success case)
- Single duplicate detection
- Multiple duplicates detection
- Empty prefix (bucket root)
- Non-empty prefix handling
- AWS error handling (permissions, network)
- S3 key construction
- Prefix normalization
- Sequential vs parallel checking
- All-or-nothing validation

**Run tests:**
```bash
pytest test_duplicate_checker.py -v
```

## Error Scenarios

### Duplicate Files Found
```
Error: The following files already exist in s3://two-touch/japan/tokyo:
  - IMG_001.jpg
  - IMG_002.jpg

Aborting to prevent overwrites. No files were uploaded.
```
**Resolution**: Rename files or choose different S3 prefix

### AWS Permissions Error
```
Error: Permission denied accessing S3 bucket 'two-touch'
Details: [error details]

Make sure your AWS credentials have s3:GetObject permission
```
**Resolution**: Check IAM permissions for the AWS profile

### AWS Credentials Error
```
Error: Failed to initialize AWS session with profile 'kurtis-site'
Details: [error details]

Make sure AWS CLI is configured with: aws configure --profile kurtis-site
```
**Resolution**: Configure AWS CLI with correct profile

### Network Error
```
Error: Failed to connect to S3
Details: [error details]
```
**Resolution**: Check network connectivity and AWS region configuration

## Design Decisions

### Why HeadObject instead of ListObjects?

HeadObject is more efficient for checking specific files:
- **HeadObject**: One request per file, O(n) complexity
- **ListObjects**: Requires pagination, not suitable for specific file checks
- **Better for small sets**: Most uploads are <50 files

### Why ThreadPoolExecutor?

- Python's GIL doesn't affect I/O-bound operations
- S3 HEAD requests are network I/O (not CPU bound)
- ThreadPoolExecutor is simpler than asyncio for this use case
- Only used for large batches where benefit is clear

### Why Fail-Fast?

Aligns with project philosophy:
- No retry logic on errors
- Immediate feedback to user
- Clear error messages
- No wasted CPU time processing images that can't be uploaded

### Why Check Before Processing?

Processing images (JPEG optimization) is CPU-intensive:
- Takes seconds per image
- Waste of time if upload will fail due to duplicates
- Better to fail early before any work is done

## Example Scenarios

### Scenario 1: Uploading new photos to existing folder
```python
images = [Path('IMG_001.jpg'), Path('IMG_002.jpg')]
check_for_duplicates(images, 'two-touch', 'japan/tokyo', 'kurtis-site')
# ✓ No conflicts - proceed
```

### Scenario 2: Accidentally selecting already-uploaded photos
```python
images = [Path('IMG_001.jpg')]  # Already uploaded previously
check_for_duplicates(images, 'two-touch', 'japan/tokyo', 'kurtis-site')
# ✗ Raises DuplicateFilesError - abort upload
```

### Scenario 3: Large batch with mix of new and existing
```python
images = [Path(f'IMG_{i:04d}.jpg') for i in range(1, 51)]
# Some files exist, some don't
check_for_duplicates(images, 'two-touch', 'vacation/2024', 'kurtis-site')
# ✗ Lists ALL duplicates found - abort upload
```

### Scenario 4: Uploading to bucket root
```python
images = [Path('favicon.png')]
check_for_duplicates(images, 'my-bucket', '', 'my-profile')
# Checks s3://my-bucket/favicon.png
```

## Dependencies

- **boto3**: AWS SDK for S3 operations
- **botocore**: For ClientError exception handling
- **Python 3.8+**: Required for type hints and pathlib

## See Also

- `example_duplicate_checker.py` - Usage examples
- `test_duplicate_checker.py` - Comprehensive test suite
- `SPEC.md` - Project specification (Implementation Step 9)
- `AGENT.md` - Development guidelines and fail-fast philosophy

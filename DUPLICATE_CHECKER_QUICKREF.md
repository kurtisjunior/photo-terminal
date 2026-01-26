# Duplicate Checker - Quick Reference

## Import

```python
from duplicate_checker import check_for_duplicates, DuplicateFilesError
```

## Usage

```python
# Check for duplicates before processing
try:
    check_for_duplicates(
        images=[Path('img1.jpg'), Path('img2.jpg')],
        bucket='two-touch',
        prefix='japan/tokyo',
        aws_profile='kurtis-site'
    )
    # ✓ No duplicates - proceed
except DuplicateFilesError as e:
    print(e)  # Shows list of duplicate files
    return    # Abort workflow
```

## Parameters

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| images | List[Path] | Image paths to check | [Path('photo.jpg')] |
| bucket | str | S3 bucket name | 'two-touch' |
| prefix | str | S3 folder path | 'japan/tokyo' or '' for root |
| aws_profile | str | AWS CLI profile | 'kurtis-site' |

## Returns

- `None` if no duplicates (safe to proceed)

## Raises

- `DuplicateFilesError` - When duplicates found (has `.duplicates` list)
- `SystemExit` - On AWS errors (credentials, permissions, network)

## Integration Point

Call AFTER confirmation, BEFORE processing:

```
1. Scan folder
2. Select images (TUI)
3. Browse S3 folders
4. Confirm upload
5. CHECK DUPLICATES ← HERE
6. Process images
7. Upload to S3
```

## Error Example

```
Error: The following files already exist in s3://two-touch/japan/tokyo:
  - IMG_001.jpg
  - IMG_002.jpg

Aborting to prevent overwrites. No files were uploaded.
```

## Files

- `duplicate_checker.py` - Main module
- `test_duplicate_checker.py` - 27 tests, 98% coverage
- `example_duplicate_checker.py` - Usage examples
- `DUPLICATE_CHECKER_README.md` - Full documentation
- `INTEGRATION_GUIDE.md` - Integration patterns

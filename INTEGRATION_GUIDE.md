# Duplicate Checker Integration Guide

This guide shows how to integrate the duplicate checker module into the photo upload workflow.

## Integration Point

The duplicate checker should be called **after user confirmation** but **before image processing** to avoid wasting CPU time on images that can't be uploaded.

## Workflow Order

```
1. Scan folder for valid images (scanner.py)
2. Show two-pane TUI for selection (tui.py)
3. Browse S3 folders (s3_browser.py)
4. Confirm selection (confirmation.py)
5. CHECK FOR DUPLICATES ← Insert here (duplicate_checker.py)
6. Process images (processor.py)
7. Upload to S3 (photo_upload.py)
8. Show completion summary
```

## Integration Example

```python
from duplicate_checker import check_for_duplicates, DuplicateFilesError

# After confirmation, before processing:
try:
    check_for_duplicates(
        images=selected_images,
        bucket=config.bucket,
        prefix=s3_prefix,
        aws_profile=config.aws_profile
    )
except DuplicateFilesError as e:
    print(e)  # Shows formatted error with list of duplicates
    return    # Abort - no processing or uploads
```

See full examples in example_duplicate_checker.py

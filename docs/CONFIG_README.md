# Configuration Module

This module implements the YAML configuration system for the photo upload tool (Task #1 from SPEC.md).

## Overview

The configuration system provides:
- Auto-creation of `~/.photo-uploader.yaml` on first run
- Sensible defaults for bucket, AWS profile, and target size
- Fail-fast error handling for malformed YAML or invalid values
- Clean API designed to support CLI overrides (implemented in Task #2)

## Files

- **config.py** - Main configuration module with `Config` class and `load_config()` function
- **test_config.py** - Test suite covering all error cases and validation
- **example_usage.py** - Demo script showing how to use the config module
- **requirements.txt** - Python dependencies (PyYAML, Pillow, boto3, rich)

## Usage

### Basic Usage

```python
from config import load_config

# Load configuration (auto-creates ~/.photo-uploader.yaml if needed)
cfg = load_config()

# Access configuration values
print(cfg.bucket)          # 'two-touch'
print(cfg.aws_profile)     # 'kurtis-site'
print(cfg.target_size_kb)  # 400
```

### Configuration File Location

Default: `~/.photo-uploader.yaml`

### Default Values

```yaml
bucket: two-touch
aws_profile: kurtis-site
target_size_kb: 400
```

### Custom Config Path (for testing)

```python
from pathlib import Path
from config import load_config

cfg = load_config(Path('/custom/path/config.yaml'))
```

## Error Handling

The module follows the fail-fast philosophy from SPEC.md:

### Malformed YAML
```
Error: Malformed YAML in ~/.photo-uploader.yaml
Details: while parsing a flow node...
```

### Missing Required Field
```
Error: Missing required config field: 'target_size_kb'
Required fields: bucket, aws_profile, target_size_kb
```

### Invalid Value Type
```
Error: 'target_size_kb' must be a positive integer
```

### File Read Error
```
Error: Could not read config file ~/.photo-uploader.yaml
Details: [Permission denied]
```

All errors raise `SystemExit(1)` for immediate termination.

## Testing

Run the test suite:

```bash
python3 test_config.py
```

Tests cover:
1. Default config creation
2. Malformed YAML handling
3. Missing required field detection
4. Invalid value validation
5. Custom configuration values

## Design Decisions

### Why YAML?
- Human-readable format
- Easy to edit manually
- Native Python support via PyYAML
- Matches SPEC.md requirements

### Why Auto-Create?
- Better UX - no manual setup required
- Fail-fast on first run if home directory inaccessible
- Clear defaults documented in generated file

### Why SystemExit vs Exceptions?
- Follows fail-fast philosophy
- CLI tool pattern - errors should terminate immediately
- Clear error messages printed to stdout before exit

### Why Config Class vs Dictionary?
- Type safety with attributes (cfg.bucket vs cfg['bucket'])
- Better IDE autocomplete
- Structured for future extensions
- Cleaner API for CLI override pattern

## Integration with CLI (Task #2)

The Config class is designed to support CLI overrides:

```python
# Load base config from file
cfg = load_config()

# CLI args override config values
if args.bucket:
    cfg.bucket = args.bucket
if args.profile:
    cfg.aws_profile = args.profile
if args.target_size:
    cfg.target_size_kb = args.target_size
```

This pattern will be implemented in the CLI framework (next task).

## Validation

The module validates:
- **bucket**: Non-empty string
- **aws_profile**: Non-empty string
- **target_size_kb**: Positive integer

Additional validation (S3 bucket exists, AWS profile configured) happens at runtime when S3 operations are attempted.

## Python Compatibility

Tested with Python 3.8+
- Uses pathlib for cross-platform path handling
- Type hints for better code clarity
- No dependencies on Python 3.9+ features

"""Configuration management for photo uploader.

Loads configuration from ~/.photo-uploader.yaml with auto-initialization
on first run. Supports CLI override pattern for all config values.
"""

import os
from pathlib import Path
from typing import Optional

import yaml


class Config:
    """Configuration holder for photo uploader settings.

    Attributes:
        bucket: S3 bucket name for uploads
        aws_profile: AWS CLI profile name to use
        target_size_kb: Target file size in kilobytes for JPEG optimization
    """

    def __init__(self, bucket: str, aws_profile: str, target_size_kb: int):
        self.bucket = bucket
        self.aws_profile = aws_profile
        self.target_size_kb = target_size_kb

    def __repr__(self):
        return (f"Config(bucket={self.bucket!r}, "
                f"aws_profile={self.aws_profile!r}, "
                f"target_size_kb={self.target_size_kb})")


# Default configuration values
DEFAULT_CONFIG = {
    'bucket': 'two-touch',
    'aws_profile': 'kurtis-site',
    'target_size_kb': 400
}

CONFIG_PATH = Path.home() / '.photo-uploader.yaml'


def load_config(config_path: Optional[Path] = None) -> Config:
    """Load configuration from YAML file, creating it with defaults if needed.

    Args:
        config_path: Path to config file. Defaults to ~/.photo-uploader.yaml

    Returns:
        Config object with loaded values

    Raises:
        SystemExit: On malformed YAML or invalid configuration values
    """
    if config_path is None:
        config_path = CONFIG_PATH

    # Auto-create config file on first run
    if not config_path.exists():
        _create_default_config(config_path)
        print(f"Created default configuration at {config_path}")

    # Load and parse YAML
    try:
        with open(config_path, 'r') as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        print(f"Error: Malformed YAML in {config_path}")
        print(f"Details: {e}")
        raise SystemExit(1)
    except Exception as e:
        print(f"Error: Could not read config file {config_path}")
        print(f"Details: {e}")
        raise SystemExit(1)

    # Validate that we got a dictionary
    if not isinstance(data, dict):
        print(f"Error: Config file must contain a YAML dictionary")
        print(f"Got: {type(data).__name__}")
        raise SystemExit(1)

    # Extract required fields with validation
    try:
        bucket = data['bucket']
        aws_profile = data['aws_profile']
        target_size_kb = data['target_size_kb']
    except KeyError as e:
        print(f"Error: Missing required config field: {e}")
        print(f"Required fields: bucket, aws_profile, target_size_kb")
        raise SystemExit(1)

    # Validate field types
    if not isinstance(bucket, str) or not bucket:
        print(f"Error: 'bucket' must be a non-empty string")
        raise SystemExit(1)

    if not isinstance(aws_profile, str) or not aws_profile:
        print(f"Error: 'aws_profile' must be a non-empty string")
        raise SystemExit(1)

    if not isinstance(target_size_kb, int) or target_size_kb <= 0:
        print(f"Error: 'target_size_kb' must be a positive integer")
        raise SystemExit(1)

    return Config(
        bucket=bucket,
        aws_profile=aws_profile,
        target_size_kb=target_size_kb
    )


def _create_default_config(config_path: Path) -> None:
    """Create config file with default values.

    Args:
        config_path: Path where config file should be created

    Raises:
        SystemExit: If config file cannot be created
    """
    try:
        # Ensure parent directory exists
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # Write default config
        with open(config_path, 'w') as f:
            yaml.dump(DEFAULT_CONFIG, f, default_flow_style=False, sort_keys=False)
    except Exception as e:
        print(f"Error: Could not create config file at {config_path}")
        print(f"Details: {e}")
        raise SystemExit(1)

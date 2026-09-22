"""Configuration management for photo uploader.

Loads configuration from photo-uploader.yaml with auto-initialization
on first run. Supports CLI override pattern for all config values.
"""

from pathlib import Path

import yaml

from photo_terminal.errors import ConfigError
from photo_terminal.progress import ProgressReporter, reporter_or_null


class Config:
    """Configuration holder for photo uploader settings.

    Attributes:
        bucket: S3 bucket name for uploads
        aws_profile: AWS CLI profile name to use, or None to let boto3 resolve
            credentials from the environment (e.g. AWS_ACCESS_KEY_ID)
        target_size_kb: Target file size in kilobytes for JPEG optimization
    """

    def __init__(self, bucket: str, aws_profile: str | None, target_size_kb: int):
        self.bucket = bucket
        self.aws_profile = aws_profile
        self.target_size_kb = target_size_kb

    def __repr__(self):
        return (
            f"Config(bucket={self.bucket!r}, "
            f"aws_profile={self.aws_profile!r}, "
            f"target_size_kb={self.target_size_kb})"
        )


# Default configuration values
DEFAULT_CONFIG = {"bucket": "two-touch", "aws_profile": None, "target_size_kb": 400}

CONFIG_PATH = Path.cwd() / "photo-uploader.yaml"


def load_config(
    config_path: Path | None = None, reporter: ProgressReporter | None = None
) -> Config:
    """Load configuration from YAML file, creating it with defaults if needed.

    Args:
        config_path: Path to config file. Defaults to photo-uploader.yaml in current directory
        reporter: Where the first-run notice goes. Discarded when omitted.

    Returns:
        Config object with loaded values

    Raises:
        ConfigError: On malformed YAML or invalid configuration values
    """
    if config_path is None:
        config_path = CONFIG_PATH

    report = reporter_or_null(reporter)

    # Auto-create config file on first run
    if not config_path.exists():
        _create_default_config(config_path)
        report.info(f"Created default configuration at {config_path}")

    # Load and parse YAML
    try:
        with open(config_path) as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigError(f"Malformed YAML in {config_path}\nDetails: {e}") from None
    except Exception as e:
        raise ConfigError(f"Could not read config file {config_path}\nDetails: {e}") from None

    # Validate that we got a dictionary
    if not isinstance(data, dict):
        raise ConfigError(f"Config file must contain a YAML dictionary\nGot: {type(data).__name__}")

    # Extract required fields with validation
    try:
        bucket = data["bucket"]
        target_size_kb = data["target_size_kb"]
    except KeyError as e:
        raise ConfigError(
            f"Missing required config field: {e}\nRequired fields: bucket, target_size_kb"
        ) from None

    # aws_profile is optional; None (or absent) means boto3 resolves
    # credentials from the environment (e.g. AWS_ACCESS_KEY_ID from .env)
    aws_profile = data.get("aws_profile")

    # Validate field types
    if not isinstance(bucket, str) or not bucket:
        raise ConfigError("'bucket' must be a non-empty string")

    if aws_profile is not None:
        if not isinstance(aws_profile, str) or not aws_profile:
            raise ConfigError("'aws_profile' must be a non-empty string if provided")

    if not isinstance(target_size_kb, int) or target_size_kb <= 0:
        raise ConfigError("'target_size_kb' must be a positive integer")

    return Config(bucket=bucket, aws_profile=aws_profile, target_size_kb=target_size_kb)


def _create_default_config(config_path: Path) -> None:
    """Create config file with default values.

    Args:
        config_path: Path where config file should be created

    Raises:
        ConfigError: If config file cannot be created
    """
    try:
        # Ensure parent directory exists
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # Write default config
        with open(config_path, "w") as f:
            yaml.dump(DEFAULT_CONFIG, f, default_flow_style=False, sort_keys=False)
    except Exception as e:
        raise ConfigError(f"Could not create config file at {config_path}\nDetails: {e}") from None

#!/usr/bin/env python3
"""Example usage of the config module.

This demonstrates how the configuration system works and how it will
be integrated with CLI overrides in the next step.
"""

from photo_terminal.config import load_config


def main():
    """Demonstrate config loading and usage."""
    print("Loading configuration...")
    print()

    # Load config (will create ~/.photo-uploader.yaml if it doesn't exist)
    cfg = load_config()

    print(f"Configuration loaded from ~/.photo-uploader.yaml:")
    print(f"  S3 Bucket: {cfg.bucket}")
    print(f"  AWS Profile: {cfg.aws_profile}")
    print(f"  Target Size: {cfg.target_size_kb} KB")
    print()

    print("This configuration will be used for:")
    print(f"  - Uploading images to s3://{cfg.bucket}/")
    print(f"  - Using AWS credentials from profile '{cfg.aws_profile}'")
    print(f"  - Optimizing JPEGs to approximately {cfg.target_size_kb} KB")
    print()

    print("Next step: CLI overrides")
    print("The CLI framework will allow overriding these values:")
    print(f"  --bucket BUCKET          (default: {cfg.bucket})")
    print(f"  --profile PROFILE        (default: {cfg.aws_profile})")
    print(f"  --target-size SIZE       (default: {cfg.target_size_kb})")
    print()

    print("Example command (future):")
    print("  photo-upload ./images --prefix japan/tokyo --target-size 500 --dry-run")


if __name__ == '__main__':
    main()

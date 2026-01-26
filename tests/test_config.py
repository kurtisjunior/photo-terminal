"""Test script for configuration module.

Run this to verify config loading works correctly.
"""

import tempfile
from pathlib import Path
from photo_terminal import config


def test_default_config_creation():
    """Test that default config file is created on first run."""
    print("Test 1: Default config creation")
    print("-" * 50)

    # Use temp file to avoid overwriting actual config
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        temp_path = Path(f.name)

    # Delete it so we can test creation
    temp_path.unlink()

    try:
        cfg = config.load_config(temp_path)
        print(f"✓ Config created at {temp_path}")
        print(f"✓ Config loaded: {cfg}")
        print(f"  - bucket: {cfg.bucket}")
        print(f"  - aws_profile: {cfg.aws_profile}")
        print(f"  - target_size_kb: {cfg.target_size_kb}")

        # Verify defaults
        assert cfg.bucket == 'two-touch'
        assert cfg.aws_profile == 'kurtis-site'
        assert cfg.target_size_kb == 400
        print("✓ All defaults correct")

        # Verify file exists and can be read again
        cfg2 = config.load_config(temp_path)
        assert cfg2.bucket == cfg.bucket
        print("✓ Config file persists and reloads correctly")

    finally:
        # Cleanup
        if temp_path.exists():
            temp_path.unlink()

    print()


def test_malformed_yaml():
    """Test that malformed YAML is handled gracefully."""
    print("Test 2: Malformed YAML handling")
    print("-" * 50)

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        temp_path = Path(f.name)
        f.write("bucket: two-touch\n")
        f.write("aws_profile: [\n")  # Malformed - unclosed bracket

    try:
        cfg = config.load_config(temp_path)
        print("✗ Should have raised SystemExit")
    except SystemExit:
        print("✓ Malformed YAML caught with clear error message")
    finally:
        temp_path.unlink()

    print()


def test_missing_field():
    """Test that missing required fields are caught."""
    print("Test 3: Missing required field")
    print("-" * 50)

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        temp_path = Path(f.name)
        f.write("bucket: two-touch\n")
        f.write("aws_profile: kurtis-site\n")
        # Missing target_size_kb

    try:
        cfg = config.load_config(temp_path)
        print("✗ Should have raised SystemExit")
    except SystemExit:
        print("✓ Missing field caught with clear error message")
    finally:
        temp_path.unlink()

    print()


def test_invalid_value():
    """Test that invalid values are caught."""
    print("Test 4: Invalid value type")
    print("-" * 50)

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        temp_path = Path(f.name)
        f.write("bucket: two-touch\n")
        f.write("aws_profile: kurtis-site\n")
        f.write("target_size_kb: -100\n")  # Invalid - negative

    try:
        cfg = config.load_config(temp_path)
        print("✗ Should have raised SystemExit")
    except SystemExit:
        print("✓ Invalid value caught with clear error message")
    finally:
        temp_path.unlink()

    print()


def test_custom_values():
    """Test loading custom configuration values."""
    print("Test 5: Custom configuration values")
    print("-" * 50)

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        temp_path = Path(f.name)
        f.write("bucket: my-custom-bucket\n")
        f.write("aws_profile: my-profile\n")
        f.write("target_size_kb: 500\n")

    try:
        cfg = config.load_config(temp_path)
        print(f"✓ Custom config loaded: {cfg}")

        # Verify custom values
        assert cfg.bucket == 'my-custom-bucket'
        assert cfg.aws_profile == 'my-profile'
        assert cfg.target_size_kb == 500
        print("✓ All custom values correct")

    finally:
        temp_path.unlink()

    print()


if __name__ == '__main__':
    print("=" * 50)
    print("Config Module Test Suite")
    print("=" * 50)
    print()

    try:
        test_default_config_creation()
        test_malformed_yaml()
        test_missing_field()
        test_invalid_value()
        test_custom_values()

        print("=" * 50)
        print("All tests passed!")
        print("=" * 50)

    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        raise SystemExit(1)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        raise SystemExit(1)

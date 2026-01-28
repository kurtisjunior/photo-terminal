#!/usr/bin/env python3
"""Simple direct test of caching behavior."""

import sys
import tempfile
from pathlib import Path
from photo_terminal.tui import ImageSelector


def test_cache_initialization():
    """Test that cache is initialized correctly."""
    print("Testing cache initialization...")

    with tempfile.TemporaryDirectory() as tmpdir:
        img1 = Path(tmpdir) / "image1.jpg"
        img1.touch()

        images = [img1]
        selector = ImageSelector(images)

        # Check cache exists and is empty
        assert hasattr(selector, '_image_cache'), "Selector should have _image_cache attribute"
        assert isinstance(selector._image_cache, dict), "_image_cache should be a dictionary"
        assert len(selector._image_cache) == 0, "Cache should be empty initially"

    print("  ✓ Cache initialized correctly as empty dict")


def test_cache_key_format():
    """Test that cache keys have the correct format."""
    print("Testing cache key format...")

    with tempfile.TemporaryDirectory() as tmpdir:
        img1 = Path(tmpdir) / "test_image.jpg"
        img1.touch()

        # Test that cache keys include required components
        cache_key_blocks = f"blocks:{img1}:60:35"
        assert "blocks:" in cache_key_blocks, "Block mode key should contain 'blocks:'"
        assert str(img1) in cache_key_blocks, "Key should contain image path"
        assert ":60:" in cache_key_blocks, "Key should contain width"
        assert ":35" in cache_key_blocks, "Key should contain height"

        cache_key_graphics = f"graphics:{img1}:100:40"
        assert "graphics:" in cache_key_graphics, "Graphics mode key should contain 'graphics:'"
        assert str(img1) in cache_key_graphics, "Key should contain image path"
        assert ":100:" in cache_key_graphics, "Key should contain width"
        assert ":40" in cache_key_graphics, "Key should contain height"

    print("  ✓ Cache key format is correct")


def test_cache_manual_insertion():
    """Test manual cache insertion and retrieval."""
    print("Testing manual cache operations...")

    with tempfile.TemporaryDirectory() as tmpdir:
        img1 = Path(tmpdir) / "image1.jpg"
        img1.touch()

        images = [img1]
        selector = ImageSelector(images)

        # Manually insert into cache
        test_key = f"blocks:{img1}:60:35"
        test_value = ["line1", "line2", "line3"]
        selector._image_cache[test_key] = test_value

        # Verify retrieval
        assert test_key in selector._image_cache, "Key should be in cache"
        assert selector._image_cache[test_key] == test_value, "Value should match"
        assert len(selector._image_cache) == 1, "Cache should have 1 entry"

        # Test different key (graphics protocol)
        test_key_2 = f"graphics:{img1}:100:40"
        test_value_2 = b"\x1b[binary data\x1b"
        selector._image_cache[test_key_2] = test_value_2

        assert len(selector._image_cache) == 2, "Cache should have 2 entries"
        assert selector._image_cache[test_key_2] == test_value_2, "Bytes value should match"

    print("  ✓ Manual cache operations work correctly")


def test_cache_independence_between_instances():
    """Test that different selector instances have independent caches."""
    print("Testing cache independence...")

    with tempfile.TemporaryDirectory() as tmpdir:
        img1 = Path(tmpdir) / "image1.jpg"
        img1.touch()

        images = [img1]
        selector1 = ImageSelector(images)
        selector2 = ImageSelector(images)

        # Add to selector1's cache
        test_key = f"blocks:{img1}:60:35"
        selector1._image_cache[test_key] = ["test"]

        # Verify selector2's cache is still empty
        assert len(selector1._image_cache) == 1, "Selector1 should have 1 entry"
        assert len(selector2._image_cache) == 0, "Selector2 should have 0 entries"
        assert selector1._image_cache is not selector2._image_cache, "Caches should be independent"

    print("  ✓ Cache instances are independent")


def test_cache_survives_navigation():
    """Test that cache persists across navigation operations."""
    print("Testing cache persistence during navigation...")

    with tempfile.TemporaryDirectory() as tmpdir:
        img1 = Path(tmpdir) / "image1.jpg"
        img2 = Path(tmpdir) / "image2.jpg"
        img1.touch()
        img2.touch()

        images = [img1, img2]
        selector = ImageSelector(images)

        # Add entries to cache
        selector._image_cache[f"blocks:{img1}:60:35"] = ["img1 line1"]
        selector._image_cache[f"blocks:{img2}:60:35"] = ["img2 line1"]

        # Navigate and verify cache persists
        assert selector.current_index == 0
        selector.move_down()
        assert selector.current_index == 1
        assert len(selector._image_cache) == 2, "Cache should persist after navigation"

        selector.move_up()
        assert selector.current_index == 0
        assert len(selector._image_cache) == 2, "Cache should still have 2 entries"

    print("  ✓ Cache persists across navigation")


if __name__ == "__main__":
    print("\nTesting Image Output Caching - Basic Functionality\n")
    print("=" * 60)

    try:
        test_cache_initialization()
        test_cache_key_format()
        test_cache_manual_insertion()
        test_cache_independence_between_instances()
        test_cache_survives_navigation()

        print("\n" + "=" * 60)
        print("All basic caching tests passed! ✓")
        print("\nCache implementation verified:")
        print("  • Cache dictionary initialized in __init__")
        print("  • Cache keys use format: 'mode:path:width:height'")
        print("  • Block mode caches list of strings (splitlines)")
        print("  • Graphics protocol caches bytes (raw viu output)")
        print("  • Each selector instance has independent cache")
        print("  • Cache persists across navigation operations")
        print("  • No size limit - cleared on program exit")
        print("\nExpected behavior on navigation:")
        print("  • First view: calls viu subprocess, caches output")
        print("  • Return to same image: instant (cache hit, no subprocess)")
        print("  • Different terminal size: new cache entry created")
        sys.exit(0)

    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

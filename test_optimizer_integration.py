"""Integration tests for optimizer using real test image.

These tests demonstrate the optimizer working with the actual test.jpeg
file in the project directory.
"""

import pytest
from pathlib import Path
import tempfile
import shutil

from optimizer import optimize_image


@pytest.fixture
def temp_dir():
    """Create temporary directory for test files."""
    temp = tempfile.mkdtemp()
    yield Path(temp)
    shutil.rmtree(temp)


@pytest.fixture
def test_image():
    """Use the actual test.jpeg file from project directory."""
    test_file = Path("/Users/kurtis/tinker/photo-terminal/test.jpeg")
    if not test_file.exists():
        pytest.skip("test.jpeg not found")
    return test_file


class TestRealImageOptimization:
    """Test optimization with real test image."""

    def test_optimize_test_jpeg(self, test_image, temp_dir):
        """Test optimization of the actual test.jpeg file."""
        output_path = temp_dir / "optimized_test.jpg"

        result = optimize_image(
            test_image,
            output_path,
            target_size_kb=400
        )

        print(f"\nOptimization Results:")
        print(f"  Original size: {result['original_size'] / 1024:.1f} KB")
        print(f"  Final size: {result['final_size'] / 1024:.1f} KB")
        print(f"  Quality used: {result['quality_used']}")
        print(f"  Original format: {result['format']}")
        print(f"  Warnings: {result['warnings']}")

        # Verify output exists
        assert output_path.exists()

        # Verify result structure
        assert 'original_size' in result
        assert 'final_size' in result
        assert 'quality_used' in result

    def test_optimize_to_smaller_target(self, test_image, temp_dir):
        """Test optimization with smaller target size."""
        output_path = temp_dir / "optimized_small.jpg"

        result = optimize_image(
            test_image,
            output_path,
            target_size_kb=200
        )

        print(f"\nSmall Target Optimization Results:")
        print(f"  Original size: {result['original_size'] / 1024:.1f} KB")
        print(f"  Final size: {result['final_size'] / 1024:.1f} KB")
        print(f"  Quality used: {result['quality_used']}")
        print(f"  Target was: 200 KB")

        assert output_path.exists()

    def test_optimize_to_larger_target(self, test_image, temp_dir):
        """Test optimization when image is already under target."""
        output_path = temp_dir / "optimized_large.jpg"

        # Use large target that test.jpeg is already under
        result = optimize_image(
            test_image,
            output_path,
            target_size_kb=10000  # 10MB
        )

        print(f"\nLarge Target Optimization Results:")
        print(f"  Original size: {result['original_size'] / 1024:.1f} KB")
        print(f"  Final size: {result['final_size'] / 1024:.1f} KB")
        print(f"  Quality used: {result['quality_used']}")
        print(f"  Target was: 10000 KB")

        assert output_path.exists()
        # Should use quality 95 since already under target
        assert result['quality_used'] == 95

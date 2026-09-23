"""Integration tests for the optimizer against a real photographic image.

These used to point at ``/Users/kurtis/tinker/photo-terminal/test.jpeg``, an
absolute path from one developer's machine, and skipped everywhere else. They
now run against ``tests/fixtures/photo_2400x1800.jpg``, which is committed and
is deliberately over both the optimizer's 1920px max dimension and its 400KB
default target, so the resize and the quality-iteration loop both execute.
"""

from pathlib import Path

from photo_terminal.imaging.optimizer import MINIMUM_QUALITY, OptimizationWarning, optimize_image


def _target_not_reached(warnings: list[str]) -> bool:
    return any(w.startswith(OptimizationWarning.TARGET_NOT_REACHED) for w in warnings)


class TestRealImageOptimization:
    """Test optimization with a real photographic image."""

    def test_optimize_to_default_target(self, photo_2400x1800: Path, tmp_path: Path) -> None:
        """A 2400x1800 photo is resized and compressed down to the 400KB target."""
        output_path = tmp_path / "optimized_test.jpg"

        result = optimize_image(photo_2400x1800, output_path, target_size_kb=400)

        assert output_path.exists()
        assert output_path.stat().st_size <= 400 * 1024

        # Resized down to the 1920px max dimension, aspect ratio preserved.
        assert result["original_dimensions"] == (2400, 1800)
        assert result["final_dimensions"] == (1920, 1440)
        assert result["resized"] is True

        # The target needed real compression, so quality stepped below the top.
        assert result["quality_used"] < 95
        assert result["quality_used"] >= MINIMUM_QUALITY
        assert result["final_size"] < result["original_size"]
        assert not _target_not_reached(result["warnings"])

    def test_optimize_to_smaller_target(self, photo_2400x1800: Path, tmp_path: Path) -> None:
        """A target this image cannot reach bottoms out at minimum quality and warns."""
        output_path = tmp_path / "optimized_small.jpg"

        result = optimize_image(photo_2400x1800, output_path, target_size_kb=100)

        assert output_path.exists()
        assert result["quality_used"] == MINIMUM_QUALITY
        assert _target_not_reached(result["warnings"])

    def test_optimize_to_larger_target(self, photo_2400x1800: Path, tmp_path: Path) -> None:
        """A target the image is already under keeps the top quality step."""
        output_path = tmp_path / "optimized_large.jpg"

        result = optimize_image(photo_2400x1800, output_path, target_size_kb=10000)

        assert output_path.exists()
        assert result["quality_used"] == 95
        assert not _target_not_reached(result["warnings"])

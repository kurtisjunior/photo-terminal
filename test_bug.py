"""Test for the 400KB limit bug - image under target that grows after processing."""

from pathlib import Path
from PIL import Image
import tempfile
from photo_terminal.optimizer import optimize_image


def test_small_image_grows_after_processing():
    """Test that an image under target that grows after processing still respects target."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create a medium-sized image (around 350KB original)
        # Use dimensions and complexity that will be close to 400KB at quality 95
        input_path = tmpdir / "input.jpg"

        # Create a complex pattern that compresses poorly at high quality
        img = Image.new('RGB', (1200, 900), color='white')
        pixels = img.load()

        # Add noise pattern to make it harder to compress
        import random
        random.seed(42)
        for i in range(0, 1200, 2):
            for j in range(0, 900, 2):
                color = (random.randint(100, 255), random.randint(100, 255), random.randint(100, 255))
                pixels[i, j] = color

        # Save at lower quality to get it under 400KB
        img.save(input_path, 'JPEG', quality=70)

        original_size = input_path.stat().st_size
        print(f"Original size: {original_size / 1024:.1f}KB")

        # Now optimize it - this might grow the file if we re-save at quality 95
        output_path = tmpdir / "output.jpg"
        result = optimize_image(input_path, output_path, target_size_kb=400)

        final_size = result['final_size']
        print(f"Final size: {final_size / 1024:.1f}KB")
        print(f"Quality used: {result['quality_used']}")

        # THE BUG: final size exceeds target even though we specified 400KB
        assert final_size <= 400 * 1024, f"Final size {final_size / 1024:.1f}KB exceeds target 400KB!"
        print("✓ Test passed - file respects 400KB limit")


if __name__ == '__main__':
    test_small_image_grows_after_processing()

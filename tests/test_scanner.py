"""Tests for scanner module."""

import tempfile
from pathlib import Path

import pytest
from PIL import Image

from photo_terminal.scanner import scan_folder, is_valid_image, SUPPORTED_FORMATS


class TestIsValidImage:
    """Tests for is_valid_image function."""

    def test_valid_jpeg(self, tmp_path):
        """Test that valid JPEG files are recognized."""
        img_path = tmp_path / "test.jpg"
        img = Image.new('RGB', (100, 100), color='red')
        img.save(img_path, 'JPEG')

        assert is_valid_image(img_path) is True

    def test_valid_png(self, tmp_path):
        """Test that valid PNG files are recognized."""
        img_path = tmp_path / "test.png"
        img = Image.new('RGB', (100, 100), color='blue')
        img.save(img_path, 'PNG')

        assert is_valid_image(img_path) is True

    def test_valid_webp(self, tmp_path):
        """Test that valid WEBP files are recognized."""
        img_path = tmp_path / "test.webp"
        img = Image.new('RGB', (100, 100), color='green')
        img.save(img_path, 'WEBP')

        assert is_valid_image(img_path) is True

    def test_valid_gif(self, tmp_path):
        """Test that valid GIF files are recognized."""
        img_path = tmp_path / "test.gif"
        img = Image.new('RGB', (100, 100), color='yellow')
        img.save(img_path, 'GIF')

        assert is_valid_image(img_path) is True

    def test_valid_bmp(self, tmp_path):
        """Test that valid BMP files are recognized."""
        img_path = tmp_path / "test.bmp"
        img = Image.new('RGB', (100, 100), color='purple')
        img.save(img_path, 'BMP')

        assert is_valid_image(img_path) is True

    def test_valid_tiff(self, tmp_path):
        """Test that valid TIFF files are recognized."""
        img_path = tmp_path / "test.tiff"
        img = Image.new('RGB', (100, 100), color='orange')
        img.save(img_path, 'TIFF')

        assert is_valid_image(img_path) is True

    def test_invalid_text_file(self, tmp_path):
        """Test that text files are rejected."""
        txt_path = tmp_path / "test.txt"
        txt_path.write_text("This is not an image")

        assert is_valid_image(txt_path) is False

    def test_invalid_extension(self, tmp_path):
        """Test that files with unsupported extensions are rejected."""
        file_path = tmp_path / "test.pdf"
        file_path.write_text("Not a PDF")

        assert is_valid_image(file_path) is False

    def test_wrong_extension_for_content(self, tmp_path):
        """Test that extension mismatch is detected via magic bytes."""
        # Create a PNG but name it .jpg
        img_path = tmp_path / "fake.jpg"
        img = Image.new('RGB', (100, 100), color='red')
        img.save(img_path, 'PNG')

        # Should still be valid because Pillow checks magic bytes
        # and PNG is a supported format
        assert is_valid_image(img_path) is True

    def test_corrupted_image(self, tmp_path):
        """Test that corrupted image files are rejected."""
        img_path = tmp_path / "corrupted.jpg"
        # Write invalid JPEG data
        img_path.write_bytes(b'\xff\xd8\xff\xe0\x00\x10JFIF')

        assert is_valid_image(img_path) is False


class TestScanFolder:
    """Tests for scan_folder function."""

    def test_scan_with_valid_images(self, tmp_path, capsys):
        """Test scanning folder with valid images."""
        # Create test images
        for i, fmt in enumerate(['JPEG', 'PNG', 'GIF']):
            img_path = tmp_path / f"test{i}.{fmt.lower()}"
            img = Image.new('RGB', (100, 100))
            img.save(img_path, fmt)

        result = scan_folder(str(tmp_path))

        assert len(result) == 3
        assert all(isinstance(p, Path) for p in result)
        # Check sorted by name
        assert result[0].name == 'test0.jpeg'
        assert result[1].name == 'test1.png'
        assert result[2].name == 'test2.gif'

        # Check output message
        captured = capsys.readouterr()
        assert "Found 3 valid image(s)" in captured.out

    def test_scan_mixed_valid_invalid(self, tmp_path, capsys):
        """Test scanning folder with mix of valid and invalid files."""
        # Create valid images
        img1 = tmp_path / "valid1.jpg"
        Image.new('RGB', (100, 100)).save(img1, 'JPEG')

        img2 = tmp_path / "valid2.png"
        Image.new('RGB', (100, 100)).save(img2, 'PNG')

        # Create invalid files
        (tmp_path / "invalid.txt").write_text("Not an image")
        (tmp_path / "invalid.pdf").write_text("Fake PDF")

        result = scan_folder(str(tmp_path))

        assert len(result) == 2
        assert result[0].name == 'valid1.jpg'
        assert result[1].name == 'valid2.png'

        captured = capsys.readouterr()
        assert "Found 2 valid image(s)" in captured.out

    def test_scan_empty_folder(self, tmp_path, capsys):
        """Test that empty folder raises SystemExit."""
        with pytest.raises(SystemExit) as exc_info:
            scan_folder(str(tmp_path))

        assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert "Error: Folder is empty" in captured.out

    def test_scan_no_valid_images(self, tmp_path, capsys):
        """Test that folder with no valid images raises SystemExit."""
        # Create only invalid files
        (tmp_path / "file1.txt").write_text("Text file")
        (tmp_path / "file2.pdf").write_text("PDF file")
        (tmp_path / "file3.doc").write_text("Word file")

        with pytest.raises(SystemExit) as exc_info:
            scan_folder(str(tmp_path))

        assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert "Error: No valid images found" in captured.out
        assert "Supported formats:" in captured.out

    def test_scan_excludes_hidden_files(self, tmp_path, capsys):
        """Test that hidden files are excluded from scan."""
        # Create visible image
        visible = tmp_path / "visible.jpg"
        Image.new('RGB', (100, 100)).save(visible, 'JPEG')

        # Create hidden image (starting with .)
        hidden = tmp_path / ".hidden.jpg"
        Image.new('RGB', (100, 100)).save(hidden, 'JPEG')

        result = scan_folder(str(tmp_path))

        assert len(result) == 1
        assert result[0].name == 'visible.jpg'

        captured = capsys.readouterr()
        assert "Found 1 valid image(s)" in captured.out

    def test_scan_non_recursive(self, tmp_path, capsys):
        """Test that scan only looks at top-level files."""
        # Create image in top level
        top_img = tmp_path / "top.jpg"
        Image.new('RGB', (100, 100)).save(top_img, 'JPEG')

        # Create subdirectory with image
        sub_dir = tmp_path / "subdir"
        sub_dir.mkdir()
        sub_img = sub_dir / "sub.jpg"
        Image.new('RGB', (100, 100)).save(sub_img, 'JPEG')

        result = scan_folder(str(tmp_path))

        assert len(result) == 1
        assert result[0].name == 'top.jpg'

        captured = capsys.readouterr()
        assert "Found 1 valid image(s)" in captured.out

    def test_scan_sorted_output(self, tmp_path):
        """Test that results are sorted by filename."""
        # Create images in non-alphabetical order
        names = ['zebra.jpg', 'apple.png', 'monkey.gif', 'banana.jpg']
        for name in names:
            img_path = tmp_path / name
            fmt = 'JPEG' if name.endswith('.jpg') else ('PNG' if name.endswith('.png') else 'GIF')
            Image.new('RGB', (100, 100)).save(img_path, fmt)

        result = scan_folder(str(tmp_path))

        # Check alphabetical order
        assert [p.name for p in result] == ['apple.png', 'banana.jpg', 'monkey.gif', 'zebra.jpg']

    def test_scan_all_supported_formats(self, tmp_path, capsys):
        """Test that all supported formats are recognized."""
        formats = [
            ('test.jpg', 'JPEG'),
            ('test.jpeg', 'JPEG'),
            ('test.png', 'PNG'),
            ('test.webp', 'WEBP'),
            ('test.gif', 'GIF'),
            ('test.bmp', 'BMP'),
            ('test.tiff', 'TIFF'),
            ('test.tif', 'TIFF'),
        ]

        for filename, fmt in formats:
            img_path = tmp_path / filename
            Image.new('RGB', (100, 100)).save(img_path, fmt)

        result = scan_folder(str(tmp_path))

        assert len(result) == 8
        assert all(p.name.startswith('test.') for p in result)

        captured = capsys.readouterr()
        assert "Found 8 valid image(s)" in captured.out

    def test_scan_case_insensitive_extensions(self, tmp_path, capsys):
        """Test that file extensions are case-insensitive."""
        # Create images with various case extensions
        for ext in ['.JPG', '.Png', '.WEBP', '.gif']:
            img_path = tmp_path / f"test{ext}"
            # Determine format from extension
            fmt = ext.lstrip('.').upper()
            if fmt == 'JPG':
                fmt = 'JPEG'
            Image.new('RGB', (100, 100)).save(img_path, fmt)

        result = scan_folder(str(tmp_path))

        assert len(result) == 4

        captured = capsys.readouterr()
        assert "Found 4 valid image(s)" in captured.out

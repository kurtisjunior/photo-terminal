"""The S3 key scheme.

These used to live in ``test_uploader.py`` and reach into ``uploader`` for two
underscored functions, which is also how ``dry_run`` got hold of them. The rule
is domain knowledge now, and so are its tests.
"""

from photo_terminal.domain.naming import construct_s3_key, normalize_prefix

# Tests for normalize_prefix()


def test_normalize_prefix_empty_string():
    """Test normalizing empty prefix."""
    assert normalize_prefix("") == ""


def test_normalize_prefix_no_trailing_slash():
    """Test normalizing prefix without trailing slash."""
    assert normalize_prefix("japan/tokyo") == "japan/tokyo"


def test_normalize_prefix_trailing_slash():
    """Test normalizing prefix with trailing slash."""
    assert normalize_prefix("japan/tokyo/") == "japan/tokyo"


def test_normalize_prefix_multiple_trailing_slashes():
    """Test normalizing prefix with multiple trailing slashes."""
    assert normalize_prefix("japan///") == "japan"


def test_normalize_prefix_whitespace():
    """Test normalizing prefix with whitespace."""
    assert normalize_prefix("  japan/tokyo  ") == "japan/tokyo"
    assert normalize_prefix("  japan/tokyo/  ") == "japan/tokyo"


def test_normalize_prefix_single_folder():
    """Test normalizing single folder prefix."""
    assert normalize_prefix("japan") == "japan"
    assert normalize_prefix("japan/") == "japan"


# Tests for construct_s3_key()


def test_construct_s3_key_with_prefix():
    """Test constructing S3 key with prefix."""
    assert construct_s3_key("japan/tokyo", "image.jpg") == "japan/tokyo/image.jpg"


def test_construct_s3_key_without_prefix():
    """Test constructing S3 key without prefix."""
    assert construct_s3_key("", "image.jpg") == "image.jpg"


def test_construct_s3_key_single_folder():
    """Test constructing S3 key with single folder prefix."""
    assert construct_s3_key("japan", "image.jpg") == "japan/image.jpg"


def test_construct_s3_key_deep_hierarchy():
    """Test constructing S3 key with deep folder hierarchy."""
    assert construct_s3_key("italy/trapani/2024", "sunset.jpg") == "italy/trapani/2024/sunset.jpg"

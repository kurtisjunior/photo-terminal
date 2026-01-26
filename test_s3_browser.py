"""Tests for S3 folder browser module."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from botocore.exceptions import (
    ClientError,
    NoCredentialsError,
    ProfileNotFound,
    EndpointConnectionError,
)

from s3_browser import (
    S3AccessError,
    validate_s3_access,
    list_s3_folders,
    S3FolderBrowser,
    browse_s3_folders,
)


# Test fixtures

@pytest.fixture
def mock_s3_client():
    """Mock boto3 S3 client."""
    return Mock()


@pytest.fixture
def mock_session(mock_s3_client):
    """Mock boto3 Session."""
    session = Mock()
    session.client.return_value = mock_s3_client
    return session


# Tests for validate_s3_access

def test_s3_access_success(mock_session, mock_s3_client):
    """Test successful S3 access validation."""
    mock_s3_client.list_objects_v2.return_value = {'Contents': []}

    with patch('s3_browser.boto3.Session', return_value=mock_session):
        # Should not raise any exception
        validate_s3_access('test-bucket', 'test-profile')

    mock_s3_client.list_objects_v2.assert_called_once_with(
        Bucket='test-bucket',
        MaxKeys=1
    )


def test_s3_access_profile_not_found(mock_session):
    """Test error when AWS profile not found."""
    with patch('s3_browser.boto3.Session', side_effect=ProfileNotFound(profile='test-profile')):
        with pytest.raises(S3AccessError) as exc_info:
            validate_s3_access('test-bucket', 'test-profile')

        assert 'profile' in str(exc_info.value).lower()
        assert 'test-profile' in str(exc_info.value)
        assert 'aws configure' in str(exc_info.value).lower()


def test_s3_access_no_credentials(mock_session, mock_s3_client):
    """Test error when AWS credentials not found."""
    mock_s3_client.list_objects_v2.side_effect = NoCredentialsError()

    with patch('s3_browser.boto3.Session', return_value=mock_session):
        with pytest.raises(S3AccessError) as exc_info:
            validate_s3_access('test-bucket', 'test-profile')

        assert 'credentials' in str(exc_info.value).lower()
        assert 'aws configure' in str(exc_info.value).lower()


def test_s3_access_bucket_not_found(mock_session, mock_s3_client):
    """Test error when S3 bucket does not exist."""
    error_response = {
        'Error': {
            'Code': 'NoSuchBucket',
            'Message': 'The specified bucket does not exist'
        }
    }
    mock_s3_client.list_objects_v2.side_effect = ClientError(error_response, 'ListObjectsV2')

    with patch('s3_browser.boto3.Session', return_value=mock_session):
        with pytest.raises(S3AccessError) as exc_info:
            validate_s3_access('test-bucket', 'test-profile')

        assert 'test-bucket' in str(exc_info.value)
        assert 'does not exist' in str(exc_info.value).lower()


def test_s3_access_denied(mock_session, mock_s3_client):
    """Test error when access to S3 bucket is denied."""
    error_response = {
        'Error': {
            'Code': 'AccessDenied',
            'Message': 'Access Denied'
        }
    }
    mock_s3_client.list_objects_v2.side_effect = ClientError(error_response, 'ListObjectsV2')

    with patch('s3_browser.boto3.Session', return_value=mock_session):
        with pytest.raises(S3AccessError) as exc_info:
            validate_s3_access('test-bucket', 'test-profile')

        assert 'access denied' in str(exc_info.value).lower()
        assert 'permission' in str(exc_info.value).lower()


def test_s3_access_network_error(mock_session, mock_s3_client):
    """Test error when network connection fails."""
    mock_s3_client.list_objects_v2.side_effect = EndpointConnectionError(
        endpoint_url='https://s3.amazonaws.com'
    )

    with patch('s3_browser.boto3.Session', return_value=mock_session):
        with pytest.raises(S3AccessError) as exc_info:
            validate_s3_access('test-bucket', 'test-profile')

        assert 'network' in str(exc_info.value).lower()


# Tests for list_s3_folders

def test_list_s3_folders_root(mock_session, mock_s3_client):
    """Test listing folders at root level."""
    mock_s3_client.list_objects_v2.return_value = {
        'CommonPrefixes': [
            {'Prefix': 'japan/'},
            {'Prefix': 'italy/'},
            {'Prefix': 'spain/'},
        ]
    }

    with patch('s3_browser.boto3.Session', return_value=mock_session):
        folders = list_s3_folders('test-bucket', 'test-profile', '')

    assert folders == ['italy', 'japan', 'spain']  # Sorted
    mock_s3_client.list_objects_v2.assert_called_once_with(
        Bucket='test-bucket',
        Prefix='',
        Delimiter='/'
    )


def test_list_s3_folders_subfolder(mock_session, mock_s3_client):
    """Test listing folders in a subfolder."""
    mock_s3_client.list_objects_v2.return_value = {
        'CommonPrefixes': [
            {'Prefix': 'italy/rome/'},
            {'Prefix': 'italy/trapani/'},
            {'Prefix': 'italy/venice/'},
        ]
    }

    with patch('s3_browser.boto3.Session', return_value=mock_session):
        folders = list_s3_folders('test-bucket', 'test-profile', 'italy/')

    assert folders == ['rome', 'trapani', 'venice']  # Sorted
    mock_s3_client.list_objects_v2.assert_called_once_with(
        Bucket='test-bucket',
        Prefix='italy/',
        Delimiter='/'
    )


def test_list_s3_folders_empty(mock_session, mock_s3_client):
    """Test listing folders when no subfolders exist."""
    mock_s3_client.list_objects_v2.return_value = {
        'CommonPrefixes': []
    }

    with patch('s3_browser.boto3.Session', return_value=mock_session):
        folders = list_s3_folders('test-bucket', 'test-profile', 'japan/tokyo/')

    assert folders == []


def test_list_s3_folders_error(mock_session, mock_s3_client):
    """Test error handling when listing folders fails."""
    mock_s3_client.list_objects_v2.side_effect = Exception("Network error")

    with patch('s3_browser.boto3.Session', return_value=mock_session):
        with pytest.raises(S3AccessError) as exc_info:
            list_s3_folders('test-bucket', 'test-profile', '')

        assert 'error listing' in str(exc_info.value).lower()


# Tests for S3FolderBrowser class

def test_browser_init():
    """Test S3FolderBrowser initialization."""
    browser = S3FolderBrowser('test-bucket', 'test-profile')

    assert browser.bucket == 'test-bucket'
    assert browser.aws_profile == 'test-profile'
    assert browser.current_prefix == ""
    assert browser.folders == []
    assert browser.current_index == 0


def test_browser_breadcrumb_root():
    """Test breadcrumb at root level."""
    browser = S3FolderBrowser('test-bucket', 'test-profile')
    browser.current_prefix = ""

    assert browser.get_breadcrumb() == "Root"


def test_browser_breadcrumb_single_level():
    """Test breadcrumb at single level."""
    browser = S3FolderBrowser('test-bucket', 'test-profile')
    browser.current_prefix = "japan/"

    assert browser.get_breadcrumb() == "Root / japan"


def test_browser_breadcrumb_nested():
    """Test breadcrumb at nested level."""
    browser = S3FolderBrowser('test-bucket', 'test-profile')
    browser.current_prefix = "italy/trapani/"

    assert browser.get_breadcrumb() == "Root / italy / trapani"


def test_browser_menu_items_root():
    """Test menu items at root level."""
    browser = S3FolderBrowser('test-bucket', 'test-profile')
    browser.current_prefix = ""
    browser.folders = ['japan', 'italy']

    items = browser.get_menu_items()

    assert items[0] == browser.SELECT_CURRENT
    # No "go up" at root
    assert browser.GO_UP not in items
    assert 'japan' in items
    assert 'italy' in items


def test_browser_menu_items_subfolder():
    """Test menu items in a subfolder."""
    browser = S3FolderBrowser('test-bucket', 'test-profile')
    browser.current_prefix = "japan/"
    browser.folders = ['tokyo', 'kyoto']

    items = browser.get_menu_items()

    assert items[0] == browser.SELECT_CURRENT
    assert items[1] == browser.GO_UP  # Should have "go up"
    assert 'tokyo' in items
    assert 'kyoto' in items


def test_browser_navigation_up():
    """Test moving selection up."""
    browser = S3FolderBrowser('test-bucket', 'test-profile')
    browser.folders = ['japan', 'italy']
    browser.current_index = 2

    browser.move_up()
    assert browser.current_index == 1

    browser.move_up()
    assert browser.current_index == 0

    # Should not go below 0
    browser.move_up()
    assert browser.current_index == 0


def test_browser_navigation_down():
    """Test moving selection down."""
    browser = S3FolderBrowser('test-bucket', 'test-profile')
    browser.folders = ['japan', 'italy']
    browser.current_index = 0

    browser.move_down()
    assert browser.current_index == 1

    browser.move_down()
    assert browser.current_index == 2

    # Should not exceed list length
    browser.move_down()
    assert browser.current_index == 2


def test_browser_select_current_folder():
    """Test selecting current folder."""
    browser = S3FolderBrowser('test-bucket', 'test-profile')
    browser.current_prefix = "japan/tokyo/"
    browser.folders = []
    browser.current_index = 0  # First item is "Select current folder"

    result = browser.handle_selection()

    assert result == "japan/tokyo/"


def test_browser_drill_into_folder(mock_session, mock_s3_client):
    """Test drilling into a subfolder."""
    mock_s3_client.list_objects_v2.return_value = {
        'CommonPrefixes': [
            {'Prefix': 'japan/tokyo/'},
            {'Prefix': 'japan/kyoto/'},
        ]
    }

    browser = S3FolderBrowser('test-bucket', 'test-profile')
    browser.current_prefix = "japan/"
    browser.folders = ['tokyo', 'kyoto']
    browser.current_index = 2  # First item is "Select", second is "..", third is "tokyo"

    with patch('s3_browser.boto3.Session', return_value=mock_session):
        result = browser.handle_selection()

    assert result is None  # Continue browsing
    assert browser.current_prefix == "japan/tokyo/"


def test_browser_go_up_one_level(mock_session, mock_s3_client):
    """Test going up one level."""
    mock_s3_client.list_objects_v2.return_value = {
        'CommonPrefixes': [
            {'Prefix': 'japan/'},
        ]
    }

    browser = S3FolderBrowser('test-bucket', 'test-profile')
    browser.current_prefix = "japan/tokyo/"
    browser.folders = []
    browser.current_index = 1  # First item is "Select", second is ".."

    with patch('s3_browser.boto3.Session', return_value=mock_session):
        result = browser.handle_selection()

    assert result is None  # Continue browsing
    assert browser.current_prefix == "japan/"


def test_browser_go_up_to_root(mock_session, mock_s3_client):
    """Test going up to root level."""
    mock_s3_client.list_objects_v2.return_value = {
        'CommonPrefixes': [
            {'Prefix': 'japan/'},
            {'Prefix': 'italy/'},
        ]
    }

    browser = S3FolderBrowser('test-bucket', 'test-profile')
    browser.current_prefix = "japan/"
    browser.folders = []
    browser.current_index = 1  # First item is "Select", second is ".."

    with patch('s3_browser.boto3.Session', return_value=mock_session):
        result = browser.handle_selection()

    assert result is None  # Continue browsing
    assert browser.current_prefix == ""


def test_browser_load_folders(mock_session, mock_s3_client):
    """Test loading folders at current level."""
    mock_s3_client.list_objects_v2.return_value = {
        'CommonPrefixes': [
            {'Prefix': 'japan/'},
            {'Prefix': 'italy/'},
        ]
    }

    browser = S3FolderBrowser('test-bucket', 'test-profile')
    browser.current_index = 5  # Some arbitrary index

    with patch('s3_browser.boto3.Session', return_value=mock_session):
        browser.load_folders()

    assert browser.folders == ['italy', 'japan']
    assert browser.current_index == 0  # Reset to top


# Tests for browse_s3_folders function

def test_browse_with_cli_prefix(mock_session, mock_s3_client):
    """Test browse_s3_folders with CLI prefix (skip browser)."""
    mock_s3_client.list_objects_v2.return_value = {}

    with patch('s3_browser.boto3.Session', return_value=mock_session):
        result = browse_s3_folders('test-bucket', 'test-profile', 'japan/tokyo')

    # Should return prefix directly without showing browser
    assert result == 'japan/tokyo/'


def test_browse_with_cli_prefix_already_trailing_slash(mock_session, mock_s3_client):
    """Test browse_s3_folders with CLI prefix that already has trailing slash."""
    mock_s3_client.list_objects_v2.return_value = {}

    with patch('s3_browser.boto3.Session', return_value=mock_session):
        result = browse_s3_folders('test-bucket', 'test-profile', 'japan/tokyo/')

    assert result == 'japan/tokyo/'


def test_browse_with_empty_cli_prefix(mock_session, mock_s3_client):
    """Test browse_s3_folders with empty string as CLI prefix (root)."""
    mock_s3_client.list_objects_v2.return_value = {}

    with patch('s3_browser.boto3.Session', return_value=mock_session):
        result = browse_s3_folders('test-bucket', 'test-profile', '')

    assert result == ''


def test_browse_s3_access_error(mock_session, mock_s3_client):
    """Test browse_s3_folders fails when S3 access test fails."""
    mock_s3_client.list_objects_v2.side_effect = NoCredentialsError()

    with patch('s3_browser.boto3.Session', return_value=mock_session):
        with pytest.raises(SystemExit) as exc_info:
            browse_s3_folders('test-bucket', 'test-profile')

        assert exc_info.value.code == 1


def test_browse_interactive_cancelled():
    """Test browse_s3_folders raises SystemExit when user cancels."""
    mock_browser = Mock()
    mock_browser.run.side_effect = KeyboardInterrupt()

    with patch('s3_browser.validate_s3_access'):
        with patch('s3_browser.S3FolderBrowser', return_value=mock_browser):
            with pytest.raises(SystemExit) as exc_info:
                browse_s3_folders('test-bucket', 'test-profile')

            assert exc_info.value.code == 1


def test_browse_interactive_success():
    """Test browse_s3_folders returns selected prefix from interactive browser."""
    mock_browser = Mock()
    mock_browser.run.return_value = 'japan/tokyo/'

    with patch('s3_browser.validate_s3_access'):
        with patch('s3_browser.S3FolderBrowser', return_value=mock_browser):
            result = browse_s3_folders('test-bucket', 'test-profile')

    assert result == 'japan/tokyo/'


# Integration tests

def test_full_navigation_flow(mock_session, mock_s3_client):
    """Test complete navigation flow: root -> subfolder -> select."""
    # Setup mock responses for different levels
    def list_objects_side_effect(**kwargs):
        prefix = kwargs.get('Prefix', '')
        if prefix == '':
            return {'CommonPrefixes': [{'Prefix': 'japan/'}]}
        elif prefix == 'japan/':
            return {'CommonPrefixes': [{'Prefix': 'japan/tokyo/'}]}
        return {'CommonPrefixes': []}

    mock_s3_client.list_objects_v2.side_effect = list_objects_side_effect

    browser = S3FolderBrowser('test-bucket', 'test-profile')

    with patch('s3_browser.boto3.Session', return_value=mock_session):
        # Start at root
        browser.load_folders()
        assert browser.folders == ['japan']
        assert browser.current_prefix == ''

        # Drill into japan
        browser.current_index = 1  # "japan" folder
        result = browser.handle_selection()
        assert result is None
        assert browser.current_prefix == 'japan/'
        assert browser.folders == ['tokyo']

        # Select current folder
        browser.current_index = 0  # "Select current folder"
        result = browser.handle_selection()
        assert result == 'japan/'

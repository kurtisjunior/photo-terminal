"""Interactive S3 folder browser with hierarchy navigation.

Provides a terminal interface for navigating S3 bucket structure:
- Lists folders/prefixes at current level
- Arrow keys to navigate
- Enter to drill into folders
- '..' to go up one level
- 'Select current folder' option to choose current location
- Shows breadcrumb navigation at top
- Tests S3 access on startup for fail-fast error handling
"""

import sys
from pathlib import Path
from typing import List, Optional, Tuple

import boto3
from botocore.exceptions import (
    ClientError,
    NoCredentialsError,
    ProfileNotFound,
    EndpointConnectionError,
    BotoCoreError
)
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


class S3AccessError(Exception):
    """Raised when S3 access validation fails."""
    pass


def validate_s3_access(bucket: str, aws_profile: str) -> None:
    """Validate S3 access early to fail-fast on credential/permission issues.

    Args:
        bucket: S3 bucket name
        aws_profile: AWS profile name

    Raises:
        S3AccessError: If S3 access fails with detailed error message
    """
    try:
        session = boto3.Session(profile_name=aws_profile)
        s3_client = session.client('s3')

        # Test ListBucket permission with minimal request
        s3_client.list_objects_v2(Bucket=bucket, MaxKeys=1)

    except ProfileNotFound:
        raise S3AccessError(
            f"AWS profile '{aws_profile}' not found.\n\n"
            f"Configure AWS CLI with:\n"
            f"  aws configure --profile {aws_profile}\n\n"
            f"Or check your ~/.aws/credentials file."
        )

    except NoCredentialsError:
        raise S3AccessError(
            "AWS credentials not found.\n\n"
            "Configure AWS CLI with:\n"
            "  aws configure\n\n"
            "Or set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables."
        )

    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')

        if error_code == 'NoSuchBucket':
            raise S3AccessError(
                f"S3 bucket '{bucket}' does not exist.\n\n"
                f"Verify the bucket name in your configuration."
            )

        elif error_code == 'AccessDenied' or error_code == 'Forbidden':
            raise S3AccessError(
                f"Access denied to S3 bucket '{bucket}'.\n\n"
                f"Verify that:\n"
                f"  1. AWS profile '{aws_profile}' has ListBucket permission\n"
                f"  2. Bucket policy allows your IAM user/role access\n\n"
                f"Error: {e.response.get('Error', {}).get('Message', str(e))}"
            )

        else:
            raise S3AccessError(
                f"AWS error accessing bucket '{bucket}':\n"
                f"Error code: {error_code}\n"
                f"Message: {e.response.get('Error', {}).get('Message', str(e))}"
            )

    except EndpointConnectionError as e:
        raise S3AccessError(
            "Network error: Could not connect to AWS.\n\n"
            "Check your internet connection and try again.\n\n"
            f"Details: {e}"
        )

    except BotoCoreError as e:
        raise S3AccessError(
            f"AWS SDK error: {e}\n\n"
            "This may be a configuration issue. Check your AWS setup."
        )

    except Exception as e:
        raise S3AccessError(
            f"Unexpected error accessing S3: {e}\n\n"
            "Please check your AWS configuration."
        )


def list_s3_folders(bucket: str, aws_profile: str, prefix: str = "") -> List[str]:
    """List folders (CommonPrefixes) at a given S3 prefix level.

    Args:
        bucket: S3 bucket name
        aws_profile: AWS profile name
        prefix: S3 prefix to list (e.g., "japan/" or "")

    Returns:
        List of folder names (without full prefix path)

    Raises:
        S3AccessError: If S3 access fails
    """
    try:
        session = boto3.Session(profile_name=aws_profile)
        s3_client = session.client('s3')

        # Use delimiter='/' to get folder-like structure
        response = s3_client.list_objects_v2(
            Bucket=bucket,
            Prefix=prefix,
            Delimiter='/'
        )

        # Extract CommonPrefixes (folders)
        folders = []
        for common_prefix in response.get('CommonPrefixes', []):
            full_prefix = common_prefix['Prefix']

            # Extract just the folder name (last segment before trailing /)
            # e.g., "japan/tokyo/" -> "tokyo"
            folder_name = full_prefix.rstrip('/').split('/')[-1]
            folders.append(folder_name)

        return sorted(folders)

    except Exception as e:
        raise S3AccessError(f"Error listing S3 folders: {e}")


class S3FolderBrowser:
    """Interactive S3 folder browser with hierarchy navigation."""

    def __init__(self, bucket: str, aws_profile: str):
        """Initialize S3 folder browser.

        Args:
            bucket: S3 bucket name
            aws_profile: AWS profile name
        """
        self.bucket = bucket
        self.aws_profile = aws_profile
        self.current_prefix = ""  # Current S3 prefix (e.g., "japan/tokyo/")
        self.folders = []  # Folders at current level
        self.current_index = 0  # Currently highlighted item
        self.console = Console()

        # Special menu items
        self.SELECT_CURRENT = "[Select current folder]"
        self.GO_UP = ".."

    def get_breadcrumb(self) -> str:
        """Get breadcrumb path for current location.

        Returns:
            Breadcrumb string (e.g., "Root / japan / tokyo")
        """
        if not self.current_prefix:
            return "Root"

        # Split prefix into parts
        parts = self.current_prefix.rstrip('/').split('/')
        return "Root / " + " / ".join(parts)

    def get_menu_items(self) -> List[str]:
        """Get menu items for current level.

        Returns:
            List of menu items including special options and folders
        """
        items = [self.SELECT_CURRENT]

        # Add "go up" option if not at root
        if self.current_prefix:
            items.append(self.GO_UP)

        # Add folders
        items.extend(self.folders)

        return items

    def load_folders(self) -> None:
        """Load folders at current prefix level."""
        self.folders = list_s3_folders(self.bucket, self.aws_profile, self.current_prefix)
        self.current_index = 0  # Reset selection to top

    def move_up(self) -> None:
        """Move selection cursor up."""
        if self.current_index > 0:
            self.current_index -= 1

    def move_down(self) -> None:
        """Move selection cursor down."""
        menu_items = self.get_menu_items()
        if self.current_index < len(menu_items) - 1:
            self.current_index += 1

    def handle_selection(self) -> Optional[str]:
        """Handle Enter key on current selection.

        Returns:
            Selected prefix if user chose current folder, None to continue browsing
        """
        menu_items = self.get_menu_items()
        selected = menu_items[self.current_index]

        if selected == self.SELECT_CURRENT:
            # User selected current folder
            return self.current_prefix

        elif selected == self.GO_UP:
            # Go up one level
            if self.current_prefix:
                # Remove last segment
                parts = self.current_prefix.rstrip('/').split('/')
                if len(parts) > 1:
                    self.current_prefix = '/'.join(parts[:-1]) + '/'
                else:
                    self.current_prefix = ""
                self.load_folders()
            return None

        else:
            # User selected a folder - drill into it
            self.current_prefix = self.current_prefix + selected + '/'
            self.load_folders()
            return None

    def create_panel(self) -> Panel:
        """Create the browser panel with folder list.

        Returns:
            Panel containing the folder browser
        """
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("item", overflow="fold")

        menu_items = self.get_menu_items()

        for i, item in enumerate(menu_items):
            # Add visual indicators
            if item == self.SELECT_CURRENT:
                display = f"✓ {item}"
            elif item == self.GO_UP:
                display = f"↑ {item}"
            else:
                display = f"  {item}/"

            # Highlight current selection
            if i == self.current_index:
                text = Text(f"► {display}", style="bold cyan")
            else:
                text = Text(f"  {display}")

            table.add_row(text)

        # Add controls footer
        controls_text = Text()
        controls_text.append("\n" + "─" * 40 + "\n", style="dim")
        controls_text.append("↑/↓: Navigate  Enter: Select/Drill down\n", style="dim")
        controls_text.append("q/Esc: Cancel", style="dim")

        # Show breadcrumb in title
        breadcrumb = self.get_breadcrumb()
        title = f"S3 Browser: {breadcrumb}"

        from rich.console import Group
        return Panel(Group(table, controls_text), title=title, border_style="blue")

    def run(self) -> str:
        """Run the interactive browser.

        Returns:
            Selected S3 prefix (e.g., "japan/tokyo/" or "" for root)

        Raises:
            SystemExit: If user cancels
        """
        # Import here to avoid issues if not in interactive terminal
        import tty
        import termios

        # Load initial folder list
        self.load_folders()

        # Save terminal settings
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)

        try:
            # Set terminal to raw mode for key capture
            tty.setraw(fd)

            with Live(self.create_panel(), console=self.console, refresh_per_second=4) as live:
                while True:
                    # Read a single character
                    char = sys.stdin.read(1)

                    # Handle escape sequences (arrow keys)
                    if char == '\x1b':  # ESC
                        next_char = sys.stdin.read(1)
                        if next_char == '[':
                            arrow = sys.stdin.read(1)
                            if arrow == 'A':  # Up arrow
                                self.move_up()
                            elif arrow == 'B':  # Down arrow
                                self.move_down()
                        else:
                            # Escape key pressed (without arrow)
                            raise SystemExit(1)

                    # Handle other keys
                    elif char == '\r' or char == '\n':  # Enter
                        result = self.handle_selection()
                        if result is not None:
                            # User selected a folder
                            return result

                    elif char == 'q' or char == 'Q':  # Quit
                        raise SystemExit(1)

                    elif char == '\x03':  # Ctrl+C
                        raise KeyboardInterrupt

                    # Update the display
                    live.update(self.create_panel())

        finally:
            # Restore terminal settings
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def browse_s3_folders(bucket: str, aws_profile: str, initial_prefix: Optional[str] = None) -> str:
    """Browse S3 folders and select upload target.

    If initial_prefix is provided, skip browser and return it directly.
    Otherwise, show interactive folder browser.

    Args:
        bucket: S3 bucket name
        aws_profile: AWS profile name
        initial_prefix: Optional prefix from CLI args (skip browser if provided)

    Returns:
        Selected S3 prefix (e.g., "japan/tokyo/" or "" for root)

    Raises:
        SystemExit: If S3 access fails or user cancels
    """
    # Test S3 access first (fail-fast)
    try:
        validate_s3_access(bucket, aws_profile)
    except S3AccessError as e:
        print(f"Error: Cannot access S3 bucket '{bucket}'")
        print()
        print(str(e))
        raise SystemExit(1)

    # If prefix provided via CLI, skip browser
    if initial_prefix is not None:
        # Ensure prefix ends with / if not empty
        if initial_prefix and not initial_prefix.endswith('/'):
            initial_prefix = initial_prefix + '/'
        return initial_prefix

    # Run interactive browser
    print()
    print("Select S3 upload folder:")
    print()

    browser = S3FolderBrowser(bucket, aws_profile)

    try:
        selected_prefix = browser.run()
        return selected_prefix

    except KeyboardInterrupt:
        print("\n\nCancelled by user")
        raise SystemExit(1)

"""DCUI-style dialog widgets."""

from __future__ import annotations

import asyncio
import re
import subprocess
from typing import TYPE_CHECKING

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Static

if TYPE_CHECKING:
    from ..app import ZBoxTUI


# Common CSS for all DCUI dialogs - ESXi DCUI style
# Uses section-specific borders so backgrounds match correctly
DCUI_DIALOG_CSS = """
    /* Modal fills screen with black background */
    {dialog_class} {{
        align: center middle;
        background: black;
    }}

    /* Outer container - no border, sections have their own */
    {dialog_class} #dialog-outer {{
        layout: vertical;
        width: {width};
        height: auto;
    }}

    /* Grey header section with top and side borders */
    {dialog_class} #dialog-header {{
        background: #5a5a5a;
        color: white;
        height: auto;
        padding: 0 2;
        border-top: solid white;
        border-left: solid white;
        border-right: solid white;
    }}

    {dialog_class} #dialog-title {{
        color: #ffd700;
        text-align: center;
        height: 1;
    }}

    {dialog_class} #dialog-subtitle {{
        color: #aaaaaa;
        text-align: center;
        height: auto;
    }}

    /* Yellow body section with bottom and side borders */
    {dialog_class} #dialog-body {{
        background: #ffd700;
        color: black;
        height: auto;
        padding: 1 2;
        border-bottom: solid white;
        border-left: solid white;
        border-right: solid white;
    }}

    /* Footer with keybinds - at bottom of yellow section */
    {dialog_class} #dialog-footer {{
        background: #ffd700;
        color: black;
        text-align: center;
        height: 1;
    }}
"""


class LoginDialog(ModalScreen[tuple[str, str] | None]):
    """A DCUI-style login dialog."""

    app: ZBoxTUI

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    DEFAULT_CSS = DCUI_DIALOG_CSS.format(dialog_class="LoginDialog", width=60) + """
    LoginDialog .form-row {
        height: 3;
        width: 100%;
    }

    LoginDialog .form-label {
        width: 15;
        color: black;
        height: 3;
        content-align: left middle;
    }

    LoginDialog .form-input {
        width: 1fr;
        background: #3a3a3a;
        color: white;
        border: none;
        height: 3;
    }

    LoginDialog .form-input:focus {
        background: #4a4a4a;
    }
    """

    def __init__(
        self,
        hostname: str = "localhost",
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._hostname = hostname

    def compose(self) -> ComposeResult:
        with Container(id="dialog-outer"):
            with Vertical(id="dialog-header"):
                yield Static("")  # Spacer before title
                yield Static("Authentication Required", id="dialog-title")
                yield Static("")  # Spacer after title
                yield Static(
                    f"Enter an authorized login name and password for {self._hostname}.",
                    id="dialog-subtitle",
                )
                yield Static("")  # Spacer after subtitle
            with Vertical(id="dialog-body"):
                with Horizontal(classes="form-row"):
                    yield Static("Login Name:", classes="form-label")
                    yield Input(
                        value="root",
                        placeholder="username",
                        classes="form-input",
                        id="username-input",
                    )
                with Horizontal(classes="form-row"):
                    yield Static("Password:", classes="form-label")
                    yield Input(
                        password=True,
                        placeholder="password",
                        classes="form-input",
                        id="password-input",
                    )
                yield Static("")  # Spacer before footer
                yield Static("<Enter> OK    <Esc> Cancel", id="dialog-footer")

    def on_mount(self) -> None:
        """Focus the username input on mount and take debug screenshot."""
        self.query_one("#username-input", Input).focus()
        self.app.save_debug_screenshot("login_dialog")

    @on(Input.Submitted)
    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in input fields."""
        if event.input.id == "username-input":
            # Move to password field
            self.query_one("#password-input", Input).focus()
        elif event.input.id == "password-input":
            # Submit the form
            self._submit()

    def _submit(self) -> None:
        """Submit the login form."""
        username = self.query_one("#username-input", Input).value
        password = self.query_one("#password-input", Input).value
        self.dismiss((username, password))

    def action_cancel(self) -> None:
        """Cancel the dialog."""
        self.dismiss(None)


class PasswordDialog(ModalScreen[bool]):
    """A DCUI-style dialog for changing the root password."""

    app: ZBoxTUI

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    DEFAULT_CSS = DCUI_DIALOG_CSS.format(dialog_class="PasswordDialog", width=60) + """
    PasswordDialog .form-row {
        height: 3;
        width: 100%;
    }

    PasswordDialog .form-label {
        width: 20;
        color: black;
        height: 3;
        content-align: left middle;
    }

    PasswordDialog .form-input {
        width: 1fr;
        background: #3a3a3a;
        color: white;
        border: none;
        height: 3;
    }

    PasswordDialog .form-input:focus {
        background: #4a4a4a;
    }

    PasswordDialog #error-message {
        color: #8b0000;
        height: 1;
        text-align: center;
    }

    PasswordDialog #success-message {
        color: #006400;
        height: 1;
        text-align: center;
    }
    """

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)

    def compose(self) -> ComposeResult:
        with Container(id="dialog-outer"):
            with Vertical(id="dialog-header"):
                yield Static("")  # Spacer before title
                yield Static("Configure Root Password", id="dialog-title")
                yield Static("")  # Spacer after title
                yield Static(
                    "Enter a new password for the root account.",
                    id="dialog-subtitle",
                )
                yield Static("")  # Spacer after subtitle
            with Vertical(id="dialog-body"):
                with Horizontal(classes="form-row"):
                    yield Static("New Password:", classes="form-label")
                    yield Input(
                        password=True,
                        placeholder="Enter new password",
                        classes="form-input",
                        id="password-input",
                    )
                with Horizontal(classes="form-row"):
                    yield Static("Confirm Password:", classes="form-label")
                    yield Input(
                        password=True,
                        placeholder="Confirm new password",
                        classes="form-input",
                        id="confirm-input",
                    )
                yield Static("", id="error-message")
                yield Static("")  # Spacer before footer
                yield Static("<Enter> Apply    <Esc> Cancel", id="dialog-footer")

    def on_mount(self) -> None:
        """Focus the password input on mount and take debug screenshot."""
        self.query_one("#password-input", Input).focus()
        self.app.save_debug_screenshot("password_dialog")

    @on(Input.Submitted)
    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in input fields."""
        if event.input.id == "password-input":
            # Move to confirm field
            self.query_one("#confirm-input", Input).focus()
        elif event.input.id == "confirm-input":
            # Submit the form
            self._submit()

    def _submit(self) -> None:
        """Validate and apply the password change."""
        password = self.query_one("#password-input", Input).value
        confirm = self.query_one("#confirm-input", Input).value
        error_msg = self.query_one("#error-message", Static)

        # Validate passwords
        if not password:
            error_msg.update("Error: Password cannot be empty")
            self.query_one("#password-input", Input).focus()
            return

        if password != confirm:
            error_msg.update("Error: Passwords do not match")
            self.query_one("#confirm-input", Input).value = ""
            self.query_one("#confirm-input", Input).focus()
            return

        if len(password) < 4:
            error_msg.update("Error: Password must be at least 4 characters")
            return

        # Apply the password change
        try:
            result = subprocess.run(
                ["chpasswd"],
                input=f"root:{password}\n",
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                error_msg.update("")
                # Show success and close
                self.app.push_screen(
                    MessageDialog(
                        "Password Changed",
                        "Root password has been successfully updated.",
                    ),
                    callback=lambda _: self.dismiss(True),
                )
            else:
                error_msg.update(f"Error: {result.stderr.strip() or 'Failed to change password'}")
        except subprocess.TimeoutExpired:
            error_msg.update("Error: Password change timed out")
        except FileNotFoundError:
            error_msg.update("Error: chpasswd command not found")
        except Exception as e:
            error_msg.update(f"Error: {e}")

    def action_cancel(self) -> None:
        """Cancel the dialog."""
        self.dismiss(False)


class MessageDialog(ModalScreen[bool]):
    """A simple message dialog with OK/Cancel."""

    app: ZBoxTUI

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("enter", "confirm", "OK", show=False),
    ]

    DEFAULT_CSS = DCUI_DIALOG_CSS.format(dialog_class="MessageDialog", width=50) + """
    MessageDialog #dialog-message {
        color: black;
        height: auto;
    }
    """

    def __init__(
        self,
        title: str,
        message: str,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._title = title
        self._message = message

    def compose(self) -> ComposeResult:
        with Container(id="dialog-outer"):
            with Vertical(id="dialog-header"):
                yield Static("")  # Spacer before title
                yield Static(self._title, id="dialog-title")
                yield Static("")  # Spacer after title
            with Vertical(id="dialog-body"):
                yield Static(self._message, id="dialog-message")
                yield Static("")  # Spacer before footer
                yield Static("<Enter> OK    <Esc> Cancel", id="dialog-footer")

    def on_mount(self) -> None:
        """Take debug screenshot on mount."""
        # Use title as part of the filename, sanitized for filesystem
        safe_title = self._title.lower().replace(" ", "_").replace("/", "_")
        self.app.save_debug_screenshot(f"message_dialog_{safe_title}")

    def action_confirm(self) -> None:
        """Confirm the dialog."""
        self.dismiss(True)

    def action_cancel(self) -> None:
        """Cancel the dialog."""
        self.dismiss(False)


def get_default_gateway() -> str | None:
    """Get the default gateway IP address."""
    try:
        result = subprocess.run(
            ["ip", "route", "show", "default"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            # Parse "default via X.X.X.X dev ..."
            match = re.search(r"default via (\d+\.\d+\.\d+\.\d+)", result.stdout)
            if match:
                return match.group(1)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


async def ping_host(host: str, count: int = 3) -> tuple[bool, str]:
    """Ping a host and return (success, message)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ping",
            "-c",
            str(count),
            "-W",
            "2",  # 2 second timeout per ping
            host,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        output = stdout.decode()

        if proc.returncode == 0:
            # Extract average latency from ping output
            match = re.search(r"rtt min/avg/max/mdev = [\d.]+/([\d.]+)/", output)
            if match:
                avg_ms = match.group(1)
                return True, f"OK ({avg_ms} ms)"
            return True, "OK"
        else:
            return False, "Failed - No response"
    except TimeoutError:
        return False, "Failed - Timeout"
    except FileNotFoundError:
        return False, "Failed - ping not found"
    except Exception as e:
        return False, f"Failed - {e}"


class NetworkTestDialog(ModalScreen[None]):
    """A dialog for testing network connectivity via ping."""

    app: ZBoxTUI

    BINDINGS = [
        Binding("escape", "close", "Close", show=False),
        Binding("enter", "close", "Close", show=False),
        Binding("r", "retest", "Retest", show=False),
    ]

    DEFAULT_CSS = DCUI_DIALOG_CSS.format(dialog_class="NetworkTestDialog", width=60) + """
    NetworkTestDialog .test-row {
        height: 1;
    }

    NetworkTestDialog .test-label {
        width: 35;
        color: black;
    }

    NetworkTestDialog .test-status {
        width: 1fr;
        color: black;
    }

    NetworkTestDialog .test-status.--success {
        color: #006400;
    }

    NetworkTestDialog .test-status.--failure {
        color: #8b0000;
    }

    NetworkTestDialog .test-status.--pending {
        color: #555555;
    }
    """

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._gateway = get_default_gateway()

    def compose(self) -> ComposeResult:
        with Container(id="dialog-outer"):
            with Vertical(id="dialog-header"):
                yield Static("")  # Spacer before title
                yield Static("Test Network Connectivity", id="dialog-title")
                yield Static("")  # Spacer after title
                yield Static(
                    "Testing connectivity to default gateway/internet...",
                    id="dialog-subtitle",
                )
                yield Static("")  # Spacer after subtitle
            with Vertical(id="dialog-body"):
                # Gateway test
                if self._gateway:
                    gateway_label = f"Default Gateway ({self._gateway}):"
                else:
                    gateway_label = "Default Gateway (not found):"
                with Horizontal(classes="test-row"):
                    yield Static(gateway_label, classes="test-label")
                    yield Static(
                        "Testing...", classes="test-status --pending", id="gateway-status"
                    )

                # Google DNS test
                with Horizontal(classes="test-row"):
                    yield Static("Google DNS (8.8.8.8):", classes="test-label")
                    yield Static(
                        "Testing...", classes="test-status --pending", id="google-status"
                    )

                # Cloudflare DNS test
                with Horizontal(classes="test-row"):
                    yield Static("Cloudflare DNS (1.1.1.1):", classes="test-label")
                    yield Static(
                        "Testing...", classes="test-status --pending", id="cloudflare-status"
                    )

                yield Static("")  # Spacer before footer
                yield Static("<Enter> Close    <R> Retest", id="dialog-footer")

    def on_mount(self) -> None:
        """Start network tests on mount and take debug screenshot."""
        self.app.save_debug_screenshot("network_test_dialog")
        self._run_tests()

    @work(exclusive=True)
    async def _run_tests(self) -> None:
        """Run all network connectivity tests."""
        # Test gateway
        gateway_status = self.query_one("#gateway-status", Static)
        if self._gateway:
            success, message = await ping_host(self._gateway)
            gateway_status.remove_class("--pending")
            gateway_status.add_class("--success" if success else "--failure")
            gateway_status.update(message)
        else:
            gateway_status.remove_class("--pending")
            gateway_status.add_class("--failure")
            gateway_status.update("No gateway configured")

        # Test Google DNS
        google_status = self.query_one("#google-status", Static)
        success, message = await ping_host("8.8.8.8")
        google_status.remove_class("--pending")
        google_status.add_class("--success" if success else "--failure")
        google_status.update(message)

        # Test Cloudflare DNS
        cloudflare_status = self.query_one("#cloudflare-status", Static)
        success, message = await ping_host("1.1.1.1")
        cloudflare_status.remove_class("--pending")
        cloudflare_status.add_class("--success" if success else "--failure")
        cloudflare_status.update(message)

        # Update instruction text
        instruction = self.query_one("#dialog-subtitle", Static)
        instruction.update("Network connectivity test complete.")

    def action_retest(self) -> None:
        """Re-run all tests."""
        # Reset statuses
        for status_id in ["#gateway-status", "#google-status", "#cloudflare-status"]:
            status = self.query_one(status_id, Static)
            status.remove_class("--success", "--failure")
            status.add_class("--pending")
            status.update("Testing...")

        instruction = self.query_one("#dialog-subtitle", Static)
        instruction.update("Testing connectivity to default gateway/internet...")

        # Re-run tests
        self._run_tests()

    def action_close(self) -> None:
        """Close the dialog."""
        self.dismiss(None)


class TestDialog(ModalScreen[None]):
    """A template dialog demonstrating the standard DCUI modal layout.

    This dialog serves as a reference implementation for all modals in zBoxTUI.
    Structure:
        - White border around the entire dialog
        - Gray header section with centered yellow title and optional subtitle
        - Yellow body section with content and footer keybinds
    """

    app: ZBoxTUI

    BINDINGS = [
        Binding("escape", "close", "Close", show=False),
        Binding("enter", "close", "Close", show=False),
    ]

    DEFAULT_CSS = DCUI_DIALOG_CSS.format(dialog_class="TestDialog", width=70) + """
    TestDialog .content-line {
        height: 1;
        color: black;
    }
    """

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)

    def compose(self) -> ComposeResult:
        # Lorem ipsum lines for demonstration
        lorem_lines = [
            "Lorem ipsum dolor sit amet, consectetur adipiscing elit.",
            "Sed do eiusmod tempor incididunt ut labore et dolore magna.",
            "Ut enim ad minim veniam, quis nostrud exercitation ullamco.",
            "Laboris nisi ut aliquip ex ea commodo consequat voluptate.",
            "Duis aute irure dolor in reprehenderit in voluptate velit.",
            "Esse cillum dolore eu fugiat nulla pariatur excepteur sint.",
            "Occaecat cupidatat non proident, sunt in culpa qui officia.",
            "Deserunt mollit anim id est laborum sed ut perspiciatis unde.",
            "Omnis iste natus error sit voluptatem accusantium doloremque.",
            "Laudantium totam rem aperiam eaque ipsa quae ab illo veniam.",
        ]

        with Container(id="dialog-outer"):
            # Gray header section with centered text
            with Vertical(id="dialog-header"):
                yield Static("")  # Spacer before title
                yield Static("Test Dialog Title", id="dialog-title")
                yield Static("")  # Spacer after title
                yield Static(
                    "This is a summary or explanation of the dialog purpose.",
                    id="dialog-subtitle",
                )
                yield Static("")  # Spacer after subtitle

            # Yellow body section with content
            with Vertical(id="dialog-body"):
                for line in lorem_lines:
                    yield Static(line, classes="content-line")
                yield Static("")  # Spacer before footer
                yield Static("<Enter> Close    <Esc> Cancel", id="dialog-footer")

    def on_mount(self) -> None:
        """Take debug screenshot on mount."""
        self.app.save_debug_screenshot("test_dialog")

    def action_close(self) -> None:
        """Close the dialog."""
        self.dismiss(None)


def get_system_logs(lines: int = 100) -> list[str]:
    """Get system logs from journalctl or /var/log/syslog.

    Args:
        lines: Number of lines to retrieve.

    Returns:
        List of log lines.
    """
    # Try journalctl first (modern systemd systems)
    try:
        result = subprocess.run(
            ["journalctl", "--no-pager", "-n", str(lines), "--output=short"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().split("\n")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Fallback to /var/log/syslog
    try:
        result = subprocess.run(
            ["tail", "-n", str(lines), "/var/log/syslog"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().split("\n")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Fallback to /var/log/messages (RHEL-based systems)
    try:
        result = subprocess.run(
            ["tail", "-n", str(lines), "/var/log/messages"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().split("\n")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return ["No system logs available."]


class SystemLogsDialog(ModalScreen[None]):
    """A dialog for viewing system logs with scrolling support."""

    app: ZBoxTUI

    BINDINGS = [
        Binding("escape", "close", "Close", show=False),
        Binding("enter", "close", "Close", show=False),
        Binding("r", "refresh", "Refresh", show=False),
        Binding("up", "scroll_up", "Scroll Up", show=False),
        Binding("down", "scroll_down", "Scroll Down", show=False),
        Binding("pageup", "page_up", "Page Up", show=False),
        Binding("pagedown", "page_down", "Page Down", show=False),
        Binding("home", "scroll_home", "Scroll to Top", show=False),
        Binding("end", "scroll_end", "Scroll to Bottom", show=False),
    ]

    DEFAULT_CSS = DCUI_DIALOG_CSS.format(dialog_class="SystemLogsDialog", width="90%") + """
    SystemLogsDialog #dialog-outer {
        height: 90%;
    }

    SystemLogsDialog #dialog-body {
        height: 1fr;
        overflow: hidden;
    }

    SystemLogsDialog #log-container {
        height: 1fr;
        max-height: 100%;
        background: #1a1a1a;
        color: #cccccc;
        padding: 0 1;
        scrollbar-size-horizontal: 0;
    }
    """

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._log_lines: list[str] = []

    def compose(self) -> ComposeResult:
        from textual.widgets import RichLog

        with Container(id="dialog-outer"):
            with Vertical(id="dialog-header"):
                yield Static("")  # Spacer before title
                yield Static("System Logs", id="dialog-title")
                yield Static("")  # Spacer after title
                yield Static(
                    "Viewing recent system log entries",
                    id="dialog-subtitle",
                )
                yield Static("")  # Spacer after subtitle
            with Vertical(id="dialog-body"):
                yield RichLog(id="log-container", wrap=False, highlight=True)
                yield Static("")  # Spacer before footer
                yield Static(
                    "<↑/↓> Scroll  <PgUp/Dn> Page  <R> Refresh  <Enter/Esc> Close",
                    id="dialog-footer",
                )

    def on_mount(self) -> None:
        """Load logs on mount and take debug screenshot."""
        self.app.save_debug_screenshot("system_logs_dialog")
        self._load_logs()

    def _load_logs(self) -> None:
        """Load system logs and display them."""
        from rich.text import Text
        from textual.widgets import RichLog

        self._log_lines = get_system_logs(lines=1000)

        log_container = self.query_one("#log-container", RichLog)
        log_container.clear()

        for line in self._log_lines:
            # Create a Rich Text object (no markup parsing issues)
            text = Text(line)
            # Color-code based on log level
            line_lower = line.lower()
            if "error" in line_lower or "fail" in line_lower or "crit" in line_lower:
                text.stylize("red")
            elif "warn" in line_lower:
                text.stylize("yellow")
            elif "info" in line_lower:
                text.stylize("green")
            log_container.write(text)

        # Scroll to bottom to show most recent logs
        log_container.scroll_end(animate=False)

        # Update subtitle with line count
        subtitle = self.query_one("#dialog-subtitle", Static)
        subtitle.update(f"Showing {len(self._log_lines)} recent log entries")

    def action_refresh(self) -> None:
        """Refresh the logs."""
        self._load_logs()

    def action_scroll_up(self) -> None:
        """Scroll up one line."""
        from textual.widgets import RichLog

        log_container = self.query_one("#log-container", RichLog)
        log_container.scroll_up()

    def action_scroll_down(self) -> None:
        """Scroll down one line."""
        from textual.widgets import RichLog

        log_container = self.query_one("#log-container", RichLog)
        log_container.scroll_down()

    def action_page_up(self) -> None:
        """Scroll up one page."""
        from textual.widgets import RichLog

        log_container = self.query_one("#log-container", RichLog)
        log_container.scroll_page_up()

    def action_page_down(self) -> None:
        """Scroll down one page."""
        from textual.widgets import RichLog

        log_container = self.query_one("#log-container", RichLog)
        log_container.scroll_page_down()

    def action_scroll_home(self) -> None:
        """Scroll to the beginning."""
        from textual.widgets import RichLog

        log_container = self.query_one("#log-container", RichLog)
        log_container.scroll_home()

    def action_scroll_end(self) -> None:
        """Scroll to the end."""
        from textual.widgets import RichLog

        log_container = self.query_one("#log-container", RichLog)
        log_container.scroll_end()

    def action_close(self) -> None:
        """Close the dialog."""
        self.dismiss(None)


def get_zbox_config() -> list[str]:
    """Read the zBox configuration file.

    Returns:
        List of lines from /etc/zbox.config or error message.
    """
    config_path = "/etc/zbox.config"
    try:
        with open(config_path) as f:
            return f.read().strip().split("\n")
    except FileNotFoundError:
        return [f"Configuration file not found: {config_path}"]
    except PermissionError:
        return [f"Permission denied reading: {config_path}"]
    except Exception as e:
        return [f"Error reading config: {e}"]


class ZBoxLogsDialog(ModalScreen[None]):
    """A dialog for viewing zBox configuration file."""

    app: ZBoxTUI

    BINDINGS = [
        Binding("escape", "close", "Close", show=False),
        Binding("enter", "close", "Close", show=False),
        Binding("r", "refresh", "Refresh", show=False),
        Binding("up", "scroll_up", "Scroll Up", show=False),
        Binding("down", "scroll_down", "Scroll Down", show=False),
        Binding("pageup", "page_up", "Page Up", show=False),
        Binding("pagedown", "page_down", "Page Down", show=False),
        Binding("home", "scroll_home", "Scroll to Top", show=False),
        Binding("end", "scroll_end", "Scroll to Bottom", show=False),
    ]

    DEFAULT_CSS = DCUI_DIALOG_CSS.format(dialog_class="ZBoxLogsDialog", width="90%") + """
    ZBoxLogsDialog #dialog-outer {
        height: 90%;
    }

    ZBoxLogsDialog #dialog-body {
        height: 1fr;
        overflow: hidden;
    }

    ZBoxLogsDialog #log-container {
        height: 1fr;
        max-height: 100%;
        background: #1a1a1a;
        color: #cccccc;
        padding: 0 1;
        scrollbar-size-horizontal: 0;
    }
    """

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._config_lines: list[str] = []

    def compose(self) -> ComposeResult:
        from textual.widgets import RichLog

        with Container(id="dialog-outer"):
            with Vertical(id="dialog-header"):
                yield Static("")  # Spacer before title
                yield Static("zBox Configuration", id="dialog-title")
                yield Static("")  # Spacer after title
                yield Static(
                    "Viewing /etc/zbox.config",
                    id="dialog-subtitle",
                )
                yield Static("")  # Spacer after subtitle
            with Vertical(id="dialog-body"):
                yield RichLog(id="log-container", wrap=False, highlight=True)
                yield Static("")  # Spacer before footer
                yield Static(
                    "<↑/↓> Scroll  <PgUp/Dn> Page  <R> Refresh  <Enter/Esc> Close",
                    id="dialog-footer",
                )

    def on_mount(self) -> None:
        """Load config on mount and take debug screenshot."""
        self.app.save_debug_screenshot("zbox_logs_dialog")
        self._load_config()

    def _load_config(self) -> None:
        """Load zBox config and display it."""
        from rich.text import Text
        from textual.widgets import RichLog

        self._config_lines = get_zbox_config()

        log_container = self.query_one("#log-container", RichLog)
        log_container.clear()

        for line in self._config_lines:
            text = Text(line)
            log_container.write(text)

        # Scroll to top for config file
        log_container.scroll_home(animate=False)

        # Update subtitle with line count
        subtitle = self.query_one("#dialog-subtitle", Static)
        subtitle.update(f"Viewing /etc/zbox.config ({len(self._config_lines)} lines)")

    def action_refresh(self) -> None:
        """Refresh the config."""
        self._load_config()

    def action_scroll_up(self) -> None:
        """Scroll up one line."""
        from textual.widgets import RichLog

        log_container = self.query_one("#log-container", RichLog)
        log_container.scroll_up()

    def action_scroll_down(self) -> None:
        """Scroll down one line."""
        from textual.widgets import RichLog

        log_container = self.query_one("#log-container", RichLog)
        log_container.scroll_down()

    def action_page_up(self) -> None:
        """Scroll up one page."""
        from textual.widgets import RichLog

        log_container = self.query_one("#log-container", RichLog)
        log_container.scroll_page_up()

    def action_page_down(self) -> None:
        """Scroll down one page."""
        from textual.widgets import RichLog

        log_container = self.query_one("#log-container", RichLog)
        log_container.scroll_page_down()

    def action_scroll_home(self) -> None:
        """Scroll to the beginning."""
        from textual.widgets import RichLog

        log_container = self.query_one("#log-container", RichLog)
        log_container.scroll_home()

    def action_scroll_end(self) -> None:
        """Scroll to the end."""
        from textual.widgets import RichLog

        log_container = self.query_one("#log-container", RichLog)
        log_container.scroll_end()

    def action_close(self) -> None:
        """Close the dialog."""
        self.dismiss(None)

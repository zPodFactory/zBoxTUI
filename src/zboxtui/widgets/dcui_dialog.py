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

from ..utils.logging import get_logger

if TYPE_CHECKING:
    from textual.events import Key

    from ..app import ZBoxTUI

log = get_logger("dialogs")


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

    DEFAULT_CSS = DCUI_DIALOG_CSS.format(dialog_class="LoginDialog", width=45) + """
    LoginDialog .form-row {
        height: 1;
        width: 100%;
    }

    LoginDialog .form-label {
        width: 15;
        color: black;
        height: 1;
        content-align: left middle;
    }

    LoginDialog .form-input {
        width: 1fr;
        background: #3a3a3a;
        color: white;
        border: none;
        height: 1;
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

    DEFAULT_CSS = DCUI_DIALOG_CSS.format(dialog_class="PasswordDialog", width=45) + """
    PasswordDialog .form-row {
        height: 1;
        width: 100%;
    }

    PasswordDialog .form-label {
        width: 20;
        color: black;
        height: 1;
        content-align: left middle;
    }

    PasswordDialog .form-input {
        width: 1fr;
        background: #3a3a3a;
        color: white;
        border: none;
        height: 1;
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
            log.warning("Password change failed: empty password")
            error_msg.update("Error: Password cannot be empty")
            self.query_one("#password-input", Input).focus()
            return

        if password != confirm:
            log.warning("Password change failed: passwords do not match")
            error_msg.update("Error: Passwords do not match")
            self.query_one("#confirm-input", Input).value = ""
            self.query_one("#confirm-input", Input).focus()
            return

        if len(password) < 4:
            log.warning("Password change failed: password too short")
            error_msg.update("Error: Password must be at least 4 characters")
            return

        # Apply the password change
        log.info("Attempting to change root password via chpasswd")
        try:
            result = subprocess.run(
                ["chpasswd"],
                input=f"root:{password}\n",
                capture_output=True,
                text=True,
                timeout=10,
            )
            log.debug(
                "chpasswd returned: returncode=%d, stderr=%r", result.returncode, result.stderr
            )
            if result.returncode == 0:
                log.info("Root password changed successfully")
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
                log.error("chpasswd failed: %s", result.stderr.strip() or "Unknown error")
                error_msg.update(f"Error: {result.stderr.strip() or 'Failed to change password'}")
        except subprocess.TimeoutExpired:
            log.error("chpasswd timed out")
            error_msg.update("Error: Password change timed out")
        except FileNotFoundError:
            log.error("chpasswd command not found")
            error_msg.update("Error: chpasswd command not found")
        except Exception as e:
            log.exception("Unexpected error changing password: %s", e)
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
    log.debug("Fetching default gateway via 'ip route show default'")
    try:
        result = subprocess.run(
            ["ip", "route", "show", "default"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        log.debug("ip route show default: returncode=%d", result.returncode)
        if result.returncode == 0:
            # Parse "default via X.X.X.X dev ..."
            match = re.search(r"default via (\d+\.\d+\.\d+\.\d+)", result.stdout)
            if match:
                gateway = match.group(1)
                log.info("Default gateway: %s", gateway)
                return gateway
        log.warning("No default gateway found in route output")
    except subprocess.TimeoutExpired:
        log.warning("ip route show default timed out")
    except FileNotFoundError:
        log.warning("ip command not found")
    return None


async def ping_host(host: str, count: int = 3) -> tuple[bool, str]:
    """Ping a host and return (success, message)."""
    log.debug("Pinging host: %s (count=%d)", host, count)
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
        log.debug("ping %s: returncode=%d", host, proc.returncode)

        if proc.returncode == 0:
            # Extract average latency from ping output
            match = re.search(r"rtt min/avg/max/mdev = [\d.]+/([\d.]+)/", output)
            if match:
                avg_ms = match.group(1)
                log.info("Ping %s: OK (%s ms)", host, avg_ms)
                return True, f"OK ({avg_ms} ms)"
            log.info("Ping %s: OK", host)
            return True, "OK"
        else:
            log.warning("Ping %s: No response", host)
            return False, "Failed - No response"
    except TimeoutError:
        log.warning("Ping %s: Timeout", host)
        return False, "Failed - Timeout"
    except FileNotFoundError:
        log.error("ping command not found")
        return False, "Failed - ping not found"
    except Exception as e:
        log.exception("Ping %s failed: %s", host, e)
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
    log.debug("Fetching system logs via 'journalctl -n %d'", lines)
    try:
        result = subprocess.run(
            ["journalctl", "--no-pager", "-n", str(lines), "--output=short"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        log.debug("journalctl: returncode=%d", result.returncode)
        if result.returncode == 0 and result.stdout.strip():
            log_lines = result.stdout.strip().split("\n")
            log.info("Retrieved %d log lines via journalctl", len(log_lines))
            return log_lines
    except subprocess.TimeoutExpired:
        log.warning("journalctl timed out")
    except FileNotFoundError:
        log.debug("journalctl not found")

    # Fallback to /var/log/syslog
    log.debug("Fallback: reading /var/log/syslog")
    try:
        result = subprocess.run(
            ["tail", "-n", str(lines), "/var/log/syslog"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        log.debug("tail /var/log/syslog: returncode=%d", result.returncode)
        if result.returncode == 0 and result.stdout.strip():
            log_lines = result.stdout.strip().split("\n")
            log.info("Retrieved %d log lines from /var/log/syslog", len(log_lines))
            return log_lines
    except subprocess.TimeoutExpired:
        log.warning("tail /var/log/syslog timed out")
    except FileNotFoundError:
        log.debug("/var/log/syslog not found or tail not available")

    # Fallback to /var/log/messages (RHEL-based systems)
    log.debug("Fallback: reading /var/log/messages")
    try:
        result = subprocess.run(
            ["tail", "-n", str(lines), "/var/log/messages"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        log.debug("tail /var/log/messages: returncode=%d", result.returncode)
        if result.returncode == 0 and result.stdout.strip():
            log_lines = result.stdout.strip().split("\n")
            log.info("Retrieved %d log lines from /var/log/messages", len(log_lines))
            return log_lines
    except subprocess.TimeoutExpired:
        log.warning("tail /var/log/messages timed out")
    except FileNotFoundError:
        log.debug("/var/log/messages not found or tail not available")

    log.warning("No system logs available from any source")
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
    log.debug("Reading zBox config from: %s", config_path)
    try:
        with open(config_path) as f:
            lines = f.read().strip().split("\n")
            log.info("Read %d lines from %s", len(lines), config_path)
            return lines
    except FileNotFoundError:
        log.warning("Configuration file not found: %s", config_path)
        return [f"Configuration file not found: {config_path}"]
    except PermissionError:
        log.error("Permission denied reading: %s", config_path)
        return [f"Permission denied reading: {config_path}"]
    except Exception as e:
        log.exception("Error reading config %s: %s", config_path, e)
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


class NetworkInterfaceDialog(ModalScreen[str | None]):
    """A dialog for selecting a network interface to configure."""

    app: ZBoxTUI

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("up", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("enter", "select", "Select", show=False),
    ]

    DEFAULT_CSS = DCUI_DIALOG_CSS.format(dialog_class="NetworkInterfaceDialog", width=50) + """
    NetworkInterfaceDialog .interface-item {
        height: 1;
        width: 100%;
        padding: 0 1;
        background: #ffd700;
        color: black;
    }

    NetworkInterfaceDialog .interface-item.--selected {
        background: #5a5a5a;
        color: white;
    }

    NetworkInterfaceDialog #no-interfaces {
        color: #8b0000;
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
        from ..utils.system import get_physical_interfaces

        self._interfaces = get_physical_interfaces()
        self._selected_index = 0

    def compose(self) -> ComposeResult:
        with Container(id="dialog-outer"):
            with Vertical(id="dialog-header"):
                yield Static("")  # Spacer before title
                yield Static("Select Network Interface", id="dialog-title")
                yield Static("")  # Spacer after title
                yield Static(
                    "Choose an interface to configure",
                    id="dialog-subtitle",
                )
                yield Static("")  # Spacer after subtitle
            with Vertical(id="dialog-body"):
                if not self._interfaces:
                    yield Static("No physical interfaces found", id="no-interfaces")
                else:
                    for i, iface in enumerate(self._interfaces):
                        label = f"{iface.name} ({iface.ipv4})"
                        classes = "interface-item"
                        if i == 0:
                            classes += " --selected"
                        yield Static(label, classes=classes, id=f"iface-{i}")
                yield Static("")  # Spacer before footer
                yield Static("<Enter> Select    <Esc> Cancel", id="dialog-footer")

    def on_mount(self) -> None:
        """Take debug screenshot on mount."""
        self.app.save_debug_screenshot("network_interface_dialog")

    def _get_item_count(self) -> int:
        """Get number of selectable items."""
        return len(self._interfaces)

    def action_cursor_up(self) -> None:
        """Move cursor up."""
        if self._get_item_count() == 0:
            return
        # Remove selection from old item
        old_widget = self.query_one(f"#iface-{self._selected_index}", Static)
        old_widget.remove_class("--selected")
        # Update index
        self._selected_index = (self._selected_index - 1) % self._get_item_count()
        # Add selection to new item
        new_widget = self.query_one(f"#iface-{self._selected_index}", Static)
        new_widget.add_class("--selected")

    def action_cursor_down(self) -> None:
        """Move cursor down."""
        if self._get_item_count() == 0:
            return
        # Remove selection from old item
        old_widget = self.query_one(f"#iface-{self._selected_index}", Static)
        old_widget.remove_class("--selected")
        # Update index
        self._selected_index = (self._selected_index + 1) % self._get_item_count()
        # Add selection to new item
        new_widget = self.query_one(f"#iface-{self._selected_index}", Static)
        new_widget.add_class("--selected")

    def action_select(self) -> None:
        """Select the current interface."""
        if self._get_item_count() == 0:
            self.dismiss(None)
            return
        selected_iface = self._interfaces[self._selected_index]
        log.info("Selected interface: %s", selected_iface.name)
        self.dismiss(selected_iface.name)

    def action_cancel(self) -> None:
        """Cancel the dialog."""
        self.dismiss(None)


class NetworkConfigDialog(ModalScreen[bool]):
    """A dialog for configuring a network interface's IPv4 settings."""

    app: ZBoxTUI

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("tab", "focus_next", "Next Field", show=False),
        Binding("shift+tab", "focus_previous", "Previous Field", show=False),
    ]

    DEFAULT_CSS = DCUI_DIALOG_CSS.format(dialog_class="NetworkConfigDialog", width=55) + """
    NetworkConfigDialog .form-row {
        height: 1;
        width: 100%;
    }

    NetworkConfigDialog .form-label {
        width: 15;
        color: black;
        height: 1;
        content-align: left middle;
    }

    NetworkConfigDialog .form-input {
        width: 1fr;
        background: #3a3a3a;
        color: white;
        border: none;
        height: 1;
    }

    NetworkConfigDialog .form-input:focus {
        background: #4a4a4a;
    }

    NetworkConfigDialog .dhcp-field {
        width: 1fr;
        background: #3a3a3a;
        height: 1;
    }

    NetworkConfigDialog .dhcp-value {
        width: 1fr;
        color: white;
        padding: 0 1;
        content-align: left middle;
    }

    NetworkConfigDialog .dhcp-tag {
        width: auto;
        color: #888888;
        padding: 0 1;
        content-align: right middle;
    }

    NetworkConfigDialog #dhcp-row {
        height: 1;
        width: 100%;
    }

    NetworkConfigDialog #dhcp-label {
        color: black;
    }

    NetworkConfigDialog #dhcp-info {
        color: #555555;
        margin-left: 1;
    }

    NetworkConfigDialog #error-message {
        color: #8b0000;
        height: 1;
        text-align: center;
    }

    NetworkConfigDialog #section-label {
        color: #555555;
        height: 1;
        margin-top: 1;
    }
    """

    def __init__(
        self,
        interface_name: str,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._interface_name = interface_name
        from ..utils.system import get_interface_config

        self._config = get_interface_config(interface_name)
        self._is_dhcp = self._config.is_dhcp

    def compose(self) -> ComposeResult:
        # Build DHCP label with current IP info if DHCP
        dhcp_info = ""
        if self._config.is_dhcp and self._config.ipv4:
            dhcp_info = f"({self._config.ipv4}/{self._config.cidr} via {self._config.gateway})"

        with Container(id="dialog-outer"):
            with Vertical(id="dialog-header"):
                yield Static("")  # Spacer before title
                yield Static(
                    f"Configure Network: {self._interface_name}", id="dialog-title"
                )
                yield Static("")  # Spacer after title
                yield Static(
                    "Configure IPv4 settings for this interface",
                    id="dialog-subtitle",
                )
                yield Static("")  # Spacer after subtitle
            with Vertical(id="dialog-body"):
                # DHCP toggle row
                with Horizontal(id="dhcp-row"):
                    dhcp_text = "[X] Use DHCP" if self._is_dhcp else "[ ] Use DHCP"
                    yield Static(dhcp_text, id="dhcp-label")
                    yield Static(dhcp_info, id="dhcp-info")

                yield Static("Static Configuration:", id="section-label")

                # IP Address - DHCP display (shown when DHCP enabled)
                with Horizontal(classes="form-row", id="ip-dhcp-row"):
                    yield Static("IP Address:", classes="form-label")
                    with Horizontal(classes="dhcp-field"):
                        yield Static(self._config.ipv4 or "-", classes="dhcp-value")
                        yield Static("(DHCP)", classes="dhcp-tag")

                # IP Address - Input (shown when static mode)
                with Horizontal(classes="form-row", id="ip-input-row"):
                    yield Static("IP Address:", classes="form-label")
                    yield Input(
                        value=self._config.ipv4,
                        placeholder="192.168.1.100",
                        classes="form-input",
                        id="ip-input",
                    )

                # Netmask - DHCP display
                with Horizontal(classes="form-row", id="netmask-dhcp-row"):
                    yield Static("Netmask:", classes="form-label")
                    with Horizontal(classes="dhcp-field"):
                        yield Static(self._config.netmask or "-", classes="dhcp-value")
                        yield Static("(DHCP)", classes="dhcp-tag")

                # Netmask - Input
                with Horizontal(classes="form-row", id="netmask-input-row"):
                    yield Static("Netmask:", classes="form-label")
                    yield Input(
                        value=self._config.netmask,
                        placeholder="255.255.255.0",
                        classes="form-input",
                        id="netmask-input",
                    )

                # Gateway - DHCP display
                with Horizontal(classes="form-row", id="gateway-dhcp-row"):
                    yield Static("Gateway:", classes="form-label")
                    with Horizontal(classes="dhcp-field"):
                        yield Static(self._config.gateway or "-", classes="dhcp-value")
                        yield Static("(DHCP)", classes="dhcp-tag")

                # Gateway - Input
                with Horizontal(classes="form-row", id="gateway-input-row"):
                    yield Static("Gateway:", classes="form-label")
                    yield Input(
                        value=self._config.gateway,
                        placeholder="192.168.1.1",
                        classes="form-input",
                        id="gateway-input",
                    )

                # DNS Server 1 - DHCP display
                with Horizontal(classes="form-row", id="dns1-dhcp-row"):
                    yield Static("DNS Server 1:", classes="form-label")
                    with Horizontal(classes="dhcp-field"):
                        yield Static(self._config.dns1 or "-", classes="dhcp-value")
                        yield Static("(DHCP)", classes="dhcp-tag")

                # DNS Server 1 - Input
                with Horizontal(classes="form-row", id="dns1-input-row"):
                    yield Static("DNS Server 1:", classes="form-label")
                    yield Input(
                        value=self._config.dns1,
                        placeholder="8.8.8.8",
                        classes="form-input",
                        id="dns1-input",
                    )

                # DNS Server 2 - DHCP display
                with Horizontal(classes="form-row", id="dns2-dhcp-row"):
                    yield Static("DNS Server 2:", classes="form-label")
                    with Horizontal(classes="dhcp-field"):
                        yield Static(self._config.dns2 or "-", classes="dhcp-value")
                        yield Static("(DHCP)", classes="dhcp-tag")

                # DNS Server 2 - Input
                with Horizontal(classes="form-row", id="dns2-input-row"):
                    yield Static("DNS Server 2:", classes="form-label")
                    yield Input(
                        value=self._config.dns2,
                        placeholder="8.8.4.4",
                        classes="form-input",
                        id="dns2-input",
                    )

                yield Static("", id="error-message")
                yield Static("")  # Spacer before footer
                yield Static(
                    "<Space> Toggle DHCP    <Enter> Apply    <Esc> Cancel",
                    id="dialog-footer",
                )

    def on_mount(self) -> None:
        """Set initial visibility and take debug screenshot."""
        self._update_field_visibility()
        self.app.save_debug_screenshot("network_config_dialog")

    def _update_field_visibility(self) -> None:
        """Show/hide DHCP display vs Input rows based on current mode."""
        field_names = ["ip", "netmask", "gateway", "dns1", "dns2"]

        for field in field_names:
            dhcp_row = self.query_one(f"#{field}-dhcp-row", Horizontal)
            input_row = self.query_one(f"#{field}-input-row", Horizontal)

            # Show DHCP row when DHCP enabled, hide input row (and vice versa)
            dhcp_row.display = self._is_dhcp
            input_row.display = not self._is_dhcp

        # Focus first input when in static mode
        if not self._is_dhcp:
            self.query_one("#ip-input", Input).focus()

    def on_key(self, event: Key) -> None:
        """Handle key presses."""
        if event.key == "space":
            self._toggle_dhcp()
            event.stop()
        elif event.key == "enter":
            self._submit()
            event.stop()

    def _toggle_dhcp(self) -> None:
        """Toggle DHCP mode on/off."""
        self._is_dhcp = not self._is_dhcp

        # Update DHCP label
        dhcp_label = self.query_one("#dhcp-label", Static)
        dhcp_text = "[X] Use DHCP" if self._is_dhcp else "[ ] Use DHCP"
        dhcp_label.update(dhcp_text)

        # Switch between DHCP display rows and Input rows
        self._update_field_visibility()

        log.debug("DHCP toggled to: %s", self._is_dhcp)

    def _submit(self) -> None:
        """Validate and apply configuration."""
        from ..utils.system import netmask_to_cidr, validate_ipv4

        error_msg = self.query_one("#error-message", Static)

        if not self._is_dhcp:
            # Validate static configuration
            ip = self.query_one("#ip-input", Input).value.strip()
            netmask = self.query_one("#netmask-input", Input).value.strip()
            gateway = self.query_one("#gateway-input", Input).value.strip()
            dns1 = self.query_one("#dns1-input", Input).value.strip()
            dns2 = self.query_one("#dns2-input", Input).value.strip()

            # Validate required fields
            if not ip:
                error_msg.update("Error: IP Address is required")
                self.query_one("#ip-input", Input).focus()
                return
            if not validate_ipv4(ip):
                error_msg.update("Error: Invalid IP Address format")
                self.query_one("#ip-input", Input).focus()
                return

            if not netmask:
                error_msg.update("Error: Netmask is required")
                self.query_one("#netmask-input", Input).focus()
                return
            if not validate_ipv4(netmask):
                error_msg.update("Error: Invalid Netmask format")
                self.query_one("#netmask-input", Input).focus()
                return

            if not gateway:
                error_msg.update("Error: Gateway is required")
                self.query_one("#gateway-input", Input).focus()
                return
            if not validate_ipv4(gateway):
                error_msg.update("Error: Invalid Gateway format")
                self.query_one("#gateway-input", Input).focus()
                return

            # DNS servers are optional but must be valid if provided
            if dns1 and not validate_ipv4(dns1):
                error_msg.update("Error: Invalid DNS Server 1 format")
                self.query_one("#dns1-input", Input).focus()
                return
            if dns2 and not validate_ipv4(dns2):
                error_msg.update("Error: Invalid DNS Server 2 format")
                self.query_one("#dns2-input", Input).focus()
                return

            cidr = netmask_to_cidr(netmask)
            config_summary = f"Static: {ip}/{cidr} via {gateway}"
        else:
            config_summary = "DHCP"
            ip = netmask = gateway = dns1 = dns2 = ""

        # Clear error and show confirmation dialog
        error_msg.update("")
        log.info(
            "Network config validated for %s: %s",
            self._interface_name,
            config_summary,
        )

        # Show confirmation dialog
        self.app.push_screen(
            MessageDialog(
                "Confirm Network Configuration",
                f"Apply the following configuration to {self._interface_name}?\n\n"
                f"Mode: {config_summary}\n\n"
                "This will modify /etc/network/interfaces and restart the interface.",
            ),
            callback=lambda confirmed: self._apply_config(confirmed) if confirmed else None,
        )

    def _apply_config(self, confirmed: bool) -> None:
        """Apply the network configuration."""
        import shutil

        if not confirmed:
            return

        error_msg = self.query_one("#error-message", Static)
        iface = self._interface_name

        # Gather values
        if self._is_dhcp:
            method = "dhcp"
            ip = netmask = gateway = dns1 = dns2 = ""
        else:
            method = "static"
            ip = self.query_one("#ip-input", Input).value.strip()
            netmask = self.query_one("#netmask-input", Input).value.strip()
            gateway = self.query_one("#gateway-input", Input).value.strip()
            dns1 = self.query_one("#dns1-input", Input).value.strip()
            dns2 = self.query_one("#dns2-input", Input).value.strip()

        log.info(
            "Applying network config: iface=%s method=%s ip=%s netmask=%s gw=%s",
            iface,
            method,
            ip,
            netmask,
            gateway,
        )

        interfaces_file = "/etc/network/interfaces"

        try:
            # Backup existing config
            backup_file = f"{interfaces_file}.bak"
            try:
                shutil.copy(interfaces_file, backup_file)
                log.info("Backed up %s to %s", interfaces_file, backup_file)
            except FileNotFoundError:
                log.warning("No existing %s to backup", interfaces_file)

            # Read existing config
            try:
                with open(interfaces_file) as f:
                    existing_content = f.read()
            except FileNotFoundError:
                existing_content = ""

            # Build new interface config
            if method == "dhcp":
                new_iface_config = f"auto {iface}\niface {iface} inet dhcp\n"
            else:
                dns_line = ""
                if dns1 or dns2:
                    dns_servers = " ".join(filter(None, [dns1, dns2]))
                    dns_line = f"    dns-nameservers {dns_servers}\n"
                new_iface_config = (
                    f"auto {iface}\n"
                    f"iface {iface} inet static\n"
                    f"    address {ip}\n"
                    f"    netmask {netmask}\n"
                    f"    gateway {gateway}\n"
                    f"{dns_line}"
                )

            # Remove existing config for this interface and add new
            import re as re_module

            # Pattern to match the interface stanza (auto line + iface line + indented options)
            iface_escaped = re_module.escape(iface)
            pattern = (
                rf"(auto\s+{iface_escaped}\n)?"
                rf"iface\s+{iface_escaped}\s+inet\s+\w+[^\n]*\n"
                r"(?:\s+[^\n]+\n)*"
            )
            new_content = re_module.sub(pattern, "", existing_content)

            # Ensure file ends with newline before adding new config
            if new_content and not new_content.endswith("\n"):
                new_content += "\n"
            if new_content and not new_content.endswith("\n\n"):
                new_content += "\n"

            new_content += new_iface_config

            # Write new config
            with open(interfaces_file, "w") as f:
                f.write(new_content)
            log.info("Wrote new interface config to %s", interfaces_file)

            # Restart the interface with proper cleanup
            log.info("Restarting interface %s", iface)

            # Release DHCP lease if switching to static (prevents lingering DHCP IPs)
            if method == "static":
                log.debug("Releasing DHCP lease for %s", iface)
                subprocess.run(
                    ["dhclient", "-r", iface],
                    capture_output=True,
                    timeout=10,
                )

            # Flush all addresses from interface to ensure clean state
            log.debug("Flushing addresses from %s", iface)
            subprocess.run(
                ["ip", "addr", "flush", "dev", iface],
                capture_output=True,
                timeout=10,
            )

            # Take interface down
            result = subprocess.run(
                ["ifdown", "--force", iface],
                capture_output=True,
                text=True,
                timeout=30,
            )
            log.debug("ifdown %s: returncode=%d", iface, result.returncode)

            # Bring interface up with new configuration
            result = subprocess.run(
                ["ifup", iface],
                capture_output=True,
                text=True,
                timeout=30,
            )
            log.debug("ifup %s: returncode=%d stderr=%r", iface, result.returncode, result.stderr)

            if result.returncode == 0:
                log.info("Interface %s restarted successfully", iface)
                self.app.push_screen(
                    MessageDialog(
                        "Configuration Applied",
                        f"Network configuration for {iface} has been applied successfully.",
                    ),
                    callback=lambda _: self.dismiss(True),
                )
            else:
                log.error("Failed to restart interface: %s", result.stderr)
                error_msg.update(f"Error: {result.stderr.strip() or 'Failed to restart interface'}")

        except PermissionError:
            log.error("Permission denied modifying %s", interfaces_file)
            error_msg.update("Error: Permission denied. Run as root.")
        except subprocess.TimeoutExpired:
            log.error("Interface restart timed out")
            error_msg.update("Error: Interface restart timed out")
        except Exception as e:
            log.exception("Error applying network config: %s", e)
            error_msg.update(f"Error: {e}")

    def action_cancel(self) -> None:
        """Cancel the dialog."""
        self.dismiss(False)

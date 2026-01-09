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
                    "Testing connectivity to gateway and internet DNS servers...",
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
        instruction.update("Testing connectivity to gateway and internet DNS servers...")

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

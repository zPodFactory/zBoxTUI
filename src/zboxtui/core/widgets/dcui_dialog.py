"""Shared modal dialog widgets (header, body, footer layout)."""

from __future__ import annotations

from dataclasses import dataclass

import asyncio
import re
import subprocess
import time
from collections import deque
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from rich.spinner import Spinner
from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Input, Static

from ..utils.logging import get_logger, read_zboxtui_log_lines
from ..utils.privilege import verify_root_password
from ..utils.system_control import NetworkApplyRequest, apply_network_interface
from ..utils.system import (
    cpu_percent,
    format_size,
    get_cpu_count,
    get_cpu_info,
    get_disk_usage,
    get_memory_stats,
    read_cpu_times,
    read_net_bytes,
)
from .bar_chart import BarChart

# 1 GiB in bytes - memory and storage are reported in GB (1024-based).
_GIB = 1024**3

# Refresh rate for inline Rich Spinner animations. Textual doesn't auto-refresh
# Static widgets when their renderable is animated, so spinner-bearing Statics
# set this on auto_refresh while spinning and clear it (= None) when done.
_SPINNER_REFRESH = 1 / 15

if TYPE_CHECKING:
    from textual.events import Key

    from ...app import ZBoxTUI

log = get_logger("dialogs")

# Default footer for ack-only / completed modals.
DIALOG_FOOTER_CLOSE = "Press Enter to close"


def format_dialog_paragraphs(parts: list[str | None]) -> str:
    """Build dialog body text: join fragments with spaces, break on ``None``.

    Use short strings in source for readability; ``None`` starts a new paragraph
    (blank line). The rendered ``Static`` should use ``text-wrap: wrap`` so each
    paragraph fills the dialog width.
    """
    paragraphs: list[str] = []
    current: list[str] = []
    for part in parts:
        if part is None:
            if current:
                paragraphs.append(" ".join(current))
                current = []
            continue
        stripped = part.strip()
        if not stripped:
            if current:
                paragraphs.append(" ".join(current))
                current = []
            continue
        current.append(stripped)
    if current:
        paragraphs.append(" ".join(current))
    return "\n\n".join(paragraphs)



# Shared layout/CSS for modal dialogs (header, body, footer).
# All colours come from the active theme ($z-bg, $z-panel, $z-crust, …).
DCUI_DIALOG_CSS = """
    /* Full-screen backdrop behind the centered dialog */
    {dialog_class} {{
        align: center middle;
        background: $z-crust;
    }}

    /* Dialog shell; borders are on header/body sections below */
    {dialog_class} #dialog-outer {{
        layout: vertical;
        width: {width};
        height: auto;
    }}

    /* Title bar ($z-panel) */
    {dialog_class} #dialog-header {{
        background: $z-panel;
        color: $z-panel-fg;
        height: auto;
        padding: 0 2;
        border-top: solid $z-border;
        border-left: solid $z-border;
        border-right: solid $z-border;
    }}

    {dialog_class} #dialog-title {{
        color: $z-title;
        text-align: center;
        height: 1;
    }}

    {dialog_class} #dialog-subtitle {{
        color: $z-panel-fg-dim;
        text-align: center;
        height: auto;
    }}

    /* Main content area ($z-bg) */
    {dialog_class} #dialog-body {{
        background: $z-bg;
        color: $z-fg;
        height: auto;
        padding: 1 2;
        border-bottom: solid $z-border;
        border-left: solid $z-border;
        border-right: solid $z-border;
    }}

    /* Keybind hints; last row inside #dialog-body */
    {dialog_class} #dialog-footer {{
        background: $z-bg;
        color: $z-fg;
        text-align: center;
        height: 1;
    }}
"""


class LoginDialog(ModalScreen[bool | None]):
    """Root password prompt using the standard modal layout."""

    app: ZBoxTUI

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("q", "cancel", "Cancel", show=False),
    ]

    DEFAULT_CSS = DCUI_DIALOG_CSS.format(dialog_class="LoginDialog", width=45) + """
    LoginDialog .form-row {
        height: 1;
        width: 100%;
    }

    LoginDialog .form-label {
        width: 15;
        color: $z-fg;
        height: 1;
        content-align: left middle;
    }

    LoginDialog .form-input {
        width: 1fr;
        background: $z-mantle;
        color: $z-panel-fg;
        border: none;
        height: 1;
    }

    LoginDialog .form-input:focus {
        background: $z-panel-focus;
    }

    LoginDialog #spinner {
        width: 3;
        height: 1;
        color: $z-fg-faint;
        content-align: center middle;
    }

    LoginDialog #spinner.--hidden {
        display: none;
    }

    LoginDialog #error-container {
        height: auto;
    }

    LoginDialog #error-container.--hidden {
        display: none;
    }

    LoginDialog #error-message {
        height: 1;
        text-align: center;
        color: $z-error;
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
                yield Static("")
                yield Static("Authentication Required", id="dialog-title")
                yield Static("")
                yield Static(
                    "Enter root password.",
                    id="dialog-subtitle",
                )
                yield Static("")
            with Vertical(id="dialog-body"):
                with Horizontal(classes="form-row"):
                    yield Static("Password:", classes="form-label")
                    yield Input(
                        password=True,
                        placeholder="root password",
                        classes="form-input",
                        id="password-input",
                    )
                    yield Static("", id="spinner", classes="--hidden")
                with Vertical(id="error-container", classes="--hidden"):
                    yield Static("")
                    yield Static("", id="error-message")
                yield Static("")
                yield Static("<Enter> OK    <Esc> Cancel", id="dialog-footer")

    def on_mount(self) -> None:
        self.query_one("#password-input", Input).focus()
        self.app.save_debug_screenshot("login_dialog")

    @on(Input.Submitted)
    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "password-input":
            self._submit()

    def _submit(self) -> None:
        password = self.query_one("#password-input", Input).value
        error_container = self.query_one("#error-container", Vertical)
        error_msg = self.query_one("#error-message", Static)

        if not password:
            error_container.remove_class("--hidden")
            error_msg.update("Error: Password is required")
            return

        error_container.add_class("--hidden")
        self.query_one("#password-input", Input).disabled = True
        self._start_spinner()
        self._verify_password(password)

    def _start_spinner(self) -> None:
        spinner = self.query_one("#spinner", Static)
        spinner.remove_class("--hidden")
        spinner.update(Spinner("dots"))
        spinner.auto_refresh = _SPINNER_REFRESH

    def _stop_spinner(self) -> None:
        spinner = self.query_one("#spinner", Static)
        spinner.auto_refresh = None
        spinner.add_class("--hidden")
        spinner.update("")

    @work(thread=True)
    def _verify_password(self, password: str) -> None:
        log.debug("Verifying root password")
        result = verify_root_password(password)
        self.app.call_from_thread(self._handle_verification_result, result)

    def _handle_verification_result(self, success: bool) -> None:
        self._stop_spinner()
        error_container = self.query_one("#error-container", Vertical)
        error_msg = self.query_one("#error-message", Static)
        password_input = self.query_one("#password-input", Input)

        password_input.disabled = False

        if success:
            log.info("Root authentication successful")
            self.dismiss(True)
            return

        log.warning("Root authentication failed")
        error_container.remove_class("--hidden")
        error_msg.update("Error: Invalid password")
        password_input.value = ""
        password_input.focus()

    def action_cancel(self) -> None:
        self.dismiss(None)


class PasswordDialog(ModalScreen[bool]):
    """Change-root-password form using the standard modal layout."""

    app: ZBoxTUI

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("q", "cancel", "Cancel", show=False),
    ]

    DEFAULT_CSS = DCUI_DIALOG_CSS.format(dialog_class="PasswordDialog", width=45) + """
    PasswordDialog .form-row {
        height: 1;
        width: 100%;
    }

    PasswordDialog .form-label {
        width: 20;
        color: $z-fg;
        height: 1;
        content-align: left middle;
    }

    PasswordDialog .form-input {
        width: 1fr;
        background: $z-mantle;
        color: $z-panel-fg;
        border: none;
        height: 1;
    }

    PasswordDialog .form-input:focus {
        background: $z-panel-focus;
    }

    PasswordDialog #error-message {
        color: $z-error;
        height: 1;
        text-align: center;
    }

    PasswordDialog #success-message {
        color: $z-success;
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
                yield Static("")
                yield Static("Configure Root Password", id="dialog-title")
                yield Static("")
                yield Static(
                    "Enter a new password for the root account.",
                    id="dialog-subtitle",
                )
                yield Static("")
            with Vertical(id="dialog-body"):
                with Horizontal(classes="form-row"):
                    yield Static("New Password:", classes="form-label")
                    yield Input(
                        password=True,
                        placeholder="secure password",
                        classes="form-input",
                        id="password-input",
                    )
                with Horizontal(classes="form-row"):
                    yield Static("Confirm Password:", classes="form-label")
                    yield Input(
                        password=True,
                        placeholder="secure password",
                        classes="form-input",
                        id="confirm-input",
                    )
                yield Static("", id="error-message")
                yield Static("")
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
                        ack_only=True,
                    ),
                    callback=dismiss_screen_after_modal(self, True),
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


def dismiss_screen_after_modal(
    screen: ModalScreen[Any],
    result: Any = True,
    *,
    before_dismiss: Callable[[], None] | None = None,
) -> Callable[[Any], None]:
    """Return a ``push_screen`` callback that dismisses ``screen`` safely.

    Textual rejects ``await screen.dismiss()`` when invoked from another
    screen's dismiss handler (e.g. a success MessageDialog closing). Defer
    the parent dismiss to the next event-loop tick via :meth:`call_later`.

    Optional ``before_dismiss`` runs first (e.g. refresh the dashboard after
    hostname or network changes).
    """
    def _close(_child_result: Any) -> None:
        if before_dismiss is not None:
            before_dismiss()

        def _dismiss_parent() -> None:
            # Do not return dismiss()'s AwaitComplete — invoke() would await it.
            screen.dismiss(result)

        screen.call_later(_dismiss_parent)

    return _close


class MessageDialog(ModalScreen[bool]):
    """Simple message modal.

    Default: OK / Cancel confirmation (``ack_only=False``).
    ``ack_only=True``: post-action notice — only Close; Esc also closes.
    """

    app: ZBoxTUI

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("enter", "confirm", "OK", show=False),
        Binding("q", "cancel", "Cancel", show=False),
    ]

    DEFAULT_CSS = DCUI_DIALOG_CSS.format(dialog_class="MessageDialog", width=50) + """
    MessageDialog #dialog-message {
        color: $z-fg;
        height: auto;
    }
    """

    def __init__(
        self,
        title: str,
        message: str,
        *,
        ack_only: bool = False,
        before_confirm: Callable[[], None] | None = None,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._title = title
        self._message = message
        self._ack_only = ack_only
        self._before_confirm = before_confirm

    def compose(self) -> ComposeResult:
        footer = DIALOG_FOOTER_CLOSE if self._ack_only else "<Enter> OK    <Esc> Cancel"
        with Container(id="dialog-outer"):
            with Vertical(id="dialog-header"):
                yield Static("")
                yield Static(self._title, id="dialog-title")
                yield Static("")
            with Vertical(id="dialog-body"):
                yield Static(self._message, id="dialog-message")
                yield Static("")
                yield Static(footer, id="dialog-footer")

    def on_mount(self) -> None:
        """Take debug screenshot on mount."""
        # Use title as part of the filename, sanitized for filesystem
        safe_title = self._title.lower().replace(" ", "_").replace("/", "_")
        self.app.save_debug_screenshot(f"message_dialog_{safe_title}")

    def action_confirm(self) -> None:
        """Confirm the dialog."""
        if self._before_confirm is not None:
            self._before_confirm()
        self.dismiss(True)

    def action_cancel(self) -> None:
        """Cancel the dialog (ack-only modals treat Esc/Q as Close)."""
        if self._ack_only:
            self.action_confirm()
            return
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


@dataclass
class _ConnectivityTestTarget:
    """One row in the network connectivity test dialog."""

    label: str
    host: str | None = None


_CLOUDFLARE_DNS = "1.1.1.1"
_GOOGLE_DNS = "8.8.8.8"


def build_network_test_targets() -> list[_ConnectivityTestTarget]:
    """Targets in test order: gateway, configured DNS, Cloudflare, Google.

    Public resolver rows (1.1.1.1 / 8.8.8.8) are omitted when that address
    already appears as DNS Server 1 or 2 from ``/etc/network/interfaces``.
    """
    from ..utils.system import get_default_gateway, resolve_interface_dns_servers

    targets: list[_ConnectivityTestTarget] = []
    seen_hosts: set[str] = set()

    gw_ip, gw_iface = get_default_gateway()
    if gw_ip:
        targets.append(
            _ConnectivityTestTarget(f"Default Gateway ({gw_ip}):", gw_ip)
        )
        seen_hosts.add(gw_ip)
    else:
        targets.append(
            _ConnectivityTestTarget("Default Gateway (not found):", None)
        )

    if gw_iface:
        for index, dns_ip in enumerate(resolve_interface_dns_servers(gw_iface), start=1):
            if dns_ip in seen_hosts:
                continue
            seen_hosts.add(dns_ip)
            targets.append(
                _ConnectivityTestTarget(f"DNS Server {index} ({dns_ip}):", dns_ip)
            )

    # Skip Cloudflare/Google when already configured as dns-nameservers above.
    for label, dns_ip in (
        (f"Cloudflare DNS ({_CLOUDFLARE_DNS}):", _CLOUDFLARE_DNS),
        (f"Google DNS ({_GOOGLE_DNS}):", _GOOGLE_DNS),
    ):
        if dns_ip in seen_hosts:
            continue
        seen_hosts.add(dns_ip)
        targets.append(_ConnectivityTestTarget(label, dns_ip))

    return targets


class NetworkTestDialog(ModalScreen[None]):
    """A dialog for testing network connectivity via ping."""

    app: ZBoxTUI

    # Placeholder shown on rows whose test has not started yet.
    _PENDING_LABEL = "Pending"

    BINDINGS = [
        Binding("escape", "close", "Close", show=False),
        Binding("enter", "close", "Close", show=False),
        Binding("q", "close", "Close", show=False),
        Binding("r", "retest", "Retest", show=False),
    ]

    DEFAULT_CSS = DCUI_DIALOG_CSS.format(dialog_class="NetworkTestDialog", width=60) + """
    NetworkTestDialog .test-row {
        height: 1;
    }

    NetworkTestDialog .test-label {
        width: 35;
        color: $z-fg;
    }

    NetworkTestDialog .test-status {
        width: 1fr;
        color: $z-fg;
    }

    NetworkTestDialog .test-status.--success {
        color: $z-success;
    }

    NetworkTestDialog .test-status.--failure {
        color: $z-error;
    }

    NetworkTestDialog .test-status.--pending {
        color: $z-fg-faint;
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
        self._targets = build_network_test_targets()

    def compose(self) -> ComposeResult:
        with Container(id="dialog-outer"):
            with Vertical(id="dialog-header"):
                yield Static("")
                yield Static("Test Network Connectivity", id="dialog-title")
                yield Static("")
                yield Static(
                    "Testing gateway, DNS, and public resolvers...",
                    id="dialog-subtitle",
                )
                yield Static("")
            with Vertical(id="dialog-body"):
                pending = self._PENDING_LABEL
                for index, target in enumerate(self._targets):
                    with Horizontal(classes="test-row"):
                        yield Static(target.label, classes="test-label")
                        yield Static(
                            pending,
                            classes="test-status --pending",
                            id=f"test-status-{index}",
                        )

                yield Static("")
                yield Static("Press Enter to close    <R> Retest", id="dialog-footer")

    def on_mount(self) -> None:
        """Start network tests on mount and take debug screenshot."""
        self.app.save_debug_screenshot("network_test_dialog")
        self._run_tests()

    def _theme_dots(self, results: list[bool | None]) -> Text:
        """Theme-aware probe dots, spaced so they do not overlap the spinner."""
        from .probes import probe_dots as _probe_dots

        theme = self.app.current_theme
        return Text(" ") + _probe_dots(
            results,
            success=(theme.success if theme else None) or "green",
            error=(theme.error if theme else None) or "red",
            faint="grey50",
        )

    def _begin_test(self, status: Static, probe_count: int = 3) -> None:
        """Show the spinner alongside ``probe_count`` faint dot slots."""
        status.remove_class("--success", "--failure")
        status.add_class("--pending")
        status.update(Spinner("dots", text=self._theme_dots([None] * probe_count)))
        status.auto_refresh = _SPINNER_REFRESH

    def _finish_test(self, status: Static, success: bool, message: str) -> None:
        """Replace the spinning row with the plain summary line."""
        status.auto_refresh = None
        status.remove_class("--pending")
        status.add_class("--success" if success else "--failure")
        status.update(message)

    async def _run_target(self, host: str, status: Static) -> None:
        """Run 3 paced ICMP probes against ``host``, updating ``status``."""
        from .probes import run_probes, summarise

        self._begin_test(status, probe_count=3)

        def on_probe(results: list[bool | None], _latencies: list[float]) -> None:
            status.update(Spinner("dots", text=self._theme_dots(results)))

        results, latencies = await run_probes(host, count=3, on_progress=on_probe)
        ok, message = summarise(results, latencies)
        self._finish_test(status, ok, message)

    def _reset_test_rows(self) -> None:
        """Return every test row to the pre-run pending state."""
        for index in range(len(self._targets)):
            status = self.query_one(f"#test-status-{index}", Static)
            status.remove_class("--success", "--failure")
            status.add_class("--pending")
            status.update(self._PENDING_LABEL)

    @work(exclusive=True)
    async def _run_tests(self) -> None:
        """Run connectivity tests in order: GW, DNS, Cloudflare, Google."""
        for index, target in enumerate(self._targets):
            status = self.query_one(f"#test-status-{index}", Static)
            if target.host:
                await self._run_target(target.host, status)
            else:
                self._finish_test(status, False, "No gateway configured")

        instruction = self.query_one("#dialog-subtitle", Static)
        instruction.update("Network connectivity test complete.")

    def action_retest(self) -> None:
        """Re-run all tests."""
        self._reset_test_rows()
        instruction = self.query_one("#dialog-subtitle", Static)
        instruction.update("Testing gateway, DNS, and public resolvers...")
        self._run_tests()

    def action_close(self) -> None:
        """Close the dialog."""
        self.dismiss(None)



class AboutDialog(ModalScreen[None]):
    """About zBoxTUI — project summary and version."""

    app: ZBoxTUI

    BINDINGS = [
        Binding("escape", "close", "Close", show=False),
        Binding("enter", "close", "Close", show=False),
        Binding("q", "close", "Close", show=False),
    ]

    DEFAULT_CSS = DCUI_DIALOG_CSS.format(dialog_class="AboutDialog", width=70) + """
    AboutDialog #dialog-about {
        width: 100%;
        height: auto;
        color: $z-fg;
        text-wrap: wrap;
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
        from ... import __version__

        self._version = __version__

    def compose(self) -> ComposeResult:
        about_parts: list[str | None] = [
            "zBoxTUI is a DCUI-inspired terminal UI for",
            "zBox appliances on Debian.",
            "Layout inspired by VMware ESXi DCUI and XCP-ng",
            "xsconsole (ncurses).",
            None,
            "Use it from the console to configure hostname,",
            "password, and network settings, install curated",
            "packages, and inspect system metrics.",
            None,
            "VMware/ESXi (Broadcom), XenServer/Citrix, and",
            "XCP-ng marks belong to their owners.",
            "zBoxTUI is not affiliated with any vendor.",
        ]

        with Container(id="dialog-outer"):
            with Vertical(id="dialog-header"):
                yield Static("")
                yield Static("About zBoxTUI", id="dialog-title")
                yield Static("")
                yield Static(
                    f"Version: {self._version}",
                    id="dialog-subtitle",
                )
                yield Static("")

            with Vertical(id="dialog-body"):
                yield Static(format_dialog_paragraphs(about_parts), id="dialog-about")
                yield Static("")
                yield Static(DIALOG_FOOTER_CLOSE, id="dialog-footer")

    def on_mount(self) -> None:
        """Take debug screenshot on mount."""
        self.app.save_debug_screenshot("about_dialog")

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
        Binding("q", "close", "Close", show=False),
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
        background: $z-panel;
        color: $z-panel-fg-dim;
        /* Left padding only so the scrollbar sits flush with the $z-panel edge */
        padding: 0 0 0 1;
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
                yield Static("")
                yield Static("System Logs", id="dialog-title")
                yield Static("")
                yield Static(
                    "Viewing recent system log entries",
                    id="dialog-subtitle",
                )
                yield Static("")
            with Vertical(id="dialog-body"):
                yield RichLog(id="log-container", wrap=False, highlight=False)
                yield Static("")
                yield Static(
                    "<↑/↓> Scroll  <PgUp/Dn> Page  <R> Refresh  · Press Enter to close",
                    id="dialog-footer",
                )

    def on_mount(self) -> None:
        """Load logs on mount and take debug screenshot."""
        self.app.save_debug_screenshot("system_logs_dialog")
        self._load_logs()

    def _load_logs(self) -> None:
        """Load system logs and display them."""
        from textual.widgets import RichLog

        self._log_lines = get_system_logs(lines=1000)

        log_container = self.query_one("#log-container", RichLog)
        log_container.clear()

        for line in self._log_lines:
            log_container.write(line)

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
        Binding("q", "close", "Close", show=False),
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
        background: $z-panel;
        color: $z-panel-fg-dim;
        /* Same scrollbar padding as SystemLogsDialog (#log-container) */
        padding: 0 0 0 1;
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
                yield Static("")
                yield Static("zBox Configuration", id="dialog-title")
                yield Static("")
                yield Static(
                    "Viewing /etc/zbox.config",
                    id="dialog-subtitle",
                )
                yield Static("")
            with Vertical(id="dialog-body"):
                yield RichLog(id="log-container", wrap=False, highlight=False)
                yield Static("")
                yield Static(
                    "<↑/↓> Scroll  <PgUp/Dn> Page  <R> Refresh  · Press Enter to close",
                    id="dialog-footer",
                )

    def on_mount(self) -> None:
        """Load config on mount and take debug screenshot."""
        self.app.save_debug_screenshot("zbox_logs_dialog")
        self._load_config()

    def _load_config(self) -> None:
        """Load zBox config and display it."""
        from textual.widgets import RichLog

        self._config_lines = get_zbox_config()

        log_container = self.query_one("#log-container", RichLog)
        log_container.clear()

        for line in self._config_lines:
            log_container.write(line)

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


class ZBoxTuiLogsDialog(ModalScreen[None]):
    """A dialog for viewing the zBoxTUI application log file."""

    app: ZBoxTUI

    BINDINGS = [
        Binding("escape", "close", "Close", show=False),
        Binding("enter", "close", "Close", show=False),
        Binding("q", "close", "Close", show=False),
        Binding("r", "refresh", "Refresh", show=False),
        Binding("up", "scroll_up", "Scroll Up", show=False),
        Binding("down", "scroll_down", "Scroll Down", show=False),
        Binding("pageup", "page_up", "Page Up", show=False),
        Binding("pagedown", "page_down", "Page Down", show=False),
        Binding("home", "scroll_home", "Scroll to Top", show=False),
        Binding("end", "scroll_end", "Scroll to Bottom", show=False),
    ]

    DEFAULT_CSS = DCUI_DIALOG_CSS.format(dialog_class="ZBoxTuiLogsDialog", width="90%") + """
    ZBoxTuiLogsDialog #dialog-outer {
        height: 90%;
    }

    ZBoxTuiLogsDialog #dialog-body {
        height: 1fr;
        overflow: hidden;
    }

    ZBoxTuiLogsDialog #log-container {
        height: 1fr;
        max-height: 100%;
        background: $z-panel;
        color: $z-panel-fg-dim;
        padding: 0 0 0 1;
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
        self._log_path: str = ""
        self._log_lines: list[str] = []

    def compose(self) -> ComposeResult:
        from textual.widgets import RichLog

        with Container(id="dialog-outer"):
            with Vertical(id="dialog-header"):
                yield Static("")
                yield Static("zBoxTUI Logs", id="dialog-title")
                yield Static("")
                yield Static(
                    "Viewing zBoxTUI application log",
                    id="dialog-subtitle",
                )
                yield Static("")
            with Vertical(id="dialog-body"):
                yield RichLog(id="log-container", wrap=False, highlight=False)
                yield Static("")
                yield Static(
                    "<↑/↓> Scroll  <PgUp/Dn> Page  <R> Refresh  · Press Enter to close",
                    id="dialog-footer",
                )

    def on_mount(self) -> None:
        """Load logs on mount and take debug screenshot."""
        self.app.save_debug_screenshot("zboxtui_logs_dialog")
        self._load_logs()

    def _load_logs(self) -> None:
        """Load zBoxTUI log file and display it."""
        from textual.widgets import RichLog

        log_path, self._log_lines = read_zboxtui_log_lines()
        self._log_path = str(log_path)

        log_container = self.query_one("#log-container", RichLog)
        log_container.clear()

        for line in self._log_lines:
            log_container.write(line)

        log_container.scroll_end(animate=False)

        subtitle = self.query_one("#dialog-subtitle", Static)
        subtitle.update(f"Viewing {self._log_path} ({len(self._log_lines)} lines)")

    def action_refresh(self) -> None:
        """Refresh the log file."""
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


class NetworkInterfaceDialog(ModalScreen[str | None]):
    """A dialog for selecting a network interface to configure."""

    app: ZBoxTUI

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("q", "cancel", "Cancel", show=False),
        Binding("up", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("enter", "select", "Select", show=False),
    ]

    DEFAULT_CSS = DCUI_DIALOG_CSS.format(dialog_class="NetworkInterfaceDialog", width=50) + """
    NetworkInterfaceDialog .interface-item {
        height: 1;
        width: 100%;
        padding: 0 1;
        background: $z-bg;
        color: $z-fg;
    }

    NetworkInterfaceDialog .interface-item.--selected {
        background: $z-accent;
        color: $z-accent-fg;
    }

    NetworkInterfaceDialog #no-interfaces {
        color: $z-error;
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
                yield Static("")
                yield Static("Select Network Interface", id="dialog-title")
                yield Static("")
                yield Static(
                    "Choose an interface to configure",
                    id="dialog-subtitle",
                )
                yield Static("")
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
                yield Static("")
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


class _NetworkFocusStatic(Static):
    """Focusable static row (e.g. the DHCP toggle) for keyboard navigation."""

    can_focus = True


_APPLY_NETWORK_DWELL_S = 0.4


class ApplyingNetworkDialog(ModalScreen[tuple[bool, str] | None]):
    """Spinner shown while interface config is written and ifup/ifdown run."""

    app: ZBoxTUI

    BINDINGS = [
        Binding("escape", "noop", show=False),
        Binding("q", "noop", show=False),
    ]

    DEFAULT_CSS = DCUI_DIALOG_CSS.format(dialog_class="ApplyingNetworkDialog", width=50) + """
    ApplyingNetworkDialog #apply-row {
        height: 1;
        margin: 1 0;
    }

    ApplyingNetworkDialog #apply-status {
        width: 1fr;
        content-align: center middle;
        color: $z-fg;
    }
    """

    def __init__(self, request: NetworkApplyRequest) -> None:
        super().__init__()
        self._request = request

    def compose(self) -> ComposeResult:
        with Container(id="dialog-outer"):
            with Vertical(id="dialog-header"):
                yield Static("")
                yield Static("Applying Network Configuration", id="dialog-title")
                yield Static("")
            with Vertical(id="dialog-body"):
                with Horizontal(id="apply-row"):
                    yield Static(
                        Spinner("dots", text=" Applying network configuration…"),
                        id="apply-status",
                    )
                yield Static("")

    def on_mount(self) -> None:
        self.query_one("#apply-status", Static).auto_refresh = _SPINNER_REFRESH
        self._apply_worker()

    def action_noop(self) -> None:
        """Ignore keys while apply is in progress."""

    @work(thread=True, exclusive=True)
    def _apply_worker(self) -> None:
        ok, message = apply_network_interface(self._request)
        self.app.call_from_thread(self._finish, ok, message)

    def _finish(self, ok: bool, message: str) -> None:
        status = self.query_one("#apply-status", Static)
        status.auto_refresh = None

        def _dismiss_with_result() -> None:
            self.dismiss((ok, message))

        if ok:
            status.update("✓")
            self.refresh()
            self.set_timer(
                _APPLY_NETWORK_DWELL_S,
                lambda: self.app.call_after_refresh(_dismiss_with_result),
            )
            return

        status.update(message)
        self.refresh()
        self.set_timer(1.5, lambda: self.app.call_after_refresh(_dismiss_with_result))




def _network_confirm_message(
    interface: str,
    *,
    dhcp: bool,
    ip: str = "",
    cidr: int | None = None,
    gateway: str = "",
    dns1: str = "",
    dns2: str = "",
) -> str:
    """Human-readable summary for the network apply confirmation dialog."""
    lines = [f"Apply the following configuration to {interface}?"]
    if dhcp:
        lines.extend(["", "- mode: DHCP"])
        return "\n".join(lines)
    dns_parts = [d for d in (dns1.strip(), dns2.strip()) if d]
    dns_line = ", ".join(dns_parts) if dns_parts else "(none)"
    lines.extend(
        [
            "",
            f"- address: {ip}/{cidr}",
            f"- gateway: {gateway}",
            f"- dns servers: {dns_line}",
        ]
    )
    return "\n".join(lines)


_DHCP_VALUE_COL_WIDTH = 34
_DHCP_VALUE_TAG = " [DHCP]"


def _format_dhcp_value_line(
    value: str,
    *,
    width: int = _DHCP_VALUE_COL_WIDTH,
    blank_placeholder: str = "-",
) -> Text:
    """Value plus right-aligned ``[DHCP]`` in one Static (exports reliably to SVG)."""
    display = value if value else blank_placeholder
    pad = max(1, width - len(display) - len(_DHCP_VALUE_TAG))
    line = Text()
    line.append(display)
    line.append(" " * pad)
    line.append("[DHCP]")
    return line


class NetworkConfigDialog(ModalScreen[bool]):
    """A dialog for configuring a network interface's IPv4 settings."""

    app: ZBoxTUI

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("q", "cancel", "Cancel", show=False),
        Binding("tab", "focus_next_field", "Next Field", show=False, priority=True),
        Binding("shift+tab", "focus_previous_field", "Previous Field", show=False, priority=True),
        Binding("down", "focus_next_field", "Next Field", show=False),
        Binding("up", "focus_previous_field", "Previous Field", show=False),
    ]

    _FIELD_INPUTS = (
        "ip-input",
        "netmask-input",
        "gateway-input",
        "dns1-input",
        "dns2-input",
    )

    DEFAULT_CSS = DCUI_DIALOG_CSS.format(dialog_class="NetworkConfigDialog", width=55) + """
    NetworkConfigDialog .form-row {
        height: 1;
        width: 100%;
    }

    NetworkConfigDialog .form-label {
        width: 15;
        color: $z-fg;
        height: 1;
        content-align: left middle;
    }

    NetworkConfigDialog .form-input {
        width: 1fr;
        background: $z-mantle;
        color: $z-panel-fg;
        border: none;
        height: 1;
    }

    NetworkConfigDialog .form-input:focus {
        background: $z-panel-focus;
    }

    NetworkConfigDialog .dhcp-value {
        width: 1fr;
        height: 1;
        color: $z-fg-faint;
        content-align: left middle;
    }

    NetworkConfigDialog #dhcp-row {
        height: 1;
        width: 100%;
    }

    NetworkConfigDialog #dhcp-label {
        color: $z-fg;
        width: auto;
        padding: 0 1;
    }

    NetworkConfigDialog #dhcp-label:focus {
        background: $z-panel-focus;
    }

    NetworkConfigDialog #error-message {
        color: $z-error;
        height: 1;
        text-align: center;
    }

    NetworkConfigDialog #section-label {
        color: $z-fg;
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
        with Container(id="dialog-outer"):
            with Vertical(id="dialog-header"):
                yield Static("")
                yield Static(
                    f"Configure Network: {self._interface_name}", id="dialog-title"
                )
                yield Static("")
                yield Static(
                    "Configure IPv4 settings for this interface",
                    id="dialog-subtitle",
                )
                yield Static("")
            with Vertical(id="dialog-body"):
                # DHCP toggle row
                with Horizontal(id="dhcp-row"):
                    dhcp_text = "[X] Use DHCP" if self._is_dhcp else "[ ] Use DHCP"
                    yield _NetworkFocusStatic(dhcp_text, id="dhcp-label", markup=False)

                yield Static("Static Configuration:", id="section-label")

                # IP Address - DHCP display (shown when DHCP enabled)
                with Horizontal(classes="form-row dhcp-display", id="ip-dhcp-row"):
                    yield Static("IP Address:", classes="form-label")
                    yield Static(
                        _format_dhcp_value_line(self._config.ipv4 or "-"),
                        classes="dhcp-value",
                    )



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
                with Horizontal(classes="form-row dhcp-display", id="netmask-dhcp-row"):
                    yield Static("Netmask:", classes="form-label")
                    yield Static(
                        _format_dhcp_value_line(self._config.netmask or "-"),
                        classes="dhcp-value",
                    )



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
                with Horizontal(classes="form-row dhcp-display", id="gateway-dhcp-row"):
                    yield Static("Gateway:", classes="form-label")
                    yield Static(
                        _format_dhcp_value_line(self._config.gateway or "-"),
                        classes="dhcp-value",
                    )



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
                with Horizontal(classes="form-row dhcp-display", id="dns1-dhcp-row"):
                    yield Static("DNS Server 1:", classes="form-label")
                    yield Static(
                        _format_dhcp_value_line(self._config.dns1 or "-"),
                        classes="dhcp-value",
                    )



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
                with Horizontal(classes="form-row dhcp-display", id="dns2-dhcp-row"):
                    yield Static("DNS Server 2:", classes="form-label")
                    yield Static(
                        _format_dhcp_value_line(self._config.dns2, blank_placeholder=""),
                        classes="dhcp-value",
                    )



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
                yield Static("")
                yield Static(
                    "<Tab/↑↓> Next field  <Space> Toggle DHCP  <Enter> Apply  <Esc> Cancel",
                    id="dialog-footer",
                )

    def on_mount(self) -> None:
        """Set initial visibility and take debug screenshot."""
        self._update_field_visibility()
        if self._is_dhcp:
            self._refresh_dhcp_display_fields()
        self.app.save_debug_screenshot("network_config_dialog")

    def _focus_order(self) -> list[str]:
        """Focusable fields in tab order (DHCP row, then static inputs)."""
        order = ["dhcp-label"]
        if not self._is_dhcp:
            order.extend(self._FIELD_INPUTS)
        return order

    def _focused_field_id(self) -> str | None:
        focused = self.focused
        if focused is None:
            return None
        return focused.id

    def _focus_field(self, field_id: str) -> None:
        self.query_one(f"#{field_id}").focus()

    def action_focus_next_field(self) -> None:
        order = self._focus_order()
        if not order:
            return
        current = self._focused_field_id()
        if current is None or current not in order:
            self._focus_field(order[0])
            return
        idx = order.index(current)
        self._focus_field(order[(idx + 1) % len(order)])

    def action_focus_previous_field(self) -> None:
        order = self._focus_order()
        if not order:
            return
        current = self._focused_field_id()
        if current is None or current not in order:
            self._focus_field(order[-1])
            return
        idx = order.index(current)
        self._focus_field(order[(idx - 1) % len(order)])

    @on(Input.Submitted)
    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Enter in an input advances to the next field or applies."""
        field_id = event.input.id
        if field_id not in self._FIELD_INPUTS:
            return
        order = self._focus_order()
        if field_id not in order:
            return
        idx = order.index(field_id)
        if idx + 1 < len(order):
            self._focus_field(order[idx + 1])
        else:
            self._submit()


    def _update_field_visibility(self) -> None:
        """Show/hide DHCP display vs Input rows based on current mode."""
        field_names = ["ip", "netmask", "gateway", "dns1", "dns2"]

        for field in field_names:
            dhcp_row = self.query_one(f"#{field}-dhcp-row", Horizontal)
            input_row = self.query_one(f"#{field}-input-row", Horizontal)

            # Show DHCP row when DHCP enabled, hide input row (and vice versa)
            dhcp_row.display = self._is_dhcp
            input_row.display = not self._is_dhcp

        section_label = self.query_one("#section-label", Static)
        section_label.update(
            "DHCP Configuration:" if self._is_dhcp else "Static Configuration:"
        )
        self.query_one("#dhcp-label", _NetworkFocusStatic).focus()

    def on_key(self, event: Key) -> None:
        """Handle keys on the DHCP row (inputs use :meth:`on_input_submitted`)."""
        field_id = self._focused_field_id()
        if event.key == "space" and field_id == "dhcp-label":
            self._toggle_dhcp()
            event.stop()
        elif event.key == "enter" and field_id == "dhcp-label":
            self._submit()
            event.stop()

    def _toggle_dhcp(self) -> None:
        """Toggle DHCP mode on/off."""
        self._is_dhcp = not self._is_dhcp

        # Switch between DHCP display rows and Input rows first (always succeeds).
        self._update_field_visibility()

        # Update DHCP label (markup stays off from compose-time markup=False).
        dhcp_label = self.query_one("#dhcp-label", _NetworkFocusStatic)
        dhcp_text = "[X] Use DHCP" if self._is_dhcp else "[ ] Use DHCP"
        dhcp_label.update(dhcp_text)

        if self._is_dhcp:
            self._refresh_dhcp_display_fields()

        log.debug("DHCP toggled to: %s", self._is_dhcp)

    def _refresh_dhcp_display_fields(self) -> None:
        """Reload live/DHCP values (DNS from dnsmasq resolv when DHCP)."""
        from ..utils.system import get_interface_config

        self._config = get_interface_config(self._interface_name)
        dhcp_values = (
            ("ip", self._config.ipv4 or "-", "-"),
            ("netmask", self._config.netmask or "-", "-"),
            ("gateway", self._config.gateway or "-", "-"),
            ("dns1", self._config.dns1 or "-", "-"),
            ("dns2", self._config.dns2, ""),
        )
        for field, value, blank in dhcp_values:
            row = self.query_one(f"#{field}-dhcp-row", Horizontal)
            row.query_one(".dhcp-value", Static).update(
                _format_dhcp_value_line(value, blank_placeholder=blank)
            )

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
            confirm_message = _network_confirm_message(
                self._interface_name,
                dhcp=False,
                ip=ip,
                cidr=cidr,
                gateway=gateway,
                dns1=dns1,
                dns2=dns2,
            )
        else:
            confirm_message = _network_confirm_message(
                self._interface_name,
                dhcp=True,
            )

        # Clear error and show confirmation dialog
        error_msg.update("")
        log.info(
            "Network config validated for %s: dhcp=%s",
            self._interface_name,
            self._is_dhcp,
        )

        # Show confirmation dialog
        self.app.push_screen(
            MessageDialog(
                "Confirm Network Configuration",
                confirm_message,
            ),
            callback=lambda confirmed: self._begin_apply() if confirmed else None,
        )

    def _build_apply_request(self) -> NetworkApplyRequest:
        if self._is_dhcp:
            return NetworkApplyRequest(interface=self._interface_name, dhcp=True)
        return NetworkApplyRequest(
            interface=self._interface_name,
            dhcp=False,
            ip=self.query_one("#ip-input", Input).value.strip(),
            netmask=self.query_one("#netmask-input", Input).value.strip(),
            gateway=self.query_one("#gateway-input", Input).value.strip(),
            dns1=self.query_one("#dns1-input", Input).value.strip(),
            dns2=self.query_one("#dns2-input", Input).value.strip(),
        )

    def _begin_apply(self) -> None:
        """Show the applying spinner and run ifup/ifdown off the UI thread."""
        request = self._build_apply_request()
        log.info(
            "Applying network config: iface=%s dhcp=%s",
            request.interface,
            request.dhcp,
        )
        self.query_one("#error-message", Static).update("")
        self.app.push_screen(
            ApplyingNetworkDialog(request),
            callback=self._after_apply,
        )

    def _after_apply(self, result: tuple[bool, str] | None) -> None:
        """Handle spinner result: success notice or inline error on this dialog."""
        if result is None:
            return
        ok, message = result
        if ok:
            self.app.push_screen(
                MessageDialog("Configuration Applied", message, ack_only=True),
                callback=dismiss_screen_after_modal(
                    self,
                    True,
                    before_dismiss=self.app.reload_dashboard,
                ),
            )
            return
        error_text = message if message.startswith("Error:") else f"Error: {message}"
        self.query_one("#error-message", Static).update(error_text)

    def action_cancel(self) -> None:
        """Cancel the dialog."""
        self.dismiss(False)


class MeterBar(Widget):
    """A thin horizontal gauge that fills in proportion to `percent` (0-100)."""

    COMPONENT_CLASSES = {"meter--filled", "meter--empty"}

    DEFAULT_CSS = """
    MeterBar {
        width: 1fr;
        height: 1;
    }
    MeterBar > .meter--filled {
        color: $z-accent;
    }
    MeterBar > .meter--empty {
        color: $z-panel;
    }
    """

    percent: reactive[float] = reactive(0.0)

    def render(self) -> Text:
        width = self.size.width or 1
        ratio = max(0.0, min(1.0, self.percent / 100.0))
        filled = round(ratio * width)
        text = Text(no_wrap=True, overflow="crop")
        text.append("━" * filled, self.get_component_rich_style("meter--filled"))
        text.append("━" * (width - filled), self.get_component_rich_style("meter--empty"))
        return text


class SystemStatsDialog(ModalScreen[None]):
    """A live System Metrics panel: CPU, memory, storage and network I/O."""

    app: ZBoxTUI

    # Samples retained for the network I/O sparklines. Sampled at 1 Hz, so
    # this is also the window in seconds. Chosen to roughly match the
    # rendered sparkline column count so each column shows one sample (no
    # max-summary bucketing — every column = 1 second of traffic).
    _HISTORY = 30

    BINDINGS = [
        Binding("escape", "close", "Close", show=False),
        Binding("enter", "close", "Close", show=False),
        Binding("q", "close", "Close", show=False),
    ]

    DEFAULT_CSS = DCUI_DIALOG_CSS.format(dialog_class="SystemStatsDialog", width=72) + """
    SystemStatsDialog .stats-section {
        color: $z-fg;
        text-style: bold;
        height: 1;
        margin-top: 1;
    }

    SystemStatsDialog .stats-row {
        height: 1;
    }

    SystemStatsDialog .stats-label {
        width: 26;
        color: $z-fg;
    }

    SystemStatsDialog .stats-value {
        width: 9;
        text-align: right;
        color: $z-fg;
    }

    SystemStatsDialog MeterBar {
        width: 1fr;
        height: 1;
        margin: 0 2;
    }

    /* Network rows are taller: the sparkline gets 3 rows of vertical
     * resolution (~24 levels using fractional block chars vs. 8 at h=1),
     * and the label/value sit centered alongside it. */
    SystemStatsDialog .net-row {
        height: 3;
    }

    SystemStatsDialog .net-row .stats-label {
        height: 3;
        content-align: left middle;
    }

    SystemStatsDialog .net-row .stats-value {
        height: 3;
        content-align: right middle;
    }

    SystemStatsDialog BarChart {
        width: 1fr;
        height: 3;
        margin: 0 2;
        color: $z-accent;
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
        self._cpu_model = get_cpu_info()
        self._cpu_count = get_cpu_count()
        # Baseline samples for the first delta-based reading.
        self._prev_cpu = read_cpu_times()
        self._prev_net = read_net_bytes()
        self._prev_time = time.monotonic()
        # Prefill with zeros so the sparkline shows full width from t=0
        # instead of growing in from the left over the first 30 seconds.
        self._rx_history: deque[float] = deque(
            [0.0] * self._HISTORY, maxlen=self._HISTORY
        )
        self._tx_history: deque[float] = deque(
            [0.0] * self._HISTORY, maxlen=self._HISTORY
        )

    def compose(self) -> ComposeResult:
        with Container(id="dialog-outer"):
            with Vertical(id="dialog-header"):
                yield Static("")
                yield Static("System Metrics", id="dialog-title")
                yield Static("")
                yield Static(
                    f"{self._cpu_model} ({self._cpu_count} cores)",
                    id="dialog-subtitle",
                )
                yield Static("")
            with Vertical(id="dialog-body"):
                yield Static("CPU", classes="stats-section")
                with Horizontal(classes="stats-row"):
                    yield Static("Current Load", classes="stats-label")
                    yield MeterBar(id="cpu-meter")
                    yield Static("--", classes="stats-value", id="cpu-value")

                yield Static("Memory", classes="stats-section")
                with Horizontal(classes="stats-row"):
                    yield Static("--", classes="stats-label", id="mem-label")
                    yield MeterBar(id="mem-meter")
                    yield Static("--", classes="stats-value", id="mem-value")

                yield Static("Storage", classes="stats-section")
                with Horizontal(classes="stats-row"):
                    yield Static("--", classes="stats-label", id="disk-label")
                    yield MeterBar(id="disk-meter")
                    yield Static("--", classes="stats-value", id="disk-value")

                yield Static("Network I/O", classes="stats-section")
                with Horizontal(classes="net-row"):
                    yield Static("RX", classes="stats-label")
                    yield BarChart(list(self._rx_history), id="rx-spark")
                    yield Static("--", classes="stats-value", id="rx-value")
                yield Static(" ")
                with Horizontal(classes="net-row"):
                    yield Static("TX", classes="stats-label")
                    yield BarChart(list(self._tx_history), id="tx-spark")
                    yield Static("--", classes="stats-value", id="tx-value")

                yield Static("")
                yield Static(DIALOG_FOOTER_CLOSE, id="dialog-footer")

    def on_mount(self) -> None:
        """Populate stats on mount and refresh every second."""
        self.app.save_debug_screenshot("system_stats_dialog")
        self._refresh_stats()
        self.set_interval(1.0, self._refresh_stats)

    def _refresh_stats(self) -> None:
        """Sample the system and update every metric widget."""
        now = time.monotonic()
        elapsed = max(now - self._prev_time, 1e-6)

        # CPU load (delta between two /proc/stat samples).
        cur_cpu = read_cpu_times()
        cpu_pct = cpu_percent(self._prev_cpu, cur_cpu)
        self._prev_cpu = cur_cpu
        self.query_one("#cpu-meter", MeterBar).percent = cpu_pct
        self.query_one("#cpu-value", Static).update(f"{cpu_pct:.1f}%")

        # Memory (same source as dashboard: provisioned GiB total, meminfo %).
        mem = get_memory_stats()
        self.query_one("#mem-meter", MeterBar).percent = mem.percent
        self.query_one("#mem-label", Static).update(
            f"{mem.used_label} Used / {mem.total_label}"
        )
        self.query_one("#mem-value", Static).update(f"{mem.percent:.1f}%")

        # Storage.
        disk_used, disk_total = get_disk_usage()
        disk_pct = 100.0 * disk_used / disk_total if disk_total else 0.0
        self.query_one("#disk-meter", MeterBar).percent = disk_pct
        self.query_one("#disk-label", Static).update(
            f"{disk_used / _GIB:.1f} GB Used / {disk_total / _GIB:.0f} GB"
        )
        self.query_one("#disk-value", Static).update(f"{disk_pct:.1f}%")

        # Network I/O rates (delta between two /proc/net/dev samples).
        cur_net = read_net_bytes()
        rx_rate = max(0.0, (cur_net[0] - self._prev_net[0]) / elapsed)
        tx_rate = max(0.0, (cur_net[1] - self._prev_net[1]) / elapsed)
        self._prev_net = cur_net
        self._prev_time = now
        self._rx_history.append(rx_rate)
        self._tx_history.append(tx_rate)
        self.query_one("#rx-spark", BarChart).data = list(self._rx_history)
        self.query_one("#tx-spark", BarChart).data = list(self._tx_history)
        self.query_one("#rx-value", Static).update(f"{format_size(rx_rate)}/s")
        self.query_one("#tx-value", Static).update(f"{format_size(tx_rate)}/s")

    def action_close(self) -> None:
        """Close the dialog."""
        self.dismiss(None)

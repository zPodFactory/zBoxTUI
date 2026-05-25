"""Dashboard screen - main DCUI home screen."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Static

from ..utils.system import get_system_info

if TYPE_CHECKING:
    from ...app import ZBoxTUI


class DashboardScreen(Screen):
    """The main dashboard screen with system info and management URLs."""

    app: ZBoxTUI

    BINDINGS = [
        ("f2", "customize", "Customize System"),
        ("f12", "shutdown", "Shutdown"),
        ("q", "app.quit", "Quit"),
    ]

    DEFAULT_CSS = """
    DashboardScreen {
        background: $z-bg;
        layout: grid;
        grid-size: 1 2;
        grid-rows: 1fr 1fr;
    }

    DashboardScreen #dashboard-header {
        background: $z-panel;
        color: $z-panel-fg;
        row-span: 1;
        padding: 1 2;
        border-top: solid $z-border;
        border-left: solid $z-border;
        border-right: solid $z-border;
    }

    DashboardScreen #dashboard-content {
        background: $z-bg;
        color: $z-fg;
        row-span: 1;
        border-left: solid $z-border;
        border-right: solid $z-border;
        border-bottom: solid $z-border;
    }

    DashboardScreen #content-inner {
        padding: 1 2;
        height: 1fr;
    }

    DashboardScreen #dashboard-footer {
        layout: horizontal;
        height: 1;
        width: 100%;
        background: $z-bg;
        color: $z-fg;
        padding: 0 1;
    }

    DashboardScreen #footer-left {
        width: 1fr;
        background: $z-bg;
        color: $z-fg;
    }

    DashboardScreen #footer-right {
        width: 1fr;
        text-align: right;
        background: $z-bg;
        color: $z-fg;
    }
    """

    def compose(self) -> ComposeResult:
        info = get_system_info()

        # Header section with system info (gray with white border top/left/right)
        with Vertical(id="dashboard-header"):
            yield Static(self._zbox_header(info))
            yield Static("")
            yield Static(info.hostname)
            yield Static("")
            yield Static(info.cpu_info)
            yield Static(info.memory_total)

        # Main content area (yellow with white border left/right/bottom)
        with Vertical(id="dashboard-content"):
            with Vertical(id="content-inner"):
                yield Static("Network Interfaces:")
                yield Static("")
                # Calculate max interface name length for alignment
                max_name_len = max(len(iface.name) for iface in info.interfaces)
                for iface in info.interfaces:
                    # Format: "  name:    IP (GW IP GW)" with right-aligned IP
                    name_padded = f"{iface.name}:".ljust(max_name_len + 2)
                    if iface.gateway:
                        ip_display = f"{iface.ipv4} ({iface.gateway} GW)"
                    else:
                        ip_display = iface.ipv4
                    yield Static(f"  {name_padded} {ip_display}")

            # Footer keybinds at bottom of yellow section
            with Horizontal(id="dashboard-footer"):
                yield Static("<F2> Customize System/View Logs", id="footer-left")
                yield Static("<F12> Shut Down/Restart", id="footer-right")

    @staticmethod
    def _zbox_header(info) -> str:
        """Build the top header line of the dashboard.

        Target shape: ``zBox ({debian_version}) - {pretty_name}``
        e.g. ``zBox (13.5) - Debian GNU/Linux 13 (trixie)``

        Fallbacks if either piece is missing (non-Debian / no
        ``/etc/os-release``): the corresponding segment is dropped
        gracefully — never emit naked parens or a trailing dash.
        """
        # Re-use the (label, ver) pair so we still display something
        # readable on a box without /etc/os-release.
        os_label = (
            f"{info.os_name} {info.os_version}".strip()
            if info.os_version
            else info.os_name
        )
        parts = ["zBox"]
        if info.debian_version:
            parts.append(f"({info.debian_version})")
        line = " ".join(parts)
        if os_label:
            line = f"{line} - {os_label}"
        return line

    def on_mount(self) -> None:
        """Take debug screenshot on mount if enabled."""
        self.app.save_debug_screenshot("dashboard")

    def action_customize(self) -> None:
        """Handle F2 - open customize/login screen."""
        self.app.action_show_login()

    def action_shutdown(self) -> None:
        """Handle F12 - show shutdown dialog."""
        self.app.action_show_shutdown()

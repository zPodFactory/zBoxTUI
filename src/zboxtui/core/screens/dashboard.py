"""Dashboard screen - main DCUI home screen."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import ProgressBar, Static

from ..utils.system import get_load_percent, get_memory_usage, get_system_info

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
        layout: horizontal;
        padding: 1 2;
        height: 1fr;
    }

    DashboardScreen #content-network,
    DashboardScreen #content-storage {
        width: 1fr;
        height: auto;
    }

    /* Generic "label + bar + percent" row used in both the header
     * (CPU / memory) and the bottom storage panel. Defined once,
     * customised per location via the .stat-bar-* descendants. */
    DashboardScreen .stat-row {
        height: 1;
        width: 100%;
    }

    DashboardScreen .stat-label {
        width: auto;
        height: 1;
    }

    DashboardScreen .stat-bar {
        width: 1fr;
        height: 1;
        margin: 0 0 0 1;
    }

    /* Textual's Bar defaults to width: 32 — force it to fill 1fr so
     * the bar reaches the row's right edge with no trailing dead
     * space before the percentage. */
    DashboardScreen .stat-bar Bar {
        width: 1fr;
    }

    DashboardScreen .stat-percent {
        width: 5;
        height: 1;
        text-align: right;
        padding-right: 1;
    }

    /* Header bars sit on $z-panel, so the bar track uses a colour
     * a bit darker than the panel for contrast. */
    DashboardScreen .header-stat-bar Bar > .bar--bar,
    DashboardScreen .header-stat-bar Bar > .bar--complete {
        color: $z-accent;
        background: $z-mantle;
    }

    /* Fixed-width labels so the CPU Load and Memory bars start at
     * the same column regardless of label content. */
    DashboardScreen .header-stat-row .stat-label {
        width: 8;
        padding-right: 1;
    }

    /* Storage bars sit on $z-bg (yellow body in vmware-esxi). */
    DashboardScreen .storage-bar Bar > .bar--bar {
        color: $z-accent;
        background: $z-mantle;
    }

    DashboardScreen .storage-bar Bar > .bar--complete {
        color: $z-error;
        background: $z-mantle;
    }

    DashboardScreen .storage-row .stat-label {
        padding-left: 2;
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
            # Keep the previous one-liners with the static facts
            # (model + cores, total memory) and add a live bar below
            # each.
            yield Static(f"{info.cpu_info} ({info.cpu_count} cores)")
            yield from self._stat_row(
                "Load",
                info.cpu_load_percent,
                kind="header",
                bar_id="cpu-load-bar",
                percent_id="cpu-load-pct",
            )
            yield Static(info.memory_total)
            yield from self._stat_row(
                "Memory",
                info.memory_percent,
                kind="header",
                bar_id="memory-bar",
                percent_id="memory-pct",
            )

        # Main content area (yellow with white border left/right/bottom)
        with Vertical(id="dashboard-content"):
            with Horizontal(id="content-inner"):
                with Vertical(id="content-network"):
                    yield Static("Network Interfaces:")
                    yield Static("")
                    max_name_len = (
                        max(len(iface.name) for iface in info.interfaces)
                        if info.interfaces
                        else 0
                    )
                    for iface in info.interfaces:
                        name_padded = f"{iface.name}:".ljust(max_name_len + 2)
                        if iface.gateway:
                            ip_display = f"{iface.ipv4} ({iface.gateway} GW)"
                        else:
                            ip_display = iface.ipv4
                        yield Static(f"  {name_padded} {ip_display}")

                with Vertical(id="content-storage"):
                    yield Static("Storage:")
                    yield Static("")
                    if not info.filesystems:
                        yield Static("  (no disk-backed mounts found)")
                    else:
                        max_mp_len = max(
                            len(fs.mount_point) for fs in info.filesystems
                        )
                        for fs in info.filesystems:
                            yield from self._stat_row(
                                fs.mount_point.ljust(max_mp_len),
                                fs.percent,
                                kind="storage",
                            )

            # Footer keybinds at bottom of yellow section
            with Horizontal(id="dashboard-footer"):
                yield Static("<F2> Customize System/View Logs", id="footer-left")
                yield Static("<F12> Shut Down/Restart", id="footer-right")

    @staticmethod
    def _stat_row(
        label: str,
        percent: float,
        *,
        kind: str,
        bar_id: str | None = None,
        percent_id: str | None = None,
    ):
        """Yield widgets for one ``label / bar / percent`` row.

        ``kind`` is either ``"header"`` (CPU/memory in the top panel —
        bar styled for the grey panel background) or ``"storage"``
        (filesystem rows in the bottom panel — yellow-body styled).
        Optional ``bar_id`` / ``percent_id`` let callers later
        ``query_one`` the bar + percentage to refresh them.
        """
        row_classes = f"stat-row {kind}-row {kind}-bar-row"
        bar_classes = f"stat-bar {kind}-bar"
        clamped = max(0.0, min(100.0, percent))
        with Horizontal(classes=row_classes):
            yield Static(label, classes="stat-label")
            bar = ProgressBar(
                total=100,
                show_eta=False,
                show_percentage=False,
                classes=bar_classes,
                id=bar_id,
            )
            bar.update(progress=clamped)
            yield bar
            yield Static(
                f"{percent:.0f}%",
                classes="stat-percent",
                id=percent_id,
            )

    @staticmethod
    def _zbox_header(info) -> str:
        """Build the top header line of the dashboard.

        Target shape: ``zBox {debian_version} - {pretty_name}``
        e.g. ``zBox 13.5 - Debian GNU/Linux 13 (trixie)``

        Fallbacks if either piece is missing (non-Debian / no
        ``/etc/os-release``): the corresponding segment is dropped
        gracefully — never emit a trailing dash or stray spacing.
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
            parts.append(info.debian_version)
        line = " ".join(parts)
        if os_label:
            line = f"{line} - {os_label}"
        return line

    def on_mount(self) -> None:
        """Take debug screenshot on mount + start the live-stat refresh tick."""
        self.app.save_debug_screenshot("dashboard")
        # 2 seconds is responsive enough for memory while staying calm
        # for the 1-min load average (which by definition only moves
        # over the minute anyway). Cheap: two /proc reads per tick.
        self.set_interval(2.0, self._refresh_stats)

    def _refresh_stats(self) -> None:
        """Re-sample CPU load + memory and update the header bars."""
        load = get_load_percent()
        mem_used, mem_total = get_memory_usage()
        mem_pct = 100.0 * mem_used / mem_total if mem_total else 0.0

        cpu_bar = self.query_one("#cpu-load-bar", ProgressBar)
        cpu_bar.update(progress=max(0.0, min(100.0, load)))
        self.query_one("#cpu-load-pct", Static).update(f"{load:.0f}%")

        mem_bar = self.query_one("#memory-bar", ProgressBar)
        mem_bar.update(progress=max(0.0, min(100.0, mem_pct)))
        self.query_one("#memory-pct", Static).update(f"{mem_pct:.0f}%")

    def action_customize(self) -> None:
        """Handle F2 - open customize/login screen."""
        self.app.action_show_login()

    def action_shutdown(self) -> None:
        """Handle F12 - show shutdown dialog."""
        self.app.action_show_shutdown()

#!/usr/bin/env python3
"""Regenerate SVG screenshots for the README (Catppuccin Mocha only).

Run from the repo root::

    uv run python scripts/capture_readme_screenshots.py

Output: ``docs/screenshots/*_catppuccin.svg``

Run this after any visual UI change (dialogs, dashboard, menu, etc.) so README
screenshots stay current.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "screenshots"
THEME = "catppuccin-mocha"
SUFFIX = "catppuccin"
SIZE = (120, 35)

# Deterministic eth0 examples for README validation (dashboard + network dialog).
ETH0_STATIC = {
    "ipv4": "192.168.1.10",
    "gateway": "192.168.1.1",
    "netmask": "255.255.255.0",
    "cidr": 24,
    "is_dhcp": False,
    "dns1": "192.168.1.1",
    "dns2": "8.8.4.4",
}
ETH0_DHCP = {
    "ipv4": "192.168.50.42",
    "gateway": "192.168.50.1",
    "netmask": "255.255.255.0",
    "cidr": 24,
    "is_dhcp": True,
    "dns1": "192.168.50.1",
    "dns2": "",
}


def _prepare_terminal_env() -> None:
    """Ensure Textual exports Catppuccin truecolor, not NO_COLOR monochrome.

    Cursor/CI often sets ``NO_COLOR=1``, which enables Textual's ``nocolor`` mode
    and grey SVG output even when ``app.theme`` is ``catppuccin-mocha``.
    Must run before ``ZBoxTUI()`` is constructed (``App`` reads env on init).
    """
    os.environ.pop("NO_COLOR", None)
    os.environ["COLORTERM"] = "truecolor"
    os.environ["TERM"] = "xterm-256color"
    os.environ["TEXTUAL_COLOR_SYSTEM"] = "truecolor"


def _eth0_interface(**fields) -> object:
    from zboxtui.core.utils.system import NetworkInterface

    return NetworkInterface(
        name="eth0",
        ipv4=fields["ipv4"],
        gateway=fields["gateway"],
        netmask=fields["netmask"],
        cidr=fields["cidr"],
        is_dhcp=fields["is_dhcp"],
    )


def _eth1_interface() -> object:
    from zboxtui.core.utils.system import NetworkInterface

    return NetworkInterface(
        name="eth1",
        ipv4="10.0.0.5",
        gateway=None,
        netmask="255.255.255.0",
        cidr=24,
        is_dhcp=False,
    )




def _prod_eth0_interface() -> object:
    """Primary LAN (matches typical zBox lab / dev host)."""
    from zboxtui.core.utils.system import NetworkInterface

    return NetworkInterface(
        name="eth0",
        ipv4="172.16.42.12",
        gateway="172.16.42.1",
        netmask="255.255.255.0",
        cidr=24,
        is_dhcp=False,
    )


def _prod_eth1_interface() -> object:
    from zboxtui.core.utils.system import NetworkInterface

    return NetworkInterface(
        name="eth1",
        ipv4="10.10.10.137",
        gateway=None,
        netmask="255.255.255.0",
        cidr=24,
        is_dhcp=True,
    )


def _tailscale0_interface() -> object:
    from zboxtui.core.utils.system import NetworkInterface

    return NetworkInterface(
        name="tailscale0",
        ipv4="100.103.60.28",
        gateway=None,
        netmask=None,
        cidr=32,
        is_dhcp=True,
    )


def _wt0_interface() -> object:
    """NetBird / WireGuard tunnel (wt*)."""
    from zboxtui.core.utils.system import NetworkInterface

    return NetworkInterface(
        name="wt0",
        ipv4="100.126.24.134",
        gateway=None,
        netmask=None,
        cidr=16,
        is_dhcp=True,
    )


DASHBOARD_VPN_INTERFACE_MODES = {
    "eth0": "[STATIC]",
    "eth1": "[DHCP]",
    "tailscale0": "[UNMANAGED]",
    "wt0": "[UNMANAGED]",
}


def _dashboard_vpn_interfaces() -> list:
    return [
        _prod_eth0_interface(),
        _prod_eth1_interface(),
        _tailscale0_interface(),
        _wt0_interface(),
    ]

def _demo_extra_routes() -> list:
    from zboxtui.core.utils.system import RouteEntry

    return [RouteEntry(destination="10.20.0.0/24", via="10.0.0.1", iface="eth1")]


def _interface_config(name: str, fields: dict) -> object:
    from zboxtui.core.utils.system import InterfaceConfig

    return InterfaceConfig(
        name=name,
        is_dhcp=fields["is_dhcp"],
        ipv4=fields["ipv4"],
        netmask=fields["netmask"],
        cidr=fields["cidr"],
        gateway=fields["gateway"],
        dns1=fields["dns1"],
        dns2=fields["dns2"],
    )


def _install_stubs(
    sample_log: Path,
    *,
    dashboard_interfaces: list | None = None,
    interface_config_for: Callable[[str], object] | None = None,
    default_gateway: tuple[str | None, str | None] | None = None,
    dns_servers: list[str] | None = None,
    interface_modes: dict[str, str | None] | None = None,
    extra_routes: list | None = None,
) -> None:
    """Stub PAM, ping, network, and logs so captures are deterministic."""
    import zboxtui.core.utils.system as system
    import zboxtui.core.widgets.dcui_dialog as dcui

    dcui.verify_root_password = lambda _pw: True

    async def _fake_ping(host: str, count: int = 3) -> tuple[bool, str]:
        return True, "OK (0.42 ms avg)"

    dcui.ping_host = _fake_ping

    dcui.build_network_test_targets = lambda: [
        dcui._ConnectivityTestTarget("Default Gateway (10.0.0.1):", "10.0.0.1"),
        dcui._ConnectivityTestTarget("DNS Server 1 (10.0.0.1):", "10.0.0.1"),
        dcui._ConnectivityTestTarget("Cloudflare DNS (1.1.1.1):", "1.1.1.1"),
        dcui._ConnectivityTestTarget("Google DNS (8.8.8.8):", "8.8.8.8"),
    ]

    if dashboard_interfaces is None:
        dashboard_interfaces = [_eth0_interface(**ETH0_STATIC), _eth1_interface()]
    system.get_network_interfaces = lambda: dashboard_interfaces
    from zboxtui.core.utils.system import FilesystemInfo

    system.get_filesystems = lambda: [
        FilesystemInfo(
            device="/dev/mapper/vg-root",
            mount_point="/",
            fstype="ext4",
            used_bytes=48_000_000_000,
            total_bytes=100_000_000_000,
        ),
        FilesystemInfo(
            device="/dev/sda1",
            mount_point="/boot",
            fstype="ext4",
            used_bytes=200_000_000,
            total_bytes=1_000_000_000,
        ),
    ]

    modes = interface_modes
    if modes is None:
        modes = {"eth0": "[STATIC]", "eth1": "[STATIC]"}
    system.get_interface_config_mode = lambda name, **kwargs: modes.get(name)

    if extra_routes is None:
        system.get_additional_ipv4_routes = _demo_extra_routes
    else:
        system.get_additional_ipv4_routes = lambda: list(extra_routes)

    config_fn = interface_config_for or (
        lambda name: _interface_config(name, ETH0_STATIC)
    )
    system.get_interface_config = config_fn

    gw_ip = default_gateway[0] if default_gateway else ETH0_STATIC["gateway"]
    gw_iface = default_gateway[1] if default_gateway else "eth0"
    system.get_default_gateway = lambda: (gw_ip, gw_iface)

    dns_list = dns_servers
    if dns_list is None:
        dns_list = [s for s in (ETH0_STATIC["dns1"], ETH0_STATIC["dns2"]) if s]
    system.resolve_interface_dns_servers = lambda _iface: dns_list

    import zboxtui.core.utils.logging as logging_mod

    def _fake_read(*, max_lines: int = 2000) -> tuple[Path, list[str]]:
        lines = sample_log.read_text(encoding="utf-8").splitlines()
        return sample_log, lines[-max_lines:]

    logging_mod.read_zboxtui_log_lines = _fake_read


def _write_sample_config(config_path: Path, log_path: Path) -> None:
    config_path.write_text(
        f"""[general]
log_file = {log_path}
log_level = INFO

[dashboard]
display_live_information = false
refresh_interval_seconds = 2.0

[network]
test_default_target = 1.1.1.1
dns_test_default_target = example.com

[theme]
name = {THEME}
""",
        encoding="utf-8",
    )


def _write_sample_log(log_path: Path) -> None:
    log_path.write_text(
        "\n".join(
            [
                "2026-05-23 10:00:01 INFO  zboxtui — started on tty1",
                "2026-05-23 10:00:02 INFO  menu.configure_hostname — Opening Configure Hostname dialog",
                "2026-05-23 10:00:15 INFO  menu.network_test_connectivity — Opening Test Network dialog",
                "2026-05-23 10:00:22 INFO  menu.configure_packages — Opening Configure Packages submenu",
                "2026-05-23 10:00:45 INFO  dashboard — live refresh interval 2.0s",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


async def _paint_network_test_snapshot(app) -> None:
    """GW + DNS OK; Cloudflare mid-probe with spinner and two green dots."""
    from rich.spinner import Spinner
    from textual.widgets import Static

    from zboxtui.core.widgets.dcui_dialog import NetworkTestDialog

    def _capture_mount(self: NetworkTestDialog) -> None:
        self.app.save_debug_screenshot("network_test_dialog")

    NetworkTestDialog.on_mount = _capture_mount  # type: ignore[method-assign]
    app.push_screen(NetworkTestDialog())
    await asyncio.sleep(0.35)
    dialog = app.screen
    if not isinstance(dialog, NetworkTestDialog):
        raise RuntimeError(f"expected NetworkTestDialog, got {type(dialog)!r}")
    dialog._finish_test(dialog.query_one("#test-status-0", Static), True, "OK (0.42 ms avg)")
    dialog._finish_test(dialog.query_one("#test-status-1", Static), True, "OK (1.15 ms avg)")
    status = dialog.query_one("#test-status-2", Static)
    status.remove_class("--success", "--failure")
    status.add_class("--pending")
    status.update(Spinner("dots", text=dialog._theme_dots([True, True, None])))




async def _ensure_dashboard_visible(app, pilot) -> None:
    """Pop modal/menu screens so the next screenshot is the dashboard."""
    from zboxtui.core.screens.dashboard import DashboardScreen

    while not isinstance(app.screen, DashboardScreen):
        if len(app.screen_stack) > 1:
            app.pop_screen()
        else:
            app.switch_screen("dashboard")
        await pilot.pause(0.05)


async def _shot_dashboard_eth0(
    app,
    pilot,
    shot: Callable,
    stem: str,
    fields: dict,
    *,
    write_settings,
) -> None:
    """Dashboard with a single visible eth0 line (static or simulated DHCP)."""
    await _ensure_dashboard_visible(app, pilot)
    write_settings({"dashboard_display_live_information": False})
    dns = [s for s in (fields.get("dns1", ""), fields.get("dns2", "")) if s]
    mode = "[DHCP]" if fields.get("is_dhcp") else "[STATIC]"
    _install_stubs(
        OUT / "_capture_zboxtui.log",
        dashboard_interfaces=[_eth0_interface(**fields)],
        interface_config_for=lambda name: _interface_config(name, fields),
        default_gateway=(fields.get("gateway"), "eth0"),
        dns_servers=dns,
        interface_modes={"eth0": mode},
        extra_routes=[],
    )
    from zboxtui.core.screens.dashboard import DashboardScreen

    screen = app.screen
    if isinstance(screen, DashboardScreen):
        await screen._reload_async()
    else:
        app.reload_dashboard()
        await pilot.pause(1.0)
    await pilot.pause(0.2)
    shot(app, stem)




async def _shot_dashboard_vpn_interfaces(
    app,
    pilot,
    shot: Callable,
    *,
    write_settings,
) -> None:
    """Dashboard with physical NICs plus Tailscale (tailscale0) and NetBird (wt0)."""
    await _ensure_dashboard_visible(app, pilot)
    write_settings({"dashboard_display_live_information": False})
    _install_stubs(
        OUT / "_capture_zboxtui.log",
        dashboard_interfaces=_dashboard_vpn_interfaces(),
        default_gateway=("172.16.42.1", "eth0"),
        dns_servers=["172.16.42.11"],
        interface_modes=DASHBOARD_VPN_INTERFACE_MODES,
        extra_routes=[],
    )
    from zboxtui.core.screens.dashboard import DashboardScreen

    screen = app.screen
    if isinstance(screen, DashboardScreen):
        await screen._reload_async()
    else:
        app.reload_dashboard()
        await pilot.pause(1.0)
    await pilot.pause(0.2)
    shot(app, "17_dashboard_vpn_interfaces")


async def _shot_network_config(
    app,
    pilot,
    shot: Callable,
    stem: str,
    fields: dict,
) -> None:
    """Network config dialog for eth0 (static inputs or DHCP read-only rows)."""
    from zboxtui.core.widgets.dcui_dialog import NetworkConfigDialog

    _install_stubs(
        OUT / "_capture_zboxtui.log",
        interface_config_for=lambda name: _interface_config(name, fields),
    )
    app.push_screen(NetworkConfigDialog("eth0"))
    await pilot.pause(0.35)
    shot(app, stem)
    app.pop_screen()
    await pilot.pause(0.1)


async def capture() -> None:
    _prepare_terminal_env()

    from zboxtui.app import ZBoxTUI
    from zboxtui.core.menu_items.configure_hostname import HostnameDialog
    from zboxtui.core.menu_items.configure_packages import PackagesDialog
    from zboxtui.core.menu_items.configure_settings import SettingsDialog
    from zboxtui.core.menu_items.configure_theme import ThemeDialog
    from zboxtui.core.menu_items.view_system_metrics import show_view_system_metrics_dialog
    from zboxtui.core.menu_items.view_zboxtui_logs import show_view_zboxtui_logs_dialog
    from zboxtui.core.utils.config import init_config, write_settings
    from zboxtui.core.widgets.dcui_dialog import NetworkInterfaceDialog

    OUT.mkdir(parents=True, exist_ok=True)
    config_path = OUT / "_capture_app.conf"
    log_path = OUT / "_capture_zboxtui.log"
    _write_sample_log(log_path)
    _write_sample_config(config_path, log_path)
    os.environ["ZBOXTUI_CONFIG"] = str(config_path)
    os.environ["ZBOXTUI_DEMO_UPGRADES"] = "1"

    init_config(None)
    _install_stubs(log_path)

    def shot(app: ZBoxTUI, stem: str) -> None:
        app.save_screenshot(str(OUT / f"{stem}_{SUFFIX}.svg"))

    app = ZBoxTUI(theme_override=THEME)
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause(0.2)
        shot(app, "01_dashboard")

        # Live dashboard: single eth0 only (dual-iface routing is shown in 01).
        _install_stubs(
            log_path,
            dashboard_interfaces=[_eth0_interface(**ETH0_STATIC)],
            default_gateway=(ETH0_STATIC["gateway"], "eth0"),
            dns_servers=[s for s in (ETH0_STATIC["dns1"], ETH0_STATIC["dns2"]) if s],
            interface_modes={"eth0": "[STATIC]"},
            extra_routes=[],
        )
        app.reload_dashboard()
        await pilot.pause(0.3)

        write_settings({"dashboard_display_live_information": True})
        app.reload_dashboard()
        await pilot.pause(0.5)
        await pilot.pause(12.0)
        shot(app, "02_dashboard_live")

        await pilot.press("f2")
        await pilot.pause(0.2)
        shot(app, "03_login")

        await pilot.press("tab")
        for char in "root":
            await pilot.press(char)
        await pilot.press("enter")
        await pilot.pause(0.4)
        shot(app, "04_menu")

        app.push_screen(HostnameDialog())
        await pilot.pause(0.3)
        shot(app, "05_hostname")
        app.pop_screen()
        await pilot.pause(0.1)

        app.push_screen(NetworkInterfaceDialog())
        await pilot.pause(0.3)
        shot(app, "06_network")
        app.pop_screen()
        await pilot.pause(0.1)

        await _shot_network_config(app, pilot, shot, "13_network_static_eth0", ETH0_STATIC)
        await _shot_network_config(app, pilot, shot, "14_network_dhcp_eth0", ETH0_DHCP)

        await _shot_dashboard_eth0(
            app, pilot, shot, "15_dashboard_eth0_static", ETH0_STATIC,
            write_settings=write_settings,
        )
        await _shot_dashboard_eth0(
            app, pilot, shot, "16_dashboard_eth0_dhcp", ETH0_DHCP,
            write_settings=write_settings,
        )

        await _shot_dashboard_vpn_interfaces(
            app, pilot, shot, write_settings=write_settings,
        )

        _install_stubs(log_path)
        app.reload_dashboard()
        await pilot.pause(0.2)

        app.push_screen(PackagesDialog())
        await pilot.pause(1.5)
        shot(app, "07_packages")
        app.pop_screen()
        await pilot.pause(0.1)

        app.push_screen(ThemeDialog())
        await pilot.pause(0.3)
        shot(app, "08_theme")
        app.pop_screen()
        await pilot.pause(0.1)

        app.push_screen(SettingsDialog())
        await pilot.pause(0.2)
        shot(app, "09_settings")
        app.pop_screen()
        await pilot.pause(0.1)

        await _paint_network_test_snapshot(app)
        await pilot.pause(0.2)
        shot(app, "10_network_test")
        app.pop_screen()
        await pilot.pause(0.1)

        show_view_system_metrics_dialog(app)
        await pilot.pause(20.0)
        shot(app, "11_system_metrics")
        app.pop_screen()
        await pilot.pause(0.1)

        show_view_zboxtui_logs_dialog(app)
        await pilot.pause(0.3)
        shot(app, "12_zboxtui_logs")
        app.pop_screen()

    for path in (config_path, log_path):
        path.unlink(missing_ok=True)

    for legacy in ("13_ping", "14_dns"):
        (OUT / f"{legacy}_{SUFFIX}.svg").unlink(missing_ok=True)


if __name__ == "__main__":
    asyncio.run(capture())
    print("Screenshots saved to", OUT)

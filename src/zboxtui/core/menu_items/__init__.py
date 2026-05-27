"""Built-in menu sections for the System Configuration screen.

File naming:
  configure_*  — General settings (hostname, password, packages, theme, settings)
  configure_network, network_* — Network configuration and diagnostics
  view_*       — Read-only viewers (logs, metrics)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .configure_hostname import show_hostname_dialog
from .configure_network import show_network_config_dialog
from .configure_packages import show_packages_dialog
from .configure_password import show_password_dialog
from .configure_settings import show_settings_dialog
from .configure_theme import show_theme_dialog
from .network_dns_lookup import show_network_dns_lookup_dialog
from .network_ping_host import show_network_ping_host_dialog
from .network_test_connectivity import show_network_test_dialog
from .view_system_logs import show_view_system_logs_dialog
from .view_system_metrics import show_view_system_metrics_dialog
from .view_zbox_logs import show_view_zbox_logs_dialog
from .view_zboxtui_logs import show_view_zboxtui_logs_dialog

if TYPE_CHECKING:
    from ...app import ZBoxTUI

PLUGINS_SECTION_TITLE = "Plugins"


@dataclass
class CoreMenuItem:
    """A built-in menu entry with its handler callable."""

    label: str
    description: str
    handler: Callable[[ZBoxTUI], None]


# ``None`` in a section item list inserts a blank row under that section header.
# ``None`` in :data:`MENU_SECTIONS` inserts a blank row between section groups.
GENERAL_MENU_ITEMS: list[CoreMenuItem | None] = [
    None,
    CoreMenuItem(
        label="Configure Hostname",
        description="Set the system hostname and DNS domain, with live FQDN preview.",
        handler=show_hostname_dialog,
    ),
    CoreMenuItem(
        label="Configure Password",
        description="Change the root password for this system.",
        handler=show_password_dialog,
    ),
    None,
    CoreMenuItem(
        label="Configure Packages",
        description="Install, update, or remove system packages.",
        handler=show_packages_dialog,
    ),
    CoreMenuItem(
        label="Configure Theme",
        description="Switch between the built-in color themes.",
        handler=show_theme_dialog,
    ),
    CoreMenuItem(
        label="Configure Settings",
        description="Edit application preferences: live dashboard, refresh interval, log file, defaults.",
        handler=show_settings_dialog,
    ),
    None,
    CoreMenuItem(
        label="View System Metrics",
        description="View live CPU, memory, storage, and network metrics.",
        handler=show_view_system_metrics_dialog,
    ),
]

NETWORK_MENU_ITEMS: list[CoreMenuItem | None] = [
    None,
    CoreMenuItem(
        label="Configure Network",
        description="Configure network interfaces, IP addresses, DNS, and routing.",
        handler=show_network_config_dialog,
    ),
    None,
    CoreMenuItem(
        label="Network: Test connectivity",
        description="Test network connectivity by pinging the gateway and DNS servers.",
        handler=show_network_test_dialog,
    ),
    CoreMenuItem(
        label="Network: Ping Host",
        description="Ping a host or IP address (default from settings).",
        handler=show_network_ping_host_dialog,
    ),
    CoreMenuItem(
        label="Network: DNS Lookup",
        description="Resolve a hostname via the system resolver or a custom DNS server.",
        handler=show_network_dns_lookup_dialog,
    ),
]

LOGS_MENU_ITEMS: list[CoreMenuItem | None] = [
    None,
    CoreMenuItem(
        label="View System Logs",
        description="View and search through system log files.",
        handler=show_view_system_logs_dialog,
    ),
    CoreMenuItem(
        label="View zBox Logs",
        description="View zBox configuration file.",
        handler=show_view_zbox_logs_dialog,
    ),
    CoreMenuItem(
        label="View zBoxTUI Logs",
        description="View zBoxTUI application log file.",
        handler=show_view_zboxtui_logs_dialog,
    ),
]

# Each entry is (section title, items) or ``None`` for a blank row between sections.
MenuSection = tuple[str, list[CoreMenuItem | None]] | None

MENU_SECTIONS: tuple[MenuSection, ...] = (
    ("General", GENERAL_MENU_ITEMS),
    None,
    ("Network", NETWORK_MENU_ITEMS),
    None,
    ("Logs", LOGS_MENU_ITEMS),
    None,
)

__all__ = [
    "GENERAL_MENU_ITEMS",
    "LOGS_MENU_ITEMS",
    "MENU_SECTIONS",
    "NETWORK_MENU_ITEMS",
    "PLUGINS_SECTION_TITLE",
    "CoreMenuItem",
    "show_hostname_dialog",
    "show_network_config_dialog",
    "show_network_dns_lookup_dialog",
    "show_network_ping_host_dialog",
    "show_network_test_dialog",
    "show_packages_dialog",
    "show_password_dialog",
    "show_settings_dialog",
    "show_theme_dialog",
    "show_view_system_logs_dialog",
    "show_view_system_metrics_dialog",
    "show_view_zbox_logs_dialog",
    "show_view_zboxtui_logs_dialog",
]

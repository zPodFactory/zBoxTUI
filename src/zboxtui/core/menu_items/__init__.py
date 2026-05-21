"""Built-in (non-plugin) menu items shown in the System Configuration screen."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .network import show_network_config_dialog, show_restart_network_dialog
from .network_test import show_network_test_dialog
from .packages import show_packages_dialog
from .password import show_password_dialog
from .theme import show_theme_dialog

if TYPE_CHECKING:
    from ...app import ZBoxTUI


@dataclass
class CoreMenuItem:
    """A built-in menu entry with its handler callable."""

    label: str
    description: str
    handler: Callable[[ZBoxTUI], None]


# Use ``None`` to insert a blank separator row between subgroups inside the
# General section. MenuScreen walks this list and yields separators / items
# accordingly.
CORE_MENU_ITEMS: list[CoreMenuItem | None] = [
    CoreMenuItem(
        label="Configure Password",
        description="Change the root password for this system.",
        handler=show_password_dialog,
    ),
    CoreMenuItem(
        label="Configure Network",
        description="Configure network interfaces, IP addresses, DNS, and routing.",
        handler=show_network_config_dialog,
    ),
    CoreMenuItem(
        label="Restart Network",
        description="Restart all network services and apply configuration changes.",
        handler=show_restart_network_dialog,
    ),
    CoreMenuItem(
        label="Test Network",
        description="Test network connectivity by pinging the gateway and DNS servers.",
        handler=show_network_test_dialog,
    ),
    None,
    CoreMenuItem(
        label="Configure Packages",
        description="Install, update, or remove system packages.",
        handler=show_packages_dialog,
    ),
    CoreMenuItem(
        label="Configure Theme",
        description="Switch between the available color themes (catppuccin, esxi).",
        handler=show_theme_dialog,
    ),
]

__all__ = [
    "CORE_MENU_ITEMS",
    "CoreMenuItem",
    "show_network_config_dialog",
    "show_network_test_dialog",
    "show_packages_dialog",
    "show_password_dialog",
    "show_restart_network_dialog",
    "show_theme_dialog",
]

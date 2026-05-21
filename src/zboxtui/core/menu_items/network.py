"""Network configuration menu item handlers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..utils.logging import get_logger
from ..widgets.dcui_dialog import (
    MessageDialog,
    NetworkConfigDialog,
    NetworkInterfaceDialog,
)

if TYPE_CHECKING:
    from ...app import ZBoxTUI

log = get_logger("menu.network")


def show_network_config_dialog(app: ZBoxTUI) -> None:
    """Show the network interface picker, then the per-interface config dialog."""
    log.info("Opening Configure Network dialog")

    def handle_interface_selection(interface_name: str | None) -> None:
        if interface_name is None:
            log.debug("Interface selection cancelled")
            return
        log.info("Interface selected: %s", interface_name)
        app.push_screen(NetworkConfigDialog(interface_name))

    app.push_screen(NetworkInterfaceDialog(), callback=handle_interface_selection)


def show_restart_network_dialog(app: ZBoxTUI) -> None:
    """Show the restart-network confirmation (placeholder)."""
    log.info("Opening Restart Network dialog")
    app.push_screen(
        MessageDialog(
            "Restart Network",
            "This will restart all network services.\n\n"
            "Feature not yet implemented.",
        ),
    )

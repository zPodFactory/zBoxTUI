"""Network configuration menu item handlers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..utils.logging import get_logger
from ..utils.system_control import NETWORKING_RESTART_CMD
from ..widgets.dcui_dialog import NetworkConfigDialog, NetworkInterfaceDialog
from .privileged_flow import run_confirmed_privileged_command

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
    """Restart ``networking.service`` after operator confirmation."""
    log.info("Opening Restart Network confirmation")
    run_confirmed_privileged_command(
        app,
        confirm_title="Restart Network",
        confirm_message=(
            "Restart the networking service?\n\n"
            "This applies /etc/network/interfaces changes and may "
            "briefly interrupt connectivity."
        ),
        argv=NETWORKING_RESTART_CMD,
        ok_title="Network Restarted",
        fail_title="Restart Failed",
        no_privilege_title="Cannot Restart Network",
        ok_message="Network services restarted.",
        timeout=60,
    )

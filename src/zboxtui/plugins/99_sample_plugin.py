"""Sample plugin for the Plugins menu section."""

from __future__ import annotations

from typing import TYPE_CHECKING

from zboxtui.core.utils.logging import get_logger
from zboxtui.core.widgets.dcui_dialog import MessageDialog

if TYPE_CHECKING:
    from zboxtui.app import ZBoxTUI

MENU_LABEL = "Sample Plugin"
MENU_SECTION = "Plugins"
MENU_DESCRIPTION = "Example entry showing how to add a plugin menu item."

log = get_logger("plugin.sample")


def show_dialog(app: ZBoxTUI) -> None:
    log.info("Opening sample plugin dialog")
    app.push_screen(
        MessageDialog(
            "Sample Plugin",
            "This is a placeholder plugin.\n\n"
            "Copy 99_sample_plugin.py, set MENU_LABEL and MENU_SECTION "
            '(must be "Plugins"), and implement show_dialog().',
            ack_only=True,
        ),
    )

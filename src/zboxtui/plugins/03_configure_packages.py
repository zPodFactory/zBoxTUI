"""Plugin: Configure Packages (placeholder)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from zboxtui.core.utils.logging import get_logger
from zboxtui.core.widgets.dcui_dialog import MessageDialog

if TYPE_CHECKING:
    from zboxtui.app import ZBoxTUI

MENU_LABEL = "Configure Packages"
MENU_DESCRIPTION = "Install, update, or remove system packages."

log = get_logger("plugin.packages")


def show_dialog(app: ZBoxTUI) -> None:
    log.info("Opening Configure Packages dialog")
    app.push_screen(
        MessageDialog(
            "Configure Packages",
            "Package management will be implemented here.\n\n"
            "This will allow:\n"
            "- Installing packages\n"
            "- Updating packages\n"
            "- Removing packages",
        ),
    )

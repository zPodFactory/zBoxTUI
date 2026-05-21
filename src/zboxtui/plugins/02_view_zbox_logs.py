"""Plugin: View zBox Logs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from zboxtui.core.utils.logging import get_logger
from zboxtui.core.widgets.dcui_dialog import ZBoxLogsDialog

if TYPE_CHECKING:
    from zboxtui.app import ZBoxTUI

MENU_LABEL = "View zBox Logs"
MENU_DESCRIPTION = "View zBox configuration file."

log = get_logger("plugin.zbox_logs")


def show_dialog(app: ZBoxTUI) -> None:
    log.info("Opening zBox Logs viewer")
    app.push_screen(ZBoxLogsDialog())

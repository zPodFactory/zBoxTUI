"""Plugin: View System Logs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from zboxtui.core.utils.logging import get_logger
from zboxtui.core.widgets.dcui_dialog import SystemLogsDialog

if TYPE_CHECKING:
    from zboxtui.app import ZBoxTUI

MENU_LABEL = "View System Logs"
MENU_DESCRIPTION = "View and search through system log files."

log = get_logger("plugin.system_logs")


def show_dialog(app: ZBoxTUI) -> None:
    log.info("Opening System Logs viewer")
    app.push_screen(SystemLogsDialog())

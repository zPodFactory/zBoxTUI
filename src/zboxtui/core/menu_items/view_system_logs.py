"""View System Logs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from zboxtui.core.utils.logging import get_logger
from zboxtui.core.widgets.dcui_dialog import SystemLogsDialog

if TYPE_CHECKING:
    from zboxtui.app import ZBoxTUI

log = get_logger("menu.view_system_logs")


def show_view_system_logs_dialog(app: ZBoxTUI) -> None:
    log.info("Opening System Logs")
    app.push_screen(SystemLogsDialog())

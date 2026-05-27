"""View zBoxTUI Logs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from zboxtui.core.utils.logging import get_logger
from zboxtui.core.widgets.dcui_dialog import ZBoxTuiLogsDialog

if TYPE_CHECKING:
    from zboxtui.app import ZBoxTUI

log = get_logger("menu.view_zboxtui_logs")


def show_view_zboxtui_logs_dialog(app: ZBoxTUI) -> None:
    log.info("Opening zBoxTUI Logs")
    app.push_screen(ZBoxTuiLogsDialog())

"""View zBox Logs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from zboxtui.core.utils.logging import get_logger
from zboxtui.core.widgets.dcui_dialog import ZBoxLogsDialog

if TYPE_CHECKING:
    from zboxtui.app import ZBoxTUI

log = get_logger("menu.view_zbox_logs")


def show_view_zbox_logs_dialog(app: ZBoxTUI) -> None:
    log.info("Opening zBox Logs")
    app.push_screen(ZBoxLogsDialog())

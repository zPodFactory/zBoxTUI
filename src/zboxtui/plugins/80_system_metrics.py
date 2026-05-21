"""Plugin: System Metrics dashboard (live CPU/memory/disk + RX/TX sparklines)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from zboxtui.core.utils.logging import get_logger
from zboxtui.core.widgets.dcui_dialog import SystemStatsDialog

if TYPE_CHECKING:
    from zboxtui.app import ZBoxTUI

MENU_LABEL = "View System Stats"
MENU_DESCRIPTION = "View live CPU, memory, storage, and network metrics."

log = get_logger("plugin.system_metrics")


def show_dialog(app: ZBoxTUI) -> None:
    log.info("Opening System Stats dialog")
    app.push_screen(SystemStatsDialog())

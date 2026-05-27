"""View System Metrics."""

from __future__ import annotations

from typing import TYPE_CHECKING

from zboxtui.core.utils.logging import get_logger
from zboxtui.core.widgets.dcui_dialog import SystemStatsDialog

if TYPE_CHECKING:
    from zboxtui.app import ZBoxTUI

log = get_logger("menu.view_system_metrics")


def show_view_system_metrics_dialog(app: ZBoxTUI) -> None:
    log.info("Opening System Metrics")
    app.push_screen(SystemStatsDialog())

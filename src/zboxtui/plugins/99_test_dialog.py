"""Plugin: Test Dialog (modal template for styling/layout development)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from zboxtui.core.utils.logging import get_logger
from zboxtui.core.widgets.dcui_dialog import TestDialog

if TYPE_CHECKING:
    from zboxtui.app import ZBoxTUI

MENU_LABEL = "Test Dialog"
MENU_DESCRIPTION = "Display a template dialog for testing modal styling and layout."

log = get_logger("plugin.test_dialog")


def show_dialog(app: ZBoxTUI) -> None:
    log.info("Opening Test Dialog")
    app.push_screen(TestDialog())

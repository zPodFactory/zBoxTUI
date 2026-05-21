"""Network connectivity test menu item handler."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..utils.logging import get_logger
from ..widgets.dcui_dialog import NetworkTestDialog

if TYPE_CHECKING:
    from ...app import ZBoxTUI

log = get_logger("menu.network_test")


def show_network_test_dialog(app: ZBoxTUI) -> None:
    """Show the gateway/DNS ping dialog."""
    log.info("Opening Test Network dialog")
    app.push_screen(NetworkTestDialog())

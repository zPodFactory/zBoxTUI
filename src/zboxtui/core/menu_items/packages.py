"""Package management menu item handler (placeholder)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..utils.logging import get_logger
from ..widgets.dcui_dialog import MessageDialog

if TYPE_CHECKING:
    from ...app import ZBoxTUI

log = get_logger("menu.packages")


def show_packages_dialog(app: ZBoxTUI) -> None:
    """Open the package management dialog (not yet implemented)."""
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

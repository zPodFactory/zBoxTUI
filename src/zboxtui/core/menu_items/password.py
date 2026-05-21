"""Password configuration menu item handler."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..utils.logging import get_logger
from ..widgets.dcui_dialog import PasswordDialog

if TYPE_CHECKING:
    from ...app import ZBoxTUI

log = get_logger("menu.password")


def show_password_dialog(app: ZBoxTUI) -> None:
    """Show the password configuration dialog."""
    log.info("Opening Configure Password dialog")
    app.push_screen(PasswordDialog())

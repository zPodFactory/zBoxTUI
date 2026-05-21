"""Plugin: Test Google DNS Ping (8.8.8.8)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.timer import Timer
from textual.widgets import Static

from zboxtui.core.utils.logging import get_logger
from zboxtui.core.widgets import DCUI_DIALOG_CSS, ping_host

if TYPE_CHECKING:
    from zboxtui.app import ZBoxTUI

MENU_LABEL = "Test Google Ping"
MENU_DESCRIPTION = "Test network connectivity by pinging Google DNS (8.8.8.8)."

_TARGET_HOST = "8.8.8.8"
_TARGET_LABEL = "Google DNS"
_SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

log = get_logger("plugin.google_ping")


class GooglePingDialog(ModalScreen[None]):
    """Dialog that pings 8.8.8.8 with a spinner and shows the result."""

    BINDINGS = [
        Binding("escape", "close", "Close", show=False),
        Binding("enter", "close", "Close", show=False),
        Binding("r", "retest", "Retest", show=False),
    ]

    DEFAULT_CSS = DCUI_DIALOG_CSS.format(dialog_class="GooglePingDialog", width=50) + """
    GooglePingDialog .test-row {
        height: 1;
    }

    GooglePingDialog .test-label {
        width: 25;
        color: $z-fg;
    }

    GooglePingDialog .test-status {
        width: 1fr;
        color: $z-fg;
    }

    GooglePingDialog .test-status.--success {
        color: $z-success;
    }

    GooglePingDialog .test-status.--failure {
        color: $z-error;
    }

    GooglePingDialog .test-status.--pending {
        color: $z-fg-faint;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._spinner_index = 0
        self._spinner_timer: Timer | None = None

    def compose(self) -> ComposeResult:
        with Container(id="dialog-outer"):
            with Vertical(id="dialog-header"):
                yield Static("")
                yield Static(f"Test {_TARGET_LABEL}", id="dialog-title")
                yield Static("")
                yield Static(f"Pinging {_TARGET_HOST}...", id="dialog-subtitle")
                yield Static("")
            with Vertical(id="dialog-body"):
                with Horizontal(classes="test-row"):
                    yield Static(f"{_TARGET_LABEL} ({_TARGET_HOST}):", classes="test-label")
                    yield Static("⠋", classes="test-status --pending", id="ping-status")
                yield Static("")
                yield Static("<Enter> Close    <R> Retest", id="dialog-footer")

    def on_mount(self) -> None:
        self._run_test()

    def _start_spinner(self) -> None:
        self._stop_spinner()
        self._spinner_index = 0
        self._update_spinner()
        self._spinner_timer = self.set_interval(0.1, self._update_spinner)

    def _stop_spinner(self) -> None:
        if self._spinner_timer is not None:
            self._spinner_timer.stop()
            self._spinner_timer = None

    def _update_spinner(self) -> None:
        status = self.query_one("#ping-status", Static)
        char = _SPINNER_FRAMES[self._spinner_index % len(_SPINNER_FRAMES)]
        status.update(char)
        self._spinner_index += 1

    @work(exclusive=True)
    async def _run_test(self) -> None:
        status = self.query_one("#ping-status", Static)
        self._start_spinner()

        success, message = await ping_host(_TARGET_HOST)

        self._stop_spinner()
        status.remove_class("--pending")
        status.add_class("--success" if success else "--failure")
        status.update(message)

    def action_close(self) -> None:
        self._stop_spinner()
        self.dismiss()

    def action_retest(self) -> None:
        status = self.query_one("#ping-status", Static)
        status.remove_class("--success", "--failure")
        status.add_class("--pending")
        self._run_test()


def show_dialog(app: ZBoxTUI) -> None:
    log.info("Opening Google Ping Test dialog")
    app.push_screen(GooglePingDialog())

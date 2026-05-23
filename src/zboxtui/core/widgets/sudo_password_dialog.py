"""Modal that captures the user's sudo password.

Used by the Configure Packages flow when the running user has sudo
access but not NOPASSWD. The dialog validates the password with
``sudo -k && sudo -S -v`` (refresh + validate, non-destructive) before
returning it, so we don't push the rest of the pipeline only to fail
on the first real apt command.

Returns the validated password (str) on success, or None if the user
cancels. The password is held in memory only for the lifetime of the
caller's reference.
"""

from __future__ import annotations

import contextlib
import subprocess
from typing import TYPE_CHECKING

from rich.spinner import Spinner
from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.timer import Timer
from textual.widgets import Input, Static

from ..utils.logging import get_logger
from .dcui_dialog import DCUI_DIALOG_CSS

if TYPE_CHECKING:
    from ...app import ZBoxTUI

log = get_logger("sudo_dialog")

_SPINNER_REFRESH = 1 / 15


class SudoPasswordDialog(ModalScreen[str | None]):
    """Prompt for the sudo password and validate it before returning."""

    app: ZBoxTUI

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    DEFAULT_CSS = DCUI_DIALOG_CSS.format(dialog_class="SudoPasswordDialog", width=50) + """
    SudoPasswordDialog .form-row {
        height: 1;
        width: 100%;
    }

    SudoPasswordDialog .form-label {
        width: 15;
        color: $z-fg;
        height: 1;
        content-align: left middle;
    }

    SudoPasswordDialog .form-input {
        width: 1fr;
        background: $z-mantle;
        color: $z-fg;
        border: none;
        height: 1;
    }

    SudoPasswordDialog .form-input:focus {
        background: $z-panel-focus;
    }

    SudoPasswordDialog #spinner {
        width: 3;
        height: 1;
        color: $z-fg-faint;
        content-align: center middle;
    }

    SudoPasswordDialog #spinner.--hidden {
        display: none;
    }

    SudoPasswordDialog #error-container {
        height: auto;
    }

    SudoPasswordDialog #error-container.--hidden {
        display: none;
    }

    SudoPasswordDialog #error-message {
        height: 1;
        text-align: center;
        color: $z-error;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._spinner_timer: Timer | None = None

    def compose(self) -> ComposeResult:
        with Container(id="dialog-outer"):
            with Vertical(id="dialog-header"):
                yield Static("")
                yield Static("Sudo Authentication", id="dialog-title")
                yield Static("")
                yield Static(
                    "Enter your password to run apt-get with sudo.",
                    id="dialog-subtitle",
                )
                yield Static("")
            with Vertical(id="dialog-body"):
                with Horizontal(classes="form-row"):
                    yield Static("Password:", classes="form-label")
                    yield Input(
                        password=True,
                        placeholder="sudo password",
                        classes="form-input",
                        id="password-input",
                    )
                    yield Static("", id="spinner", classes="--hidden")
                with Vertical(id="error-container", classes="--hidden"):
                    yield Static("")
                    yield Static("", id="error-message")
                yield Static("")
                yield Static("<Enter> OK    <Esc> Cancel", id="dialog-footer")

    def on_mount(self) -> None:
        self.query_one("#password-input", Input).focus()

    @on(Input.Submitted)
    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "password-input":
            self._submit()

    def _submit(self) -> None:
        password = self.query_one("#password-input", Input).value
        error_container = self.query_one("#error-container", Vertical)
        error_msg = self.query_one("#error-message", Static)

        if not password:
            error_container.remove_class("--hidden")
            error_msg.update("Error: Password is required")
            return

        error_container.add_class("--hidden")
        self.query_one("#password-input", Input).disabled = True
        self._start_spinner()
        self._verify_password(password)

    def _start_spinner(self) -> None:
        spinner = self.query_one("#spinner", Static)
        spinner.remove_class("--hidden")
        spinner.update(Spinner("dots"))
        spinner.auto_refresh = _SPINNER_REFRESH

    def _stop_spinner(self) -> None:
        spinner = self.query_one("#spinner", Static)
        spinner.auto_refresh = None
        spinner.add_class("--hidden")
        spinner.update("")

    @work(thread=True)
    def _verify_password(self, password: str) -> None:
        log.debug("Validating sudo password")
        ok = _validate_sudo_password(password)
        self.app.call_from_thread(self._handle_result, password if ok else None)

    def _handle_result(self, password: str | None) -> None:
        self._stop_spinner()
        password_input = self.query_one("#password-input", Input)
        password_input.disabled = False

        if password is not None:
            log.info("Sudo password validated")
            self.dismiss(password)
            return

        log.warning("Sudo password validation failed")
        error_container = self.query_one("#error-container", Vertical)
        error_msg = self.query_one("#error-message", Static)
        error_container.remove_class("--hidden")
        error_msg.update("Error: Invalid password")
        password_input.value = ""
        password_input.focus()

    def action_cancel(self) -> None:
        self.dismiss(None)


def _validate_sudo_password(password: str) -> bool:
    """Validate the password with ``sudo -k && sudo -S -v``.

    -k drops any cached credentials first so this is an actual test
    (otherwise NOPASSWD-cached credentials would falsely return OK).
    -v refreshes the user's sudo timestamp; -S reads from stdin.
    Non-destructive — runs no command, just authenticates.
    """
    with contextlib.suppress(subprocess.TimeoutExpired, FileNotFoundError, OSError):
        subprocess.run(
            ["sudo", "-k"],
            check=False,
            capture_output=True,
            timeout=5,
        )

    try:
        proc = subprocess.run(
            ["sudo", "-S", "-p", "", "-v"],
            input=f"{password}\n",
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False
    return proc.returncode == 0

"""Confirm → sudo (if needed) → privileged command → result dialog."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from rich.spinner import Spinner
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from ..utils.logging import get_logger
from ..utils.privilege import NO_PRIVILEGE_MSG, Privilege, detect_privilege, run_privileged_command
from ..utils.system_control import REBOOT_CMD
from ..widgets.dcui_dialog import DCUI_DIALOG_CSS, MessageDialog
from ..widgets.sudo_password_dialog import SudoPasswordDialog

if TYPE_CHECKING:
    from ...app import ZBoxTUI

log = get_logger("menu.privileged")

_SPINNER_REFRESH = 1 / 15
_REBOOT_SPINNER_DWELL_S = 2.0
_REBOOT_CMD_TIMEOUT_S = 15.0


def run_confirmed_privileged_command(
    app: ZBoxTUI,
    *,
    confirm_title: str,
    confirm_message: str,
    argv: Sequence[str],
    ok_title: str,
    fail_title: str,
    no_privilege_title: str,
    ok_message: str = "Done.",
    timeout: float = 120,
) -> None:
    """Show confirm, then run ``argv`` with root/sudo and report success or failure."""

    def after_confirm(confirmed: bool | None) -> None:
        if confirmed is not True:
            return
        _launch_privileged_command(
            app,
            argv,
            confirm_title=confirm_title,
            ok_title=ok_title,
            fail_title=fail_title,
            no_privilege_title=no_privilege_title,
            ok_message=ok_message,
            timeout=timeout,
        )

    app.push_screen(
        MessageDialog(confirm_title, confirm_message),
        callback=after_confirm,
    )


def _launch_privileged_command(
    app: ZBoxTUI,
    argv: Sequence[str],
    *,
    confirm_title: str,
    ok_title: str,
    fail_title: str,
    no_privilege_title: str,
    ok_message: str,
    timeout: float,
) -> None:
    app.run_worker(
        lambda: app.call_from_thread(
            _finish_privileged_command,
            app,
            list(argv),
            detect_privilege(),
            confirm_title=confirm_title,
            ok_title=ok_title,
            fail_title=fail_title,
            no_privilege_title=no_privilege_title,
            ok_message=ok_message,
            timeout=timeout,
        ),
        thread=True,
        exclusive=False,
    )


def _finish_privileged_command(
    app: ZBoxTUI,
    argv: list[str],
    privilege: Privilege,
    *,
    confirm_title: str,
    ok_title: str,
    fail_title: str,
    no_privilege_title: str,
    ok_message: str,
    timeout: float,
) -> None:
    log.info("Privileged command requested (%s); privilege=%s", confirm_title, privilege.name)
    if privilege == Privilege.NONE:
        app.push_screen(MessageDialog(no_privilege_title, NO_PRIVILEGE_MSG))
        return

    def run_with_password(password: str | None) -> None:
        sudo_password = password if privilege == Privilege.SUDO_PASSWORD else None

        def worker() -> None:
            ok, detail = run_privileged_command(
                argv,
                privilege,
                password=sudo_password,
                timeout=timeout,
            )
            title = ok_title if ok else fail_title
            body = ok_message if ok else detail
            app.call_from_thread(lambda: app.push_screen(MessageDialog(title, body)))

        app.run_worker(worker, thread=True, exclusive=False)

    if privilege == Privilege.SUDO_PASSWORD:
        cached = app.session_sudo_password
        if cached:
            run_with_password(cached)
            return

        def handle_password(pw: str | None) -> None:
            if pw is None:
                return
            app.remember_sudo_password(pw)
            run_with_password(pw)

        app.push_screen(SudoPasswordDialog(), callback=handle_password)
    else:
        run_with_password(None)


def run_confirmed_reboot(app: ZBoxTUI) -> None:
    """Confirm, then show a spinner briefly before ``systemctl reboot``."""

    def after_confirm(confirmed: bool | None) -> None:
        if confirmed is not True:
            return
        _launch_reboot(app)

    app.push_screen(
        MessageDialog(
            "Reboot System",
            "Reboot this system now?\n\n"
            "The zBoxTUI session will end and the host will restart.",
        ),
        callback=after_confirm,
    )


def _launch_reboot(app: ZBoxTUI) -> None:
    app.run_worker(
        lambda: app.call_from_thread(_finish_reboot, app, detect_privilege()),
        thread=True,
        exclusive=False,
    )


def _finish_reboot(app: ZBoxTUI, privilege: Privilege) -> None:
    log.info("Reboot requested; privilege=%s", privilege.name)
    if privilege == Privilege.NONE:
        app.push_screen(MessageDialog("Cannot Reboot", NO_PRIVILEGE_MSG))
        return

    def show_spinner(password: str | None) -> None:
        sudo_password = password if privilege == Privilege.SUDO_PASSWORD else None
        app.push_screen(RebootingDialog(privilege, sudo_password))

    if privilege == Privilege.SUDO_PASSWORD:
        cached = app.session_sudo_password
        if cached:
            show_spinner(cached)
            return

        def handle_password(pw: str | None) -> None:
            if pw is None:
                return
            app.remember_sudo_password(pw)
            show_spinner(pw)

        app.push_screen(SudoPasswordDialog(), callback=handle_password)
    else:
        show_spinner(None)


class RebootingDialog(ModalScreen[None]):
    """Spinner shown briefly before the host reboots."""

    app: ZBoxTUI

    BINDINGS = [
        Binding("escape", "noop", show=False),
        Binding("q", "noop", show=False),
    ]

    DEFAULT_CSS = DCUI_DIALOG_CSS.format(dialog_class="RebootingDialog", width=45) + """
    RebootingDialog #reboot-row {
        height: 1;
        margin: 1 0;
    }

    RebootingDialog #reboot-status {
        width: 1fr;
        content-align: center middle;
        color: $z-fg;
    }
    """

    def __init__(
        self,
        privilege: Privilege,
        sudo_password: str | None,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._privilege = privilege
        self._sudo_password = sudo_password

    def compose(self) -> ComposeResult:
        with Container(id="dialog-outer"):
            with Vertical(id="dialog-header"):
                yield Static("")
                yield Static("Reboot System", id="dialog-title")
                yield Static("")
            with Vertical(id="dialog-body"):
                with Horizontal(id="reboot-row"):
                    yield Static(
                        Spinner("dots", text=" Rebooting system…"),
                        id="reboot-status",
                    )
                yield Static("")

    def on_mount(self) -> None:
        status = self.query_one("#reboot-status", Static)
        status.auto_refresh = _SPINNER_REFRESH
        self.set_timer(_REBOOT_SPINNER_DWELL_S, self._start_reboot)

    def action_noop(self) -> None:
        """Ignore keys while reboot is in progress."""

    def _start_reboot(self) -> None:
        self._reboot_worker()

    @work(thread=True, exclusive=True)
    def _reboot_worker(self) -> None:
        ok, detail = run_privileged_command(
            REBOOT_CMD,
            self._privilege,
            password=self._sudo_password,
            timeout=_REBOOT_CMD_TIMEOUT_S,
        )
        if not ok:
            self.app.call_from_thread(self._show_failure, detail)

    def _show_failure(self, detail: str) -> None:
        self.query_one("#reboot-status", Static).auto_refresh = None
        self.dismiss()
        self.app.push_screen(MessageDialog("Reboot Failed", detail))

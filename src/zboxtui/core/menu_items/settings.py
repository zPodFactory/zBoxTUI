"""Configure Settings: edit zBoxTUI's own preferences.

Mirrors the layout of the password / network dialogs but acts on the
in-memory :class:`AppConfig` and persists changes via
:func:`write_settings`. Boolean settings use Textual's built-in
``Switch`` (Space toggles when focused); string/numeric settings use
``Input``.

On Apply, the dialog hands off to :class:`ApplySettingsDialog` — a
short-lived spinner modal that runs the write + dashboard reload in a
worker and auto-dismisses (along with the Settings dialog) once both
complete. That way the operator sees explicit progress instead of a
freeze, and lands straight back on the menu when it's done.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from rich.spinner import Spinner
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Static, Switch

from ..utils.config import get_config, write_settings
from ..utils.logging import get_logger
from ..widgets.dcui_dialog import DCUI_DIALOG_CSS

if TYPE_CHECKING:
    from ...app import ZBoxTUI

log = get_logger("menu.settings")


_BOOL_FIELDS: tuple[tuple[str, str, str], ...] = (
    (
        "dashboard_display_live_information",
        "Live dashboard info",
        "CPU/MEM Usage bars + Storage panel on the dashboard.",
    ),
)

_TEXT_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("log_file", "Log file", "/var/log/zboxtui.log on a real deploy"),
    (
        "dashboard_refresh_interval_seconds",
        "Refresh (sec)",
        "How often the dashboard re-samples /proc.",
    ),
)


def _coerce(field: str, value: str) -> object:
    """Convert raw text input to the type the AppConfig field expects."""
    if field == "dashboard_refresh_interval_seconds":
        return max(0.5, float(value.strip()))
    return value.strip()


_SPINNER_REFRESH = 1 / 15
# Minimum time the "Applying…" modal stays up — the actual work is
# usually a few ms (write a file + schedule a worker), so without a
# dwell the modal would only flash. 0.5s is enough to register as a
# deliberate step, short enough not to feel laggy.
_APPLY_DWELL_S = 0.5


class ApplySettingsDialog(ModalScreen[bool]):
    """Short-lived spinner shown while settings are being written.

    Owns the actual ``write_settings`` + ``reload_dashboard`` calls so
    SettingsDialog can dismiss immediately on Apply and the operator
    sees a single "Applying…" indicator instead of a frozen Settings
    panel.
    """

    app: ZBoxTUI

    DEFAULT_CSS = DCUI_DIALOG_CSS.format(dialog_class="ApplySettingsDialog", width=45) + """
    ApplySettingsDialog #apply-row {
        height: 1;
        margin: 1 0;
    }

    ApplySettingsDialog #apply-status {
        width: 1fr;
        content-align: center middle;
        color: $z-fg;
    }
    """

    def __init__(self, updates: dict[str, object]) -> None:
        super().__init__()
        self._updates = updates

    def compose(self) -> ComposeResult:
        with Container(id="dialog-outer"):
            with Vertical(id="dialog-header"):
                yield Static("")
                yield Static("Applying Settings", id="dialog-title")
                yield Static("")
            with Vertical(id="dialog-body"):
                with Horizontal(id="apply-row"):
                    yield Static(
                        Spinner("dots", text=" Applying settings…"),
                        id="apply-status",
                    )
                yield Static("")

    def on_mount(self) -> None:
        self.query_one("#apply-status", Static).auto_refresh = _SPINNER_REFRESH
        self._apply_worker()

    @work(exclusive=True)
    async def _apply_worker(self) -> None:
        # Fast path: write to disk on the event loop (it's a few ms,
        # the file is tiny). The user-visible cost is recompose().
        log.info("Persisting settings: %s", self._updates)
        path = write_settings(self._updates)
        if path is None:
            self._fail("Could not write to any config file")
            return

        # Trigger the dashboard rebuild; it schedules its own worker
        # so this returns immediately.
        self.app.reload_dashboard()

        # Hold the spinner up long enough for the operator to register
        # "something happened" — the real work is already in flight.
        await asyncio.sleep(_APPLY_DWELL_S)

        self.query_one("#apply-status", Static).auto_refresh = None
        self.dismiss(True)

    def _fail(self, message: str) -> None:
        status = self.query_one("#apply-status", Static)
        status.auto_refresh = None
        status.update(message)
        self.set_timer(2.0, lambda: self.dismiss(False))


class SettingsDialog(ModalScreen[bool]):
    """Form to edit the toggleable + writable application settings."""

    app: ZBoxTUI

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("q", "cancel", "Cancel", show=False),
        Binding("enter", "apply", "Apply", show=False, priority=True),
    ]

    DEFAULT_CSS = DCUI_DIALOG_CSS.format(dialog_class="SettingsDialog", width=70) + """
    SettingsDialog .form-row {
        height: 1;
        width: 100%;
    }

    SettingsDialog .form-label {
        width: 22;
        color: $z-fg;
        height: 1;
        content-align: left middle;
    }

    SettingsDialog .form-input {
        width: 1fr;
        background: $z-mantle;
        color: $z-panel-fg;
        border: none;
        height: 1;
    }

    SettingsDialog .form-input:focus {
        background: $z-panel-focus;
    }

    /* Switch is designed for a 3-line row (border + padding). Strip
     * them so it collapses to the native 4×1 slider; background swap
     * stands in for the missing focus border. */
    SettingsDialog .bool-switch {
        border: none;
        padding: 0;
        width: 4;
        height: 1;
        background: $z-mantle;
    }

    SettingsDialog .bool-switch:focus {
        border: none;
        background: $z-panel-focus;
    }

    SettingsDialog .bool-switch > .switch--slider {
        color: $z-fg-faint;
        background: $z-mantle;
    }

    SettingsDialog .bool-switch:focus > .switch--slider {
        background: $z-panel-focus;
    }

    SettingsDialog .bool-switch.-on > .switch--slider {
        color: $z-success;
    }

    SettingsDialog .section-label {
        color: $z-fg-faint;
        margin-top: 1;
    }

    SettingsDialog #error-message {
        color: $z-error;
        height: 1;
        text-align: center;
    }
    """

    def compose(self) -> ComposeResult:
        cfg = get_config()
        with Container(id="dialog-outer"):
            with Vertical(id="dialog-header"):
                yield Static("")
                yield Static("Configure Settings", id="dialog-title")
                yield Static("")
                yield Static(
                    "Edit zBoxTUI preferences. Changes apply immediately.",
                    id="dialog-subtitle",
                )
                yield Static("")
            with Vertical(id="dialog-body"):
                yield Static("Toggles", classes="section-label")
                for field, label, _ in _BOOL_FIELDS:
                    with Horizontal(classes="form-row"):
                        yield Static(f"{label}:", classes="form-label")
                        yield Switch(
                            value=bool(getattr(cfg, field)),
                            animate=False,
                            classes="bool-switch",
                            id=self._field_id(field),
                        )
                yield Static("Values", classes="section-label")
                for field, label, _ in _TEXT_FIELDS:
                    with Horizontal(classes="form-row"):
                        yield Static(f"{label}:", classes="form-label")
                        yield Input(
                            value=str(getattr(cfg, field)),
                            classes="form-input",
                            id=self._field_id(field),
                        )
                yield Static("", id="error-message")
                yield Static("")
                yield Static(
                    "<Space> Toggle    <Tab> Next    <Enter> Apply    <Esc> Cancel",
                    id="dialog-footer",
                )

    @staticmethod
    def _field_id(field: str) -> str:
        return "setting-" + field.replace("_", "-")

    def on_mount(self) -> None:
        self.app.save_debug_screenshot("settings_dialog")
        first = _BOOL_FIELDS[0][0] if _BOOL_FIELDS else _TEXT_FIELDS[0][0]
        self.query_one(f"#{self._field_id(first)}").focus()

    def _collect_updates(self) -> dict[str, object] | str:
        """Return the updates dict, or an error string for invalid input."""
        updates: dict[str, object] = {}
        for field, _, _ in _BOOL_FIELDS:
            updates[field] = self.query_one(f"#{self._field_id(field)}", Switch).value
        for field, label, _ in _TEXT_FIELDS:
            widget = self.query_one(f"#{self._field_id(field)}", Input)
            try:
                updates[field] = _coerce(field, widget.value)
            except (TypeError, ValueError):
                return f"Invalid value for {label}"
        return updates

    def action_apply(self) -> None:
        updates = self._collect_updates()
        error_msg = self.query_one("#error-message", Static)
        if isinstance(updates, str):
            error_msg.update(updates)
            return
        error_msg.update("")

        # Hand off to the spinner modal; when it dismisses (success or
        # failure), we dismiss too so the operator is back at the menu.
        def _after_apply(ok: bool | None) -> None:
            if ok:
                self.dismiss(True)

        self.app.push_screen(ApplySettingsDialog(updates), callback=_after_apply)

    def action_cancel(self) -> None:
        self.dismiss(False)


def show_settings_dialog(app: ZBoxTUI) -> None:
    log.info("Opening Configure Settings dialog")
    app.push_screen(SettingsDialog())

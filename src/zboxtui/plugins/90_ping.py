"""Plugin: Ping — interactive connectivity probe with spinner + dots.

Mirrors the look of the core "Test Network" dialog: the result row
shows a live Rich ``Spinner`` with the per-probe coloured dots inline
while the probes run, then collapses to a plain ``OK (avg ms)`` /
``FAIL`` / ``PARTIAL`` line once the run finishes.

Reference implementation for parametrised plugins. Reuses the shared
probe helpers from :mod:`zboxtui.core.widgets.probes` so this surface
and the Test Network dialog stay in lockstep.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.spinner import Spinner
from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Static

from zboxtui.core.utils.config import get_config
from zboxtui.core.utils.logging import get_logger
from zboxtui.core.widgets import DCUI_DIALOG_CSS, probe_dots, run_probes, summarise

if TYPE_CHECKING:
    from zboxtui.app import ZBoxTUI

MENU_LABEL = "Ping"
MENU_DESCRIPTION = "Ping any host or IP. Defaults to the configured ping target."

_PROBE_COUNT = 3
_SPINNER_REFRESH = 1 / 15

log = get_logger("plugin.ping")


class PingDialog(ModalScreen[None]):
    """Text-input + spinner-with-dots result line."""

    BINDINGS = [
        Binding("escape", "close", "Close", show=False),
        Binding("q", "close", "Close", show=False),
    ]

    DEFAULT_CSS = DCUI_DIALOG_CSS.format(dialog_class="PingDialog", width=55) + """
    PingDialog .form-row {
        height: 1;
        width: 100%;
    }

    PingDialog .form-label {
        width: 13;
        color: $z-fg;
    }

    PingDialog .form-input {
        width: 1fr;
        background: $z-mantle;
        color: $z-panel-fg;
        border: none;
        height: 1;
    }

    PingDialog .form-input:focus {
        background: $z-panel-focus;
    }

    PingDialog #status-row {
        height: 1;
        margin-top: 1;
    }

    PingDialog .status-label {
        width: 13;
        color: $z-fg;
    }

    PingDialog .status-value {
        width: 1fr;
        color: $z-fg;
    }

    PingDialog .status-value.--success {
        color: $z-success;
    }

    PingDialog .status-value.--failure {
        color: $z-error;
    }

    PingDialog .status-value.--pending {
        color: $z-fg-faint;
    }
    """

    def __init__(self, default_target: str) -> None:
        super().__init__()
        self._default_target = default_target

    def compose(self) -> ComposeResult:
        with Container(id="dialog-outer"):
            with Vertical(id="dialog-header"):
                yield Static("")
                yield Static("Ping", id="dialog-title")
                yield Static("")
                yield Static(
                    f"Enter a host or IP and press Enter to send "
                    f"{_PROBE_COUNT} ICMP probes (one per second).",
                    id="dialog-subtitle",
                )
                yield Static("")
            with Vertical(id="dialog-body"):
                with Horizontal(classes="form-row"):
                    yield Static("Target:", classes="form-label")
                    yield Input(
                        value=self._default_target,
                        placeholder="host or IP",
                        classes="form-input",
                        id="target-input",
                    )
                with Horizontal(id="status-row"):
                    yield Static("Result:", classes="status-label")
                    yield Static(
                        "(press Enter to start)",
                        classes="status-value --pending",
                        id="ping-status",
                    )
                yield Static("")
                yield Static("<Enter> Ping    <Esc> Close", id="dialog-footer")

    def on_mount(self) -> None:
        self.query_one("#target-input", Input).focus()

    @on(Input.Submitted, "#target-input")
    def _on_submitted(self, event: Input.Submitted) -> None:  # noqa: ARG002
        self._run_test()

    def _theme_dots(self, results: list[bool | None]) -> Text:
        """Coloured dots prefixed with a space so they sit one column
        clear of the spinner frame."""
        theme = self.app.current_theme
        return Text(" ") + probe_dots(
            results,
            success=(theme.success if theme else None) or "green",
            error=(theme.error if theme else None) or "red",
            faint="grey50",
        )

    def _run_test(self) -> None:
        target = self.query_one("#target-input", Input).value.strip()
        status = self.query_one("#ping-status", Static)
        if not target:
            status.remove_class("--success", "--pending")
            status.add_class("--failure")
            status.update("Target is empty")
            return
        status.remove_class("--success", "--failure")
        status.add_class("--pending")
        # Initial spinner-only state: 3 faint dots so the row reserves
        # space + the operator sees the slots that are about to fill.
        status.update(Spinner("dots", text=self._theme_dots([None] * _PROBE_COUNT)))
        # Rich Spinner needs the inline text re-set per frame to pick
        # up new content; auto_refresh ticks the spinner animation and
        # we'll call status.update() from the worker to refresh dots.
        status.auto_refresh = _SPINNER_REFRESH
        self._do_ping(target)

    @work(exclusive=True)
    async def _do_ping(self, target: str) -> None:
        status = self.query_one("#ping-status", Static)

        def on_probe(results, _latencies):
            # Keep the spinner spinning; refresh the dots beside it.
            status.update(Spinner("dots", text=self._theme_dots(results)))

        results, latencies = await run_probes(target, count=_PROBE_COUNT, on_progress=on_probe)

        # Final state: no spinner, plain text summary.
        ok, message = summarise(results, latencies)
        status.auto_refresh = None
        status.remove_class("--pending")
        status.add_class("--success" if ok else "--failure")
        status.update(message)

    def action_close(self) -> None:
        status = self.query_one("#ping-status", Static)
        status.auto_refresh = None
        self.dismiss(None)


def show_dialog(app: ZBoxTUI) -> None:
    log.info("Opening Ping plugin dialog")
    target = get_config().network_test_default_target or "1.1.1.1"
    app.push_screen(PingDialog(target))

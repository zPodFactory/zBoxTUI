"""Modal that runs a batch of apt-get operations and streams the output.

Shown after the user confirms an install/remove diff from
PackagesDialog. Two visible widgets:

* A textual ProgressBar — total = number of packages to operate on.
  Advances by 1 each time apt's stream emits a "Setting up <pkg>" or
  "Removing <pkg>" line for one of our targets.
* A textual RichLog that shows the full apt-get output, scrolling
  automatically.

Operations are run sequentially in the order returned by
:func:`apt.plan_operations` (removes first, then installs) inside a
Textual ``@work(exclusive=True)`` task so the UI stays responsive.

Closing the dialog is blocked while apt is running.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, ProgressBar, RichLog, Static

from ..utils.apt import (
    AptOperation,
    parse_progress,
    run_streaming,
)
from ..utils.logging import get_logger
from ..utils.privilege import Privilege
from .dcui_dialog import DCUI_DIALOG_CSS

if TYPE_CHECKING:
    from ...app import ZBoxTUI

log = get_logger("apply_dialog")


class ApplyDialog(ModalScreen[bool]):
    """Run apt operations end-to-end with live progress + log.

    Dismisses with ``True`` if every operation exited 0, ``False``
    otherwise. The caller (PackagesDialog) re-queries install state
    after dismissal so the picker reflects what landed.
    """

    app: ZBoxTUI

    BINDINGS = [
        Binding("escape", "close_if_done", "Close", show=False),
        Binding("q", "close_if_done", "Close", show=False),
        Binding("enter", "close_if_done", "Close", show=False),
    ]

    DEFAULT_CSS = DCUI_DIALOG_CSS.format(dialog_class="ApplyDialog", width=92) + """
    ApplyDialog #dialog-outer {
        height: 80%;
    }

    ApplyDialog #dialog-body {
        height: 1fr;
        padding: 1 2;
    }

    ApplyDialog #progress-row {
        height: 1;
        margin-bottom: 1;
    }

    ApplyDialog #progress-label {
        width: 30;
        color: $z-fg;
    }

    ApplyDialog ProgressBar {
        width: 1fr;
        height: 1;
    }

    ApplyDialog ProgressBar > Bar {
        width: 1fr;
    }

    ApplyDialog ProgressBar > Bar > .bar--bar {
        color: $z-accent;
    }

    ApplyDialog #current-pkg {
        height: 1;
        color: $z-fg-dim;
        margin-bottom: 1;
    }

    ApplyDialog RichLog {
        height: 1fr;
        border: round $z-border;
        background: $z-crust;
        color: $z-fg;
    }

    ApplyDialog #summary {
        height: 1;
        text-align: center;
        margin-top: 1;
    }

    ApplyDialog #summary.--success {
        color: $z-success;
    }

    ApplyDialog #summary.--failure {
        color: $z-error;
    }
    """

    def __init__(
        self,
        operations: list[AptOperation],
        privilege: Privilege,
        password: str | None = None,
    ) -> None:
        super().__init__()
        self._operations = operations
        self._privilege = privilege
        self._password = password
        self._total = sum(len(op.packages) for op in operations) or 1
        self._completed = 0
        # Track which packages we expect, so progress events for an
        # unrelated dep don't tick the bar.
        self._expected_targets: set[str] = set()
        for op in operations:
            self._expected_targets.update(op.packages)
        self._seen_targets: set[str] = set()
        self._running = True
        self._success = False

    def compose(self) -> ComposeResult:
        with Container(id="dialog-outer"):
            with Vertical(id="dialog-header"):
                yield Static("")
                yield Static("Applying Changes", id="dialog-title")
                yield Static("")
                yield Static(self._summary_line(), id="dialog-subtitle")
                yield Static("")

            with Vertical(id="dialog-body"):
                with Horizontal(id="progress-row"):
                    yield Label("Overall progress:", id="progress-label")
                    yield ProgressBar(total=self._total, show_eta=False, id="overall-progress")
                yield Static("Starting…", id="current-pkg")
                yield RichLog(highlight=False, markup=False, id="apt-log")
                yield Static("", id="summary")
                yield Static("")
                yield Static(
                    "Apply is running — close disabled until complete.",
                    id="dialog-footer",
                )

    def on_mount(self) -> None:
        self.app.save_debug_screenshot("apply_dialog")
        self._run_all()

    def _summary_line(self) -> str:
        installs = sum(len(op.packages) for op in self._operations if op.kind == "install")
        removes = sum(len(op.packages) for op in self._operations if op.kind == "remove")
        parts = []
        if installs:
            parts.append(f"Installing {installs}")
        if removes:
            parts.append(f"Removing {removes}")
        if not parts:
            return "Nothing to do."
        return " · ".join(parts) + " package" + ("s" if (installs + removes) != 1 else "")

    @work(exclusive=True)
    async def _run_all(self) -> None:
        log_widget = self.query_one("#apt-log", RichLog)
        current = self.query_one("#current-pkg", Static)

        all_ok = True
        for op in self._operations:
            verb = "Removing" if op.kind == "remove" else "Installing"
            log_widget.write(f"=== {verb} {len(op.packages)} package(s) ===")
            current.update(f"{verb} {', '.join(op.packages)}")

            def sink(stream: str, line: str) -> None:
                # stderr goes to the log too — apt routes useful info there.
                log_widget.write(line)
                event = parse_progress(line)
                if (
                    event is not None
                    and event.action in ("setting_up", "removing")
                    and event.package in self._expected_targets
                    and event.package not in self._seen_targets
                ):
                    self._seen_targets.add(event.package)
                    self._completed += 1
                    self.query_one("#overall-progress", ProgressBar).advance(1)
                    current.update(f"Finished {event.package}")

            result = await run_streaming(
                op, self._privilege, password=self._password, sink=sink
            )
            if result.returncode != 0:
                all_ok = False
                log_widget.write(f"=== exit code {result.returncode} ===")
                break

        self._running = False
        self._success = all_ok

        # Finalize the bar at full if everything worked (apt may not have
        # emitted a "Setting up" for every expected target if e.g. nothing
        # actually changed).
        if all_ok:
            bar = self.query_one("#overall-progress", ProgressBar)
            bar.update(progress=self._total)

        summary = self.query_one("#summary", Static)
        if all_ok:
            summary.update("All operations completed successfully. Press Esc/Q/Enter to close.")
            summary.set_classes("--success")
        else:
            summary.update("One or more operations failed. Press Esc/Q/Enter to close.")
            summary.set_classes("--failure")

        footer = self.query_one("#dialog-footer", Static)
        footer.update("<Enter/Esc/Q> Close")

    def action_close_if_done(self) -> None:
        if self._running:
            return
        self.dismiss(self._success)

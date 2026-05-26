"""Modal that runs a batch of apt-get operations with per-package progress.

Shown after the user confirms an install/remove diff from
PackagesDialog. The dialog shows:

* A spinner + status line while apt is running (no overall progress bar).
* One :class:`~textual.widgets.ProgressBar` per package being installed or
  removed, driven by apt's ``Unpacking`` / ``Setting up`` / ``Removing`` output.
* Full apt stdout/stderr is written only to ``zboxtui.log`` for troubleshooting.

Operations run sequentially in the order returned by
:func:`apt.plan_operations` (removes first, then installs) inside a
Textual ``@work(thread=True)`` task so subprocess I/O never blocks or
conflicts with the app's asyncio event loop.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from rich.spinner import Spinner
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import ProgressBar, Static

from ..utils.apt import AptOperation, apt_package_base, parse_progress, run_streaming_sync
from ..utils.catalog_refresh import refresh_catalog
from ..utils.logging import get_logger
from ..utils.privilege import Privilege
from .dcui_dialog import DCUI_DIALOG_CSS

if TYPE_CHECKING:
    from ...app import ZBoxTUI

log = get_logger("apply_dialog")

_SPINNER_REFRESH = 1 / 15
_PKG_ID_RE = re.compile(r"[^a-zA-Z0-9_-]+")

PackageAction = Literal["install", "remove"]
PackagePhase = Literal["pending", "active", "done", "failed"]


@dataclass
class PackageProgress:
    """UI state for one package or workflow task row."""

    name: str
    action: PackageAction
    phase: PackagePhase = "pending"
    percent: int = 0
    label: str | None = None


APT_SOURCES_TASK_ID = "apt-sources"
CATALOG_TASK_ID = "catalog"


def refresh_workflow_rows() -> list[PackageProgress]:
    """Progress rows for the combined APT + catalog refresh workflow."""
    return [
        PackageProgress(
            name=APT_SOURCES_TASK_ID,
            action="install",
            label="Updating APT sources ...",
        ),
        PackageProgress(
            name=CATALOG_TASK_ID,
            action="install",
            label="Updating zBox curated package list ...",
        ),
    ]


def package_rows_from_operations(
    operations: list[AptOperation],
) -> list[PackageProgress]:
    """Build ordered package rows (removes first, then installs)."""
    rows: list[PackageProgress] = []
    for kind in ("remove", "install"):
        for op in operations:
            if op.kind != kind:
                continue
            for name in op.packages:
                rows.append(PackageProgress(name=name, action=kind))
    return rows


def _progress_percent_for_event(action: str) -> int:
    if action == "selecting":
        return 15
    if action == "unpacking":
        return 50
    if action in ("setting_up", "removing"):
        return 100
    return 0


class ApplyDialog(ModalScreen[bool]):
    """Run apt operations with per-package progress bars."""

    app: ZBoxTUI

    BINDINGS = [
        Binding("escape", "close_if_done", "Close", show=False),
        Binding("q", "close_if_done", "Close", show=False),
        Binding("enter", "close_if_done", "Close", show=False),
        Binding("ctrl+c", "force_close", "Force close", show=False),
    ]

    DEFAULT_CSS = DCUI_DIALOG_CSS.format(dialog_class="ApplyDialog", width=72) + """
    ApplyDialog #dialog-outer { height: auto; max-height: 80%; }
    ApplyDialog #dialog-body { height: auto; max-height: 1fr; padding: 1 2; }
    ApplyDialog #overall-status-row {
        height: 1;
        margin-bottom: 1;
    }
    ApplyDialog #overall-spinner {
        width: 1;
        height: 1;
        content-align: left middle;
    }
    ApplyDialog #overall-spinner.--done {
        color: $z-success;
    }
    ApplyDialog #overall-spinner.--failed {
        color: $z-error;
    }
    ApplyDialog #overall-status {
        width: 1fr;
        height: 1;
        color: $z-fg-dim;
        content-align: left middle;
    }
    ApplyDialog #package-list {
        height: auto;
        max-height: 12;
        margin-bottom: 1;
    }
    ApplyDialog #package-list.--hidden {
        display: none;
    }
    ApplyDialog .pkg-row {
        height: 1;
    }
    ApplyDialog .pkg-label {
        width: 1fr;
        height: 1;
        color: $z-fg;
        content-align: left middle;
    }
    ApplyDialog .pkg-bar {
        width: 22;
        height: 1;
    }
    ApplyDialog .pkg-bar Bar > .bar--bar {
        color: $z-title;
        background: $z-mantle;
    }
    ApplyDialog .pkg-bar Bar > .bar--complete {
        color: $z-title;
        background: $z-mantle;
    }
    ApplyDialog #summary { height: auto; text-align: center; margin-top: 1; }
    ApplyDialog #summary.--success { color: $z-success; }
    ApplyDialog #summary.--failure { color: $z-error; }
    """

    def __init__(
        self,
        operations: list[AptOperation],
        privilege: Privilege,
        password: str | None = None,
        *,
        catalog_refresh_url: str | None = None,
    ) -> None:
        super().__init__()
        if privilege == Privilege.SUDO_PASSWORD and password is None:
            raise ValueError(
                "ApplyDialog requires a sudo password when privilege is SUDO_PASSWORD"
            )
        self._operations = operations
        self._privilege = privilege
        self._password = password
        self._catalog_refresh_url = catalog_refresh_url
        self._is_refresh_workflow = catalog_refresh_url is not None
        if self._is_refresh_workflow:
            self._packages = refresh_workflow_rows()
        else:
            self._packages = package_rows_from_operations(operations)
        self._expected_targets = {row.name for row in self._packages}
        self._expected_bases = {apt_package_base(name) for name in self._expected_targets}
        self._is_index_update = any(op.kind == "update" for op in operations)
        # Never use ``_running`` — Textual's MessagePump owns that attribute.
        self._apply_in_progress = True
        self._success = False
        self._pending_lines: list[tuple[str, str, bool]] = []

    def compose(self) -> ComposeResult:
        title = (
            "Refreshing Package List"
            if self._is_refresh_workflow
            else "Applying Changes"
        )
        with Container(id="dialog-outer"):
            with Vertical(id="dialog-header"):
                yield Static("")
                yield Static(title, id="dialog-title")
                yield Static("")
                yield Static(self._summary_line(), id="dialog-subtitle")
                yield Static("")

            with Vertical(id="dialog-body"):
                with Horizontal(id="overall-status-row"):
                    yield Static("", id="overall-spinner")
                    yield Static(" Starting…", id="overall-status")

                with VerticalScroll(id="package-list"):
                    for row in self._packages:
                        label = self._package_label(row)
                        row_id = self._row_id(row.name)
                        row_classes = f"pkg-row --{row.phase}"
                        with Horizontal(classes=row_classes, id=row_id):
                            yield Static(label, classes="pkg-label", id=self._label_id(row.name))
                            yield ProgressBar(
                                total=100,
                                show_eta=False,
                                classes="pkg-bar",
                                id=self._bar_id(row.name),
                            )

                yield Static("", id="summary")

    def on_mount(self) -> None:
        log.info("ApplyDialog mounted (privilege=%s)", self._privilege.name)
        self.app.save_debug_screenshot("apply_dialog")
        package_list = self.query_one("#package-list", VerticalScroll)
        if not self._packages:
            package_list.add_class("--hidden")
        self._start_spinner()
        self.call_later(self._start)

    def _pkg_dom_id(self, name: str) -> str:
        return _PKG_ID_RE.sub("-", name).strip("-") or "pkg"

    def _row_id(self, name: str) -> str:
        return f"pkg-row-{self._pkg_dom_id(name)}"

    def _label_id(self, name: str) -> str:
        return f"pkg-label-{self._pkg_dom_id(name)}"

    def _bar_id(self, name: str) -> str:
        return f"pkg-bar-{self._pkg_dom_id(name)}"

    def _package_label(self, row: PackageProgress) -> str:
        if row.label is not None:
            return row.label
        verb = "Removing" if row.action == "remove" else "Installing"
        return f"{verb} {row.name}"

    def _find_task_row(self, task_id: str) -> PackageProgress | None:
        for row in self._packages:
            if row.name == task_id:
                return row
        return None

    def _set_task_row(
        self,
        task_id: str,
        *,
        phase: PackagePhase,
        percent: int,
    ) -> None:
        row = self._find_task_row(task_id)
        if row is None:
            return
        row.phase = phase
        row.percent = max(row.percent, percent)
        self._update_package_row(row)

    def _start_spinner(self) -> None:
        indicator = self.query_one("#overall-spinner", Static)
        indicator.remove_class("--done", "--failed")
        indicator.update(Spinner("dots"))
        indicator.auto_refresh = _SPINNER_REFRESH

    def _set_overall_indicator(self, *, success: bool) -> None:
        """Replace the spinner with a fixed success/failure mark (keeps row alignment)."""
        indicator = self.query_one("#overall-spinner", Static)
        indicator.auto_refresh = None
        indicator.remove_class("--done", "--failed")
        if success:
            indicator.add_class("--done")
            indicator.update("✓")
        else:
            indicator.add_class("--failed")
            indicator.update("✗")

    def _set_overall_status(self, text: str) -> None:
        self.query_one("#overall-status", Static).update(f" {text}" if text else "")

    def _log_apt_line(self, stream: str, line: str, *, transient: bool = False) -> None:
        suffix = " (live)" if transient else ""
        log.debug("apt [%s]%s: %s", stream, suffix, line)

    def _queue_apt_line(
        self, stream: str, line: str, *, transient: bool = False
    ) -> None:
        self._pending_lines.append((stream, line, transient))
        if len(self._pending_lines) == 1:
            self.set_timer(0.05, self._flush_pending_lines)

    def _find_package_row(self, apt_name: str) -> PackageProgress | None:
        base = apt_package_base(apt_name)
        if base not in self._expected_bases and apt_name not in self._expected_targets:
            return None
        for row in self._packages:
            if row.name == base or row.name == apt_name:
                return row
        return None

    def _update_package_row(self, row: PackageProgress) -> None:
        pkg_row = self.query_one(f"#{self._row_id(row.name)}", Horizontal)
        pkg_row.set_classes(f"pkg-row --{row.phase}")
        self.query_one(f"#{self._label_id(row.name)}", Static).update(
            self._package_label(row)
        )
        bar = self.query_one(f"#{self._bar_id(row.name)}", ProgressBar)
        bar.update(progress=row.percent)

    def _set_operation_phase(
        self,
        op: AptOperation,
        *,
        phase: PackagePhase,
        percent: int,
    ) -> None:
        if op.kind == "update":
            return
        for name in op.packages:
            row = self._find_package_row(name)
            if row is None:
                continue
            row.phase = phase
            row.percent = max(row.percent, percent)
            self._update_package_row(row)

    def _apply_progress_event(self, package: str, action: str) -> None:
        row = self._find_package_row(package)
        if row is None:
            return
        percent = _progress_percent_for_event(action)
        row.phase = "active" if percent < 100 else "done"
        row.percent = max(row.percent, percent)
        self._update_package_row(row)
        # Intermediate install steps still provide useful status sub-text.
        # The completion branch (phase == "done") used to write "Removed X"
        # / "Installed X" here, but that read as flicker: it shows for one
        # frame before the next op's "Removing Y…" header overwrites it.
        # The per-package bar filling to 100% is the actual completion cue.
        if row.phase != "done":
            if action == "unpacking":
                self._set_overall_status(f"Unpacking {row.name}…")
            elif action == "selecting":
                self._set_overall_status(f"Preparing {row.name}…")

    def _flush_pending_lines(self) -> None:
        if not self._pending_lines:
            return
        live_status: str | None = None
        for stream, line, transient in self._pending_lines:
            self._log_apt_line(stream, line, transient=transient)
            event = parse_progress(line)
            if event is not None:
                self._apply_progress_event(event.package, event.action)
            if transient:
                live_status = line
        if live_status is not None and self._is_index_update:
            self._set_overall_status(live_status)
        self._pending_lines.clear()

    def _mark_packages_failed(self) -> None:
        for row in self._packages:
            if row.phase in ("pending", "active"):
                row.phase = "failed"
                self._update_package_row(row)

    def _finish(self, all_ok: bool) -> None:
        self._flush_pending_lines()
        self._apply_in_progress = False
        self._success = all_ok
        self._set_overall_indicator(success=all_ok)
        try:
            if all_ok:
                if self._is_refresh_workflow:
                    self._set_overall_status("Package list refreshed")
                elif self._is_index_update and not self._packages:
                    self._set_overall_status("APT index updated")
                elif self._packages:
                    self._set_overall_status("All packages processed")
            else:
                self._mark_packages_failed()
                self._set_overall_status("One or more operations failed")
            summary = self.query_one("#summary", Static)
            if all_ok:
                summary.update(
                    "All operations completed successfully. Press Esc/Q/Enter to close."
                )
                summary.set_classes("--success")
            else:
                summary.update(
                    "One or more operations failed. See zboxtui.log for details. "
                    "Press Esc/Q/Enter to close."
                )
                summary.set_classes("--failure")
        except Exception:
            log.exception("ApplyDialog finalize failed")

    def _run_refresh_workflow(self) -> bool:
        """Run apt-get update, then fetch the curated catalog."""
        all_ok = True
        update_op = AptOperation(kind="update", packages=())

        self.app.call_from_thread(
            self._set_task_row,
            APT_SOURCES_TASK_ID,
            phase="active",
            percent=10,
        )
        self.app.call_from_thread(
            self._set_overall_status,
            "Updating APT sources ...",
        )

        def on_apt_line(stream: str, line: str, *, transient: bool = False) -> None:
            self.app.call_from_thread(
                self._queue_apt_line, stream, line, transient=transient
            )
            if transient:
                self.app.call_from_thread(
                    self._set_task_row,
                    APT_SOURCES_TASK_ID,
                    phase="active",
                    percent=50,
                )

        apt_result = run_streaming_sync(
            update_op,
            self._privilege,
            password=self._password,
            sink=on_apt_line,
        )
        if apt_result.returncode == 0:
            self.app.call_from_thread(
                self._set_task_row,
                APT_SOURCES_TASK_ID,
                phase="done",
                percent=100,
            )
        else:
            all_ok = False
            self.app.call_from_thread(
                self._set_task_row,
                APT_SOURCES_TASK_ID,
                phase="failed",
                percent=100,
            )
            return all_ok

        if self._catalog_refresh_url is None:
            return all_ok

        self.app.call_from_thread(
            self._set_task_row,
            CATALOG_TASK_ID,
            phase="active",
            percent=10,
        )
        self.app.call_from_thread(
            self._set_overall_status,
            "Updating zBox curated package list ...",
        )
        catalog_result = refresh_catalog(self._catalog_refresh_url)
        if catalog_result.status == "ok":
            self.app.call_from_thread(
                self._set_task_row,
                CATALOG_TASK_ID,
                phase="done",
                percent=100,
            )
        else:
            all_ok = False
            log.error("Catalog refresh failed: %s", catalog_result.message)
            self.app.call_from_thread(
                self._set_task_row,
                CATALOG_TASK_ID,
                phase="failed",
                percent=100,
            )
        return all_ok

    @work(thread=True, group="apply_apt")
    def _start(self) -> None:
        """Run apt in a worker thread — never touch asyncio here."""
        log.info("ApplyDialog worker started")
        all_ok = True

        try:
            if self._is_refresh_workflow:
                all_ok = self._run_refresh_workflow()
            else:
                all_ok = self._run_package_operations()
        except Exception:
            log.exception("ApplyDialog worker crashed")
            all_ok = False
        finally:
            self.app.call_from_thread(self._finish, all_ok)

    def _run_package_operations(self) -> bool:
        all_ok = True
        for op in self._operations:
            verb = (
                "Removing"
                if op.kind == "remove"
                else "Updating" if op.kind == "update" else "Installing"
            )
            pkg_part = f" {', '.join(op.packages)}" if op.packages else ""
            header = f"=== {verb}{pkg_part} ==="
            log.info(header)
            status = (
                f"{verb}…"
                if op.kind == "update"
                else f"{verb} {op.packages[0]}…"
            )
            self.app.call_from_thread(self._set_overall_status, status)
            self.app.call_from_thread(
                self._set_operation_phase,
                op,
                phase="active",
                percent=10,
            )

            def on_line(
                stream: str, line: str, *, transient: bool = False
            ) -> None:
                self.app.call_from_thread(
                    self._queue_apt_line, stream, line, transient=transient
                )

            result = run_streaming_sync(
                op,
                self._privilege,
                password=self._password,
                sink=on_line,
            )
            log.info("=== exit code %d ===", result.returncode)
            if result.returncode == 0 and op.kind != "update":
                self.app.call_from_thread(
                    self._set_operation_phase,
                    op,
                    phase="done",
                    percent=100,
                )
            if result.returncode != 0:
                all_ok = False
                break
        return all_ok

    def _summary_line(self) -> str:
        if self._is_refresh_workflow:
            parts = [
                "Updating APT sources",
                "Refreshing zBox curated package list",
            ]
            if self._privilege == Privilege.SUDO_NOPASSWD:
                parts.append("via passwordless sudo")
            return " · ".join(parts)
        installs = sum(
            len(op.packages) for op in self._operations if op.kind == "install"
        )
        removes = sum(
            len(op.packages) for op in self._operations if op.kind == "remove"
        )
        updates = sum(1 for op in self._operations if op.kind == "update")
        parts = []
        if installs:
            parts.append(
                f"Installing {installs} package{'s' if installs != 1 else ''}"
            )
        if removes:
            parts.append(f"Removing {removes} package{'s' if removes != 1 else ''}")
        if updates:
            parts.append("Updating APT index")
        if self._privilege == Privilege.SUDO_NOPASSWD:
            parts.append("via passwordless sudo")
        return " · ".join(parts) if parts else "Nothing to do."

    def action_close_if_done(self) -> None:
        if self._apply_in_progress:
            return
        self.dismiss(self._success)

    def action_force_close(self) -> None:
        log.warning("ApplyDialog force-closed by user (Ctrl+C)")
        self.dismiss(False)

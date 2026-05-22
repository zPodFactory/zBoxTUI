"""Configure Packages — Phase 1: read-only catalog browser.

Opens a modal listing every curated package grouped by category, with the
*current* install state pulled from ``apt-cache policy``. No toggling, no
apply yet — those land in Phase 2. The dialog header surfaces the catalog
freshness so the user can see whether to refresh (Phase 3 wires the
refresh action).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

from ..utils.logging import get_logger
from ..utils.packages import (
    CatalogError,
    InstallState,
    PackageState,
    format_catalog_freshness,
    format_package_row,
    load_catalog,
    query_catalog_state,
    resolve_catalog_path,
)
from ..widgets.dcui_dialog import DCUI_DIALOG_CSS, MessageDialog

if TYPE_CHECKING:
    from ...app import ZBoxTUI

log = get_logger("menu.packages")

_NAME_WIDTH = 23
_VERSION_WIDTH = 22


class PackagesDialog(ModalScreen[None]):
    """Read-only browser of the curated package catalog."""

    app: ZBoxTUI

    BINDINGS = [
        Binding("escape", "close", "Close", show=False),
        Binding("q", "close", "Close", show=False),
        Binding("enter", "close", "Close", show=False),
    ]

    DEFAULT_CSS = DCUI_DIALOG_CSS.format(dialog_class="PackagesDialog", width=92) + """
    PackagesDialog #dialog-outer {
        height: 80%;
    }

    PackagesDialog #dialog-body {
        height: 1fr;
        padding: 1 2;
    }

    PackagesDialog .pkg-group-header {
        height: 1;
        color: $z-fg-dim;
        text-style: bold;
        margin-top: 1;
    }

    PackagesDialog .pkg-group-header.--first {
        margin-top: 0;
    }

    PackagesDialog .pkg-row {
        height: 1;
        color: $z-fg;
    }

    PackagesDialog .pkg-row.--installed {
        color: $z-fg;
    }

    PackagesDialog .pkg-row.--upgrade {
        color: $z-warning;
    }

    PackagesDialog .pkg-row.--missing {
        color: $z-fg-faint;
    }

    PackagesDialog #freshness {
        height: 1;
        text-align: center;
        color: $z-fg-dim;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._catalog = None
        self._states: dict[str, PackageState] = {}
        self._load_error: str | None = None

        try:
            self._catalog = load_catalog(resolve_catalog_path())
        except CatalogError as exc:
            log.exception("Could not load catalog")
            self._load_error = str(exc)

    def compose(self) -> ComposeResult:
        with Container(id="dialog-outer"):
            with Vertical(id="dialog-header"):
                yield Static("")
                yield Static("Configure Packages", id="dialog-title")
                yield Static("")
                yield Static(self._freshness_text(), id="freshness")
                yield Static("")

            with VerticalScroll(id="dialog-body"):
                if self._load_error is not None:
                    yield Static(f"Could not load the package catalog:\n{self._load_error}")
                    return
                if self._catalog is None:
                    yield Static("No catalog available.")
                    return

                for group_index, group in enumerate(self._catalog.groups):
                    header_classes = "pkg-group-header"
                    if group_index == 0:
                        header_classes += " --first"
                    yield Static(
                        f"[ {group.name} ]",
                        classes=header_classes,
                        markup=False,
                    )
                    for pkg in group.packages:
                        state = self._states.get(
                            pkg.name, PackageState(state=InstallState.NOT_INSTALLED)
                        )
                        row_text = format_package_row(
                            pkg,
                            state,
                            target_checked=state.is_installed,
                            name_width=_NAME_WIDTH,
                            version_width=_VERSION_WIDTH,
                        )
                        yield Static(
                            row_text,
                            classes=f"pkg-row {self._row_class(state)}",
                            markup=False,
                        )

            yield Static("")
            yield Static(
                "<Esc/Q> Close   (read-only — toggle & apply land in Phase 2)",
                id="dialog-footer",
            )

    def on_mount(self) -> None:
        self.app.save_debug_screenshot("packages_dialog")
        # Detect state lazily so the dialog appears quickly; apt-cache policy
        # can take a second or two on a slow disk. The body shows "NOT
        # INSTALLED" for every row until detection lands; one refresh then
        # rewrites them.
        if self._catalog is not None:
            self._refresh_states()

    def _refresh_states(self) -> None:
        if self._catalog is None:
            return
        self._states = query_catalog_state(self._catalog)
        # Rebuild row text in place. The compose() block already laid out
        # the Statics; we walk them via the catalog's iter_packages() order.
        rows = list(self.query(".pkg-row").results(Static))
        for row, pkg in zip(rows, self._catalog.iter_packages(), strict=False):
            state = self._states[pkg.name]
            row.update(
                format_package_row(
                    pkg,
                    state,
                    target_checked=state.is_installed,
                    name_width=_NAME_WIDTH,
                    version_width=_VERSION_WIDTH,
                )
            )
            row.set_classes(f"pkg-row {self._row_class(state)}")

    def _row_class(self, state: PackageState) -> str:
        if state.state == InstallState.UPGRADE_AVAILABLE:
            return "--upgrade"
        if state.state == InstallState.INSTALLED:
            return "--installed"
        return "--missing"

    def _freshness_text(self) -> str:
        if self._catalog is None or self._catalog.updated_at is None:
            return "Last update: unknown"
        return format_catalog_freshness(self._catalog.updated_at, datetime.now(UTC))

    def action_close(self) -> None:
        self.dismiss()


def show_packages_dialog(app: ZBoxTUI) -> None:
    """Open the read-only Configure Packages browser."""
    log.info("Opening Configure Packages dialog")
    try:
        app.push_screen(PackagesDialog())
    except Exception:
        log.exception("Failed to open PackagesDialog; falling back to MessageDialog")
        app.push_screen(
            MessageDialog(
                "Configure Packages",
                "Could not open the packages dialog — see zboxtui.log for details.",
            ),
        )

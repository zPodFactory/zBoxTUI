"""Configure Packages — Phase 1: read-only catalog browser.

Opens a modal listing every curated package grouped by category, with the
*current* install state pulled from ``apt-cache policy``. No toggling, no
apply yet — those land in Phase 2. The dialog header surfaces the catalog
freshness so the user can see whether to refresh (Phase 3 wires the
refresh action).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

from ..utils.logging import get_logger
from ..utils.packages import (
    CatalogError,
    CuratedPackage,
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

_NAME_WIDTH = 25
_VERSION_WIDTH = 12

# Dev/demo: when ZBOXTUI_DEMO_UPGRADES=1 is set, replace the real
# apt state for these packages with a synthetic upgrade so the user
# can visually verify what the green "new version" styling looks like
# without waiting for an actual upgrade to drop. Values are (fake
# installed, fake candidate) — comparison happens on the raw apt
# strings inside _state_from_versions, so candidate ≠ installed is
# all that's required.
_DEMO_UPGRADES: dict[str, tuple[str, str]] = {
    "btop": ("1.3.0-1", "1.3.2-0.1"),
    "docker-ce": ("27.3.1-1", "29.5.2-1"),
    "kubectl": ("1.28.4-1.1", "1.29.0-1.1"),
    "tailscale": ("1.96.0", "1.98.3"),
}


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

    /* Two Statics per package: name line (line 1) + description line
     * (line 2). The .--missing modifier dims both lines together for
     * not-installed packages so they recede visually. The upgrade row
     * paints just the "↑ new" segment in $z-success via inline Rich
     * Text styling (see _success_color()), so we don't need a separate
     * upgrade colour class here. */
    PackagesDialog .pkg-name-row {
        height: 1;
        color: $z-fg;
    }

    PackagesDialog .pkg-desc-row {
        height: 1;
        padding-left: 4;
        color: $z-fg-dim;
        margin-bottom: 1;
    }

    PackagesDialog .pkg-name-row.--missing,
    PackagesDialog .pkg-desc-row.--missing {
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
                        modifier = self._row_class(state)
                        yield Static(
                            self._render_name_line(pkg, state),
                            classes=f"pkg-name-row {modifier}",
                            markup=False,
                        )
                        yield Static(
                            pkg.description,
                            classes=f"pkg-desc-row {modifier}",
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
        self._maybe_inject_demo_upgrades()
        # Rewrite the name lines in place; description lines never change.
        # Both lines share the --missing modifier so they fade together.
        name_rows = list(self.query(".pkg-name-row").results(Static))
        desc_rows = list(self.query(".pkg-desc-row").results(Static))
        for name_row, desc_row, pkg in zip(
            name_rows, desc_rows, self._catalog.iter_packages(), strict=False
        ):
            state = self._states[pkg.name]
            modifier = self._row_class(state)
            name_row.update(self._render_name_line(pkg, state))
            name_row.set_classes(f"pkg-name-row {modifier}")
            desc_row.set_classes(f"pkg-desc-row {modifier}")

    def _maybe_inject_demo_upgrades(self) -> None:
        """If ``ZBOXTUI_DEMO_UPGRADES=1`` is set, overlay synthetic upgrades.

        Lets you see the green "→ new ↑" styling against the live TUI on
        a freshly-updated box where no real upgrades are pending. Has no
        effect when the env var is unset.
        """
        if os.environ.get("ZBOXTUI_DEMO_UPGRADES") not in ("1", "true", "yes"):
            return
        log.info("Demo mode active: injecting synthetic upgrades")
        for name, (installed, candidate) in _DEMO_UPGRADES.items():
            if name in self._states:
                self._states[name] = PackageState(
                    state=InstallState.UPGRADE_AVAILABLE,
                    installed_version=installed,
                    candidate_version=candidate,
                )

    def _render_name_line(self, pkg: CuratedPackage, state: PackageState) -> Text:
        """First-line (checkbox + name + version + optional ↑ new) Rich Text."""
        return format_package_row(
            pkg,
            state,
            target_checked=state.is_installed,
            name_width=_NAME_WIDTH,
            version_width=_VERSION_WIDTH,
            upgrade_style=f"bold {self._success_color()}",
        )

    def _success_color(self) -> str:
        """Hex of the active theme's z-success colour (fallback: 'green')."""
        try:
            return self.app.get_css_variables().get("z-success") or "green"
        except Exception:
            return "green"

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

"""Configure Packages — submenu + interactive picker.

The "Configure Packages" entry on the main menu opens a small submenu
modal with three actions:

* **Select Packages** — opens :class:`PackagesDialog`, the interactive
  picker (cursor + Space-to-toggle + Enter to apply).
* **Refresh Curated List** — fetches the catalog from ``catalog_url``
  (file:// works for local testing) and overwrites the cache so the
  next picker open sees the new content.
* **Update APT Index** — runs ``apt-get update`` via the same
  :class:`ApplyDialog` used for installs/removes.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

from ..utils.apt import AptOperation, plan_operations
from ..utils.catalog_refresh import refresh_catalog
from ..utils.config import get_config
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
    shipped_catalog_path,
)
from ..utils.privilege import Privilege, detect_privilege
from ..widgets.apply_dialog import ApplyDialog
from ..widgets.dcui_dialog import DCUI_DIALOG_CSS, MessageDialog
from ..widgets.dcui_menu import DCUIMenu, MenuItem
from ..widgets.sudo_password_dialog import SudoPasswordDialog

if TYPE_CHECKING:
    from ...app import ZBoxTUI

log = get_logger("menu.packages")

_NAME_WIDTH = 25
_VERSION_WIDTH = 12


class _CursorScroll(VerticalScroll, inherit_bindings=False):
    """A VerticalScroll that doesn't steal arrow keys or take focus.

    Textual's default VerticalScroll grabs up/down/pageup/etc. to scroll
    its viewport. Inside a modal that uses arrow keys for cursor
    navigation, that focus theft means the user's keystrokes move the
    scrollbar instead of the selection. With ``inherit_bindings=False``
    no scroll bindings are inherited, and ``can_focus=False`` keeps
    Textual's auto-focus from latching onto it. The dialog handles
    scrolling explicitly via scroll_visible() whenever the cursor moves.
    """

    can_focus = False

# Dev/demo: ZBOXTUI_DEMO_UPGRADES=1 overlays synthetic upgrades so the
# green "↑ new" styling is visible without waiting for a real upgrade.
_DEMO_UPGRADES: dict[str, tuple[str, str]] = {
    "btop": ("1.3.0-1", "1.3.2-0.1"),
    "docker-ce": ("27.3.1-1", "29.5.2-1"),
    "kubectl": ("1.28.4-1.1", "1.29.0-1.1"),
    "tailscale": ("1.96.0", "1.98.3"),
}


# ===========================================================================
# Submenu
# ===========================================================================


class PackagesSubmenuDialog(ModalScreen[None]):
    """The three-option entry point: Select / Refresh / Update APT."""

    app: ZBoxTUI

    BINDINGS = [
        Binding("escape", "close", "Close", show=False),
        Binding("q", "close", "Close", show=False),
    ]

    DEFAULT_CSS = DCUI_DIALOG_CSS.format(dialog_class="PackagesSubmenuDialog", width=60) + """
    PackagesSubmenuDialog #dialog-body {
        padding: 1 2;
    }
    """

    _ACTION_SELECT = "select"
    _ACTION_REFRESH = "refresh"
    _ACTION_UPDATE = "update"

    def compose(self) -> ComposeResult:
        with Container(id="dialog-outer"):
            with Vertical(id="dialog-header"):
                yield Static("")
                yield Static("Configure Packages", id="dialog-title")
                yield Static("")
                yield Static(
                    "Pick an action — Up/Down to navigate, Enter to choose.",
                    id="dialog-subtitle",
                )
                yield Static("")
            with Vertical(id="dialog-body"):
                yield DCUIMenu(
                    [
                        MenuItem(
                            "Select Packages",
                            "Toggle the curated catalog and apply changes.",
                            self._ACTION_SELECT,
                        ),
                        MenuItem(
                            "Refresh Curated List",
                            "Download the latest catalog from the configured URL.",
                            self._ACTION_REFRESH,
                        ),
                        MenuItem(
                            "Update APT Index",
                            "Run apt-get update to pull the latest package lists.",
                            self._ACTION_UPDATE,
                        ),
                    ],
                    id="submenu",
                )
                yield Static("")
                yield Static("<Enter> Choose    <Esc/Q> Back", id="dialog-footer")

    def on_mount(self) -> None:
        self.app.save_debug_screenshot("packages_submenu")
        self.query_one("#submenu", DCUIMenu).focus()

    @on(DCUIMenu.Selected)
    def on_menu_selected(self, event: DCUIMenu.Selected) -> None:
        action = event.item.action
        if action == self._ACTION_SELECT:
            self.app.push_screen(PackagesDialog())
        elif action == self._ACTION_REFRESH:
            self._do_refresh()
        elif action == self._ACTION_UPDATE:
            self._do_apt_update()

    def _do_refresh(self) -> None:
        url = get_config().catalog_url
        # Empty/unset config → fall back to the shipped catalog so this
        # action stays useful before zPodFactory/zbox-packages goes live.
        if not url:
            url = shipped_catalog_path().as_uri()
            log.info(
                "No catalog_url configured; refreshing from shipped catalog at %s",
                url,
            )
        else:
            log.info("Refreshing catalog from %s", url)
        result = refresh_catalog(url)
        if result.status == "ok":
            title = "Catalog Refreshed"
            body = f"Downloaded the latest catalog from\n{url}\n\nSaved to: {result.path}"
        else:
            title = "Refresh Failed"
            body = result.message
        self.app.push_screen(MessageDialog(title, body))

    def _do_apt_update(self) -> None:
        privilege = detect_privilege()
        if privilege == Privilege.NONE:
            self.app.push_screen(
                MessageDialog(
                    "Cannot Update APT Index",
                    "You need root or sudo access to run apt-get update.\n"
                    "Relaunch zboxtui as root, or add yourself to the sudo group.",
                ),
            )
            return

        op = AptOperation(kind="update", packages=())

        def go(password: str | None = None) -> None:
            self.app.push_screen(ApplyDialog([op], privilege, password=password))

        if privilege == Privilege.SUDO_PASSWORD:
            def handle_password(pw: str | None) -> None:
                if pw is None:
                    return
                go(pw)
            self.app.push_screen(SudoPasswordDialog(), callback=handle_password)
        else:
            go()

    def action_close(self) -> None:
        self.dismiss()


def show_packages_dialog(app: ZBoxTUI) -> None:
    """Open the Configure Packages submenu (the main-menu entry point)."""
    log.info("Opening Configure Packages submenu")
    app.push_screen(PackagesSubmenuDialog())


# ===========================================================================
# Interactive package picker
# ===========================================================================


class PackagesDialog(ModalScreen[None]):
    """Cursor-navigated package picker with toggle + apply.

    Up/Down (and k/j) move the cursor. Space toggles the target state at
    the cursor. Enter computes the install/remove diff vs. the system's
    current state and runs apt via :class:`ApplyDialog`. Esc/Q cancels.
    """

    app: ZBoxTUI

    BINDINGS = [
        Binding("escape", "close", "Close", show=False),
        Binding("q", "close", "Close", show=False),
        Binding("up", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("space", "toggle_pkg", "Toggle", show=False),
        Binding("enter", "apply", "Apply", show=False),
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
        margin-top: 2;
    }

    PackagesDialog .pkg-group-header.--first {
        margin-top: 0;
    }

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

    /* Pending changes: red tint for removes, green for installs. The
     * theme's $z-error / $z-success values are pastel-ish in
     * catppuccin-mocha; on themes with darker error/success the rows
     * still read as distinct from neutral. */
    PackagesDialog .pkg-name-row.--pending-remove,
    PackagesDialog .pkg-desc-row.--pending-remove {
        color: $z-error;
    }

    PackagesDialog .pkg-name-row.--pending-install,
    PackagesDialog .pkg-desc-row.--pending-install {
        color: $z-success;
    }

    /* Cursor highlight wins over state colours but preserves the
     * red/green tint for the foreground so pending changes stay
     * legible when the cursor lands on them. */
    PackagesDialog .pkg-name-row.--cursor,
    PackagesDialog .pkg-desc-row.--cursor {
        background: $z-panel;
        color: $z-panel-fg;
    }

    PackagesDialog .pkg-name-row.--cursor.--missing,
    PackagesDialog .pkg-desc-row.--cursor.--missing {
        color: $z-panel-fg-dim;
    }

    PackagesDialog .pkg-name-row.--cursor.--pending-remove,
    PackagesDialog .pkg-desc-row.--cursor.--pending-remove {
        color: $z-error;
        text-style: bold;
    }

    PackagesDialog .pkg-name-row.--cursor.--pending-install,
    PackagesDialog .pkg-desc-row.--cursor.--pending-install {
        color: $z-success;
        text-style: bold;
    }

    PackagesDialog #freshness {
        height: 1;
        text-align: center;
        color: $z-fg-dim;
    }

    PackagesDialog #status-bar {
        height: 1;
        text-align: center;
        color: $z-fg-dim;
        margin-top: 1;
    }

    PackagesDialog #status-bar.--pending {
        color: $z-accent;
        text-style: bold;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._catalog = None
        self._states: dict[str, PackageState] = {}
        self._targets: dict[str, bool] = {}
        self._cursor = 0
        self._load_error: str | None = None
        self._privilege = detect_privilege()

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

            with _CursorScroll(id="dialog-body"):
                if self._load_error is not None:
                    yield Static(f"Could not load the package catalog:\n{self._load_error}")
                    return
                if self._catalog is None:
                    yield Static("No catalog available.")
                    return

                pkg_index = 0
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
                        modifier = self._row_class(state, state.is_installed, pkg_index)
                        yield Static(
                            self._render_name_line(pkg, state),
                            classes=f"pkg-name-row {modifier}",
                            id=f"pkg-name-{pkg_index}",
                            markup=False,
                        )
                        yield Static(
                            pkg.description,
                            classes=f"pkg-desc-row {modifier}",
                            id=f"pkg-desc-{pkg_index}",
                            markup=False,
                        )
                        pkg_index += 1

            yield Static("", id="status-bar")
            yield Static(
                "<Space> Toggle    <Enter> Apply    <Esc/Q> Close",
                id="dialog-footer",
            )

    def on_mount(self) -> None:
        self.app.save_debug_screenshot("packages_dialog")
        if self._catalog is not None:
            self._refresh_states()

    # ---- state ----------------------------------------------------------

    def _refresh_states(self) -> None:
        if self._catalog is None:
            return
        self._states = query_catalog_state(self._catalog)
        self._maybe_inject_demo_upgrades()
        # Initialize targets from current state (no pending changes).
        for pkg in self._catalog.iter_packages():
            self._targets[pkg.name] = self._states[pkg.name].is_installed
        self._rerender_all()
        self._update_status_bar()

    def _maybe_inject_demo_upgrades(self) -> None:
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

    def _rerender_all(self) -> None:
        if self._catalog is None:
            return
        for pkg_index, pkg in enumerate(self._catalog.iter_packages()):
            self._rerender_row(pkg_index, pkg)

    def _rerender_row(self, pkg_index: int, pkg: CuratedPackage) -> None:
        state = self._states[pkg.name]
        target = self._targets.get(pkg.name, state.is_installed)
        modifier = self._row_class(state, target, pkg_index)
        name_row = self.query_one(f"#pkg-name-{pkg_index}", Static)
        desc_row = self.query_one(f"#pkg-desc-{pkg_index}", Static)
        name_row.update(self._render_name_line(pkg, state, target_override=target))
        name_row.set_classes(f"pkg-name-row {modifier}")
        desc_row.set_classes(f"pkg-desc-row {modifier}")

    def _row_class(self, state: PackageState, target: bool, pkg_index: int) -> str:
        parts = []
        # Pending changes take visual priority over the
        # installed-vs-missing distinction since they're the actionable
        # signal: "this row will change when Apply runs."
        if state.is_installed and not target:
            parts.append("--pending-remove")
        elif not state.is_installed and target:
            parts.append("--pending-install")
        elif not state.is_installed:
            parts.append("--missing")
        if pkg_index == self._cursor:
            parts.append("--cursor")
        return " ".join(parts)

    def _render_name_line(
        self,
        pkg: CuratedPackage,
        state: PackageState,
        *,
        target_override: bool | None = None,
    ) -> Text:
        target = target_override if target_override is not None else state.is_installed
        return format_package_row(
            pkg,
            state,
            target_checked=target,
            name_width=_NAME_WIDTH,
            version_width=_VERSION_WIDTH,
            upgrade_style=f"bold {self._success_color()}",
        )

    def _success_color(self) -> str:
        try:
            return self.app.get_css_variables().get("z-success") or "green"
        except Exception:
            return "green"

    def _freshness_text(self) -> str:
        if self._catalog is None or self._catalog.updated_at is None:
            return "Last update: unknown"
        return format_catalog_freshness(self._catalog.updated_at, datetime.now(UTC))

    # ---- diff + pending status bar -------------------------------------

    def _diff(self) -> tuple[list[str], list[str]]:
        """Return (to_install, to_remove) based on current targets vs states."""
        to_install: list[str] = []
        to_remove: list[str] = []
        if self._catalog is None:
            return to_install, to_remove
        for pkg in self._catalog.iter_packages():
            state = self._states.get(pkg.name)
            if state is None:
                continue
            target = self._targets.get(pkg.name, state.is_installed)
            if target and not state.is_installed:
                to_install.append(pkg.name)
            elif not target and state.is_installed:
                to_remove.append(pkg.name)
        return to_install, to_remove

    def _update_status_bar(self) -> None:
        bar = self.query_one("#status-bar", Static)
        to_install, to_remove = self._diff()
        if not to_install and not to_remove:
            bar.update("No pending changes.")
            bar.set_classes("")
            return
        parts = []
        if to_install:
            parts.append(f"+{len(to_install)} install")
        if to_remove:
            parts.append(f"-{len(to_remove)} remove")
        bar.update(f"Pending: {'  '.join(parts)} — press Enter to apply.")
        bar.set_classes("--pending")

    # ---- navigation -----------------------------------------------------

    def _package_count(self) -> int:
        if self._catalog is None:
            return 0
        return sum(len(g.packages) for g in self._catalog.groups)

    def action_cursor_up(self) -> None:
        if self._cursor > 0:
            self._move_cursor(self._cursor - 1)

    def action_cursor_down(self) -> None:
        if self._cursor < self._package_count() - 1:
            self._move_cursor(self._cursor + 1)

    def _move_cursor(self, new_index: int) -> None:
        if self._catalog is None:
            return
        old = self._cursor
        self._cursor = new_index
        pkgs = list(self._catalog.iter_packages())
        if old < len(pkgs):
            self._rerender_row(old, pkgs[old])
        if new_index < len(pkgs):
            self._rerender_row(new_index, pkgs[new_index])
        # Scroll the new row into view.
        try:
            new_row = self.query_one(f"#pkg-name-{new_index}", Static)
            new_row.scroll_visible(animate=False)
        except Exception:
            pass

    # ---- toggle + apply -------------------------------------------------

    def action_toggle_pkg(self) -> None:
        if self._catalog is None:
            return
        pkgs = list(self._catalog.iter_packages())
        if not pkgs:
            return
        pkg = pkgs[self._cursor]
        # Locked packages can't be un-toggled.
        if pkg.locked and self._targets.get(pkg.name, False):
            return
        self._targets[pkg.name] = not self._targets.get(pkg.name, False)
        self._rerender_row(self._cursor, pkg)
        self._update_status_bar()

    def action_apply(self) -> None:
        to_install, to_remove = self._diff()
        if not to_install and not to_remove:
            self.app.push_screen(
                MessageDialog(
                    "No Changes",
                    "Nothing to install or remove — your selection matches the system.",
                ),
            )
            return

        if self._privilege == Privilege.NONE:
            self.app.push_screen(
                MessageDialog(
                    "Cannot Apply Changes",
                    "You need root or sudo access to install or remove packages.\n"
                    "Relaunch zboxtui as root, or add yourself to the sudo group.",
                ),
            )
            return

        # Confirmation modal listing the diff.
        lines = []
        if to_install:
            lines.append(f"Install: {', '.join(to_install)}")
        if to_remove:
            lines.append(f"Remove: {', '.join(to_remove)}")
        body = "Proceed with the following changes?\n\n" + "\n".join(lines)

        def after_confirm(confirmed: bool | None) -> None:
            if confirmed is not True:
                return
            self._begin_apply(to_install, to_remove)

        self.app.push_screen(
            MessageDialog("Confirm Changes", body),
            callback=after_confirm,
        )

    def _begin_apply(self, to_install: list[str], to_remove: list[str]) -> None:
        operations = plan_operations(install=to_install, remove=to_remove)

        def launch(password: str | None) -> None:
            def handle_apply(_result: bool | None) -> None:
                # Re-query state regardless of success — apt may have done
                # partial work even on failure.
                self._refresh_states()

            self.app.push_screen(
                ApplyDialog(operations, self._privilege, password=password),
                callback=handle_apply,
            )

        if self._privilege == Privilege.SUDO_PASSWORD:
            def handle_pw(pw: str | None) -> None:
                if pw is None:
                    return
                launch(pw)
            self.app.push_screen(SudoPasswordDialog(), callback=handle_pw)
        else:
            launch(None)

    def action_close(self) -> None:
        self.dismiss()

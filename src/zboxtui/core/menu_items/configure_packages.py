"""Configure Packages — submenu + interactive picker.

The "Configure Packages" entry on the main menu opens a small submenu
with two actions:

* **Select Packages** — opens :class:`PackagesDialog`, the interactive
  picker (cursor + Space-to-toggle + Enter to apply).
* **Refresh zBox curated package list** — runs ``apt-get update``, then
  downloads the latest catalog from ``catalog_url`` (``file://`` works
  for local testing), with progress for both steps.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

from ..utils.apt import AptOperation, plan_operations
from ..utils.config import DEFAULT_CATALOG_URL, get_config
from ..utils.logging import get_logger
from ..utils.packages import (
    CatalogError,
    CuratedPackage,
    InstallState,
    PackageChangeSet,
    PackageState,
    compute_package_changes,
    format_catalog_freshness,
    format_package_detail_body,
    format_package_picker_line,
    load_catalog,
    query_catalog_state,
    resolve_catalog_path,
    shipped_catalog_path,
)
from ..utils.privilege import NO_PRIVILEGE_MSG, Privilege, detect_privilege
from ..widgets.apply_dialog import ApplyDialog
from ..widgets.dcui_dialog import DCUI_DIALOG_CSS, MessageDialog
from ..widgets.dcui_menu import DCUIMenu, MenuItem
from ..widgets.sudo_password_dialog import SudoPasswordDialog

if TYPE_CHECKING:
    from ...app import ZBoxTUI

log = get_logger("menu.packages")

_NAME_WIDTH = 20
_VERSION_WIDTH = 18
_DESC_WIDTH = 44

def _push_apply_dialog(
    app: ZBoxTUI,
    operations: list[AptOperation],
    privilege: Privilege,
    *,
    password: str | None = None,
    on_complete=None,
    immediate: bool = False,
    catalog_refresh_url: str | None = None,
) -> None:
    """Push :class:`ApplyDialog`, optionally deferring until after the next refresh."""
    def push() -> None:
        log.info("Opening ApplyDialog (privilege=%s)", privilege.name)
        app.push_screen(
            ApplyDialog(
                operations,
                privilege,
                password=password,
                catalog_refresh_url=catalog_refresh_url,
            ),
            callback=on_complete,
        )

    if immediate:
        push()
    else:
        app.call_after_refresh(push)


def _finish_privileged_launch(
    app: ZBoxTUI,
    operations: list[AptOperation],
    privilege: Privilege,
    *,
    no_privilege_title: str,
    on_complete=None,
    on_abort=None,
    immediate: bool = False,
    catalog_refresh_url: str | None = None,
) -> None:
    log.info("Privileged apply requested; privilege=%s", privilege.name)
    if privilege == Privilege.NONE:
        if on_abort is not None:
            on_abort()
        app.push_screen(MessageDialog(no_privilege_title, NO_PRIVILEGE_MSG))
        return

    def launch(password: str | None) -> None:
        sudo_password = password if privilege == Privilege.SUDO_PASSWORD else None
        _push_apply_dialog(
            app,
            operations,
            privilege,
            password=sudo_password,
            on_complete=on_complete,
            immediate=immediate,
            catalog_refresh_url=catalog_refresh_url,
        )

    if privilege == Privilege.SUDO_PASSWORD:
        cached = app.session_sudo_password
        if cached:
            log.info("Using cached sudo password from this session")
            launch(cached)
            return
        log.info("Prompting for sudo password before apt")

        def handle_password(pw: str | None) -> None:
            if pw is None:
                log.info("Sudo password prompt cancelled")
                if on_abort is not None:
                    on_abort()
                return
            app.remember_sudo_password(pw)
            launch(pw)

        app.push_screen(SudoPasswordDialog(), callback=handle_password)
    else:
        if privilege == Privilege.SUDO_NOPASSWD:
            log.info("Using passwordless sudo — no password dialog needed")
        launch(None)


def _launch_privileged_apply(
    app: ZBoxTUI,
    operations: list[AptOperation],
    *,
    no_privilege_title: str,
    on_complete=None,
    catalog_refresh_url: str | None = None,
) -> None:
    """Detect privilege off the UI thread, then prompt / apply as needed."""
    app.run_worker(
        lambda: app.call_from_thread(
            _finish_privileged_launch,
            app,
            operations,
            detect_privilege(),
            no_privilege_title=no_privilege_title,
            on_complete=on_complete,
            catalog_refresh_url=catalog_refresh_url,
        ),
        thread=True,
        group="packages_privilege",
        exclusive=False,
    )


def _catalog_refresh_url() -> str:
    url = get_config().catalog_url.strip()
    if url:
        return url
    log.info("catalog_url empty; using default catalog at %s", DEFAULT_CATALOG_URL)
    return DEFAULT_CATALOG_URL


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

# Dev/demo: ZBOXTUI_DEMO_UPGRADES=1 overlays synthetic upgrades so pending
# upgrade rows ([↑] + green candidate version) are visible without apt.

def _default_package_target(state: PackageState) -> bool:
    """Pre-check upgrade rows so Enter applies without toggling each one."""
    if state.state == InstallState.UPGRADE_AVAILABLE:
        return True
    return state.is_installed

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
    """The entry point: Select packages or refresh the curated list."""

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
                            "Refresh zBox curated package list",
                            "Update APT sources, then download the latest catalog.",
                            self._ACTION_REFRESH,
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
            self.app.call_after_refresh(lambda: self.app.push_screen(PackagesDialog()))
        elif action == self._ACTION_REFRESH:
            self._do_refresh_package_list()

    def _do_refresh_package_list(self) -> None:
        op = AptOperation(kind="update", packages=())
        _launch_privileged_apply(
            self.app,
            [op],
            catalog_refresh_url=_catalog_refresh_url(),
            no_privilege_title="Cannot Refresh Package List",
        )

    def action_close(self) -> None:
        self.dismiss()


def show_packages_dialog(app: ZBoxTUI) -> None:
    """Open the Configure Packages submenu (the main-menu entry point)."""
    log.info("Opening Configure Packages submenu")
    app.push_screen(PackagesSubmenuDialog())


# ===========================================================================
# Package detail overlay
# ===========================================================================


class PackageDetailDialog(ModalScreen[None]):
    """Scrollable read-only view of a package's full catalog description."""

    app: ZBoxTUI

    BINDINGS = [
        Binding("escape", "close", "Close", show=False),
        Binding("q", "close", "Close", show=False),
        Binding("enter", "close", "Close", show=False),
    ]

    DEFAULT_CSS = DCUI_DIALOG_CSS.format(dialog_class="PackageDetailDialog", width=72) + """
    PackageDetailDialog #detail-text {
        width: 100%;
        height: auto;
        color: $z-fg;
        text-wrap: wrap;
    }
    """

    def __init__(self, pkg_name: str, body: str) -> None:
        super().__init__()
        self._pkg_name = pkg_name
        self._body = body

    def compose(self) -> ComposeResult:
        with Container(id="dialog-outer"):
            with Vertical(id="dialog-header"):
                yield Static("")
                yield Static(self._pkg_name, id="dialog-title")
                yield Static("Package details", id="dialog-subtitle")
                yield Static("")
            with Vertical(id="dialog-body"):
                yield Static(self._body, id="detail-text", markup=False)
                yield Static("")
                yield Static("Press Enter to close", id="dialog-footer")

    def on_mount(self) -> None:
        self.query_one("#detail-text", Static).focus()

    def action_close(self) -> None:
        self.dismiss()


# ===========================================================================
# Interactive package picker
# ===========================================================================


class PackagesDialog(ModalScreen[None]):
    """Cursor-navigated package picker with toggle + apply.

    ↑/↓ (or j/k) move · Space toggles · I details · Enter applies · R resets ·
    PgUp/PgDn jump · categories group related packages.
    """

    app: ZBoxTUI

    _PAGE_JUMP = 5

    BINDINGS = [
        Binding("escape", "close", "Close", show=False),
        Binding("q", "close", "Close", show=False),
        Binding("up", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("pageup", "cursor_page_up", "Page up", show=False),
        Binding("pagedown", "cursor_page_down", "Page down", show=False),
        Binding("home", "cursor_home", "Top", show=False),
        Binding("end", "cursor_end", "Bottom", show=False),
        Binding("space", "toggle_pkg", "Toggle", show=False),
        Binding("i", "show_details", "Details", show=False),
        Binding("r", "reset_pending", "Reset", show=False),
        Binding("enter", "apply", "Apply", show=False),
    ]

    DEFAULT_CSS = DCUI_DIALOG_CSS.format(dialog_class="PackagesDialog", width=92) + """
    PackagesDialog #dialog-outer {
        height: 80%;
    }

    PackagesDialog #dialog-body {
        height: 1fr;
        layout: vertical;
        padding: 0;
    }

    PackagesDialog #package-scroll {
        height: 1fr;
        padding: 1 2;
    }

    PackagesDialog #dialog-footer-section {
        height: auto;
        padding: 0 2 1 2;
        background: $z-bg;
        border-top: solid $z-mantle;
    }

    PackagesDialog #freshness {
        text-align: center;
        color: $z-fg-dim;
    }

    PackagesDialog .pkg-group-header {
        height: 1;
        color: $z-accent;
        text-style: bold;
        margin-top: 1;
    }

    PackagesDialog .pkg-group-header.--first {
        margin-top: 0;
    }

    PackagesDialog .pkg-group-desc {
        height: 1;
        padding-left: 2;
        color: $z-fg-faint;
        margin-bottom: 1;
    }

    PackagesDialog .pkg-row {
        height: 1;
        color: $z-fg;
    }

    PackagesDialog .pkg-row.--missing {
        color: $z-fg-faint;
    }

    /* Pending changes: $z-error for removes, $z-success for installs.
     * Pastel tokens in catppuccin-mocha; darker themes still read clearly. */
    PackagesDialog .pkg-row.--pending-remove {
        color: $z-error;
    }

    PackagesDialog .pkg-row.--pending-install {
        color: $z-success;
    }


    /* Cursor highlight wins over state colours but keeps pending-change
     * foreground tokens legible when the row is selected. */
    PackagesDialog .pkg-row.--cursor {
        background: $z-panel;
        color: $z-panel-fg;
    }

    PackagesDialog .pkg-row.--cursor.--missing {
        color: $z-panel-fg-dim;
    }

    PackagesDialog .pkg-row.--cursor.--pending-remove {
        color: $z-error;
        text-style: bold;
    }

    PackagesDialog .pkg-row.--cursor.--pending-install {
        color: $z-success;
        text-style: bold;
    }


    PackagesDialog #legend {
        height: 1;
        text-align: center;
        color: $z-fg-faint;
    }

    PackagesDialog #dialog-footer {
        margin-top: 1;
    }

    PackagesDialog #apply-overlay {
        display: none;
        height: 1fr;
        text-align: center;
        color: $z-fg-dim;
        content-align: center middle;
    }

    PackagesDialog.--applying #dialog-header,
    PackagesDialog.--applying #package-scroll,
    PackagesDialog.--applying #dialog-footer-section {
        display: none;
    }

    PackagesDialog.--applying #apply-overlay {
        display: block;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._catalog = None
        self._states: dict[str, PackageState] = {}
        self._targets: dict[str, bool] = {}
        self._cursor = 0
        self._load_error: str | None = None
        self._states_ready = False
        self._privilege: Privilege | None = None
        self._privilege_ready = False

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

            with Vertical(id="dialog-body"):
                with _CursorScroll(id="package-scroll"):
                    if self._load_error is not None:
                        yield Static(
                            f"Could not load the package catalog:\n{self._load_error}"
                        )
                    elif self._catalog is None:
                        yield Static("No catalog available.")
                    else:
                        pkg_index = 0
                        for group_index, group in enumerate(self._catalog.groups):
                            header_classes = "pkg-group-header"
                            if group_index == 0:
                                header_classes += " --first"
                            yield Static(
                                f"▸ {group.name}",
                                classes=header_classes,
                                markup=False,
                            )
                            if group.description:
                                yield Static(
                                    group.description,
                                    classes="pkg-group-desc",
                                    markup=False,
                                )
                            for pkg in group.packages:
                                state = self._states.get(
                                    pkg.name, PackageState(state=InstallState.NOT_INSTALLED)
                                )
                                target = self._targets.get(pkg.name, _default_package_target(state))
                                modifier = self._row_class(state, target, pkg_index)
                                yield Static(
                                    self._render_row(pkg, state, target_override=target),
                                    classes=f"pkg-row {modifier}",
                                    id=f"pkg-row-{pkg_index}",
                                    markup=False,
                                )
                                pkg_index += 1

                with Vertical(id="dialog-footer-section"):
                    yield Static(
                        "[+] install  [-] remove  [↑] upgrade  [x] installed",
                        id="legend",
                    )
                    yield Static(
                        "<Space> Toggle  <I> Details  <Enter> Apply  <R> Reset  <Esc/Q> Close",
                        id="dialog-footer",
                    )

                yield Static("Preparing changes…", id="apply-overlay", markup=False)

    def on_mount(self) -> None:
        self.app.save_debug_screenshot("packages_dialog")
        if self._catalog is not None:
            self._refresh_states()
        self._probe_privilege_worker()

    @work(thread=True, group="packages_privilege_probe")
    def _probe_privilege_worker(self) -> None:
        privilege = detect_privilege()
        self.app.call_from_thread(self._apply_probed_privilege, privilege)

    def _apply_probed_privilege(self, privilege: Privilege) -> None:
        self._privilege = privilege
        self._privilege_ready = True

    # ---- state ----------------------------------------------------------

    def _refresh_states(self) -> None:
        """Re-query apt state off the event loop, then repaint."""
        if self._catalog is None:
            return
        self._states_ready = False
        self._refresh_states_worker()

    @work(thread=True, group="packages_state")
    def _refresh_states_worker(self) -> None:
        if self._catalog is None:
            return
        states = query_catalog_state(self._catalog)
        self.app.call_from_thread(self._apply_refreshed_states, states)

    def _apply_refreshed_states(self, states: dict[str, PackageState]) -> None:
        if self._catalog is None:
            return
        self._states = states
        self._states_ready = True
        self._maybe_inject_demo_upgrades()
        # Initialize targets from current state (no pending changes).
        for pkg in self._catalog.iter_packages():
            self._targets[pkg.name] = _default_package_target(self._states[pkg.name])
        self._rerender_all()

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
        state = self._states.get(
            pkg.name, PackageState(state=InstallState.NOT_INSTALLED)
        )
        target = self._targets.get(pkg.name, _default_package_target(state))
        modifier = self._row_class(state, target, pkg_index)
        row = self.query_one(f"#pkg-row-{pkg_index}", Static)
        row.update(self._render_row(pkg, state, target_override=target))
        row.set_classes(f"pkg-row {modifier}")

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

    def _render_row(
        self,
        pkg: CuratedPackage,
        state: PackageState,
        *,
        target_override: bool | None = None,
    ) -> Text:
        target = target_override if target_override is not None else state.is_installed
        return format_package_picker_line(
            pkg,
            state,
            target_checked=target,
            name_width=_NAME_WIDTH,
            version_width=_VERSION_WIDTH,
            desc_width=_DESC_WIDTH,
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

    # ---- diff ----------------------------------------------------------

    def _pending_changes(self) -> PackageChangeSet:
        """Install / remove / upgrade diff from current targets vs apt state."""
        if self._catalog is None:
            return PackageChangeSet()
        return compute_package_changes(
            self._catalog.iter_packages(),
            self._states,
            self._targets,
        )

    # ---- navigation -----------------------------------------------------

    def _package_count(self) -> int:
        if self._catalog is None:
            return 0
        return sum(len(g.packages) for g in self._catalog.groups)

    def _package_at_cursor(self) -> CuratedPackage | None:
        if self._catalog is None:
            return None
        pkgs = list(self._catalog.iter_packages())
        if self._cursor < 0 or self._cursor >= len(pkgs):
            return None
        return pkgs[self._cursor]

    def _group_for_package(self, pkg_name: str) -> tuple[str, str]:
        if self._catalog is None:
            return "", ""
        for group in self._catalog.groups:
            if any(pkg.name == pkg_name for pkg in group.packages):
                return group.name, group.description
        return "", ""

    def action_show_details(self) -> None:
        if not self._states_ready:
            return
        pkg = self._package_at_cursor()
        if pkg is None:
            return
        state = self._states.get(
            pkg.name, PackageState(state=InstallState.NOT_INSTALLED)
        )
        target = self._targets.get(pkg.name, _default_package_target(state))
        group_name, group_description = self._group_for_package(pkg.name)
        body = format_package_detail_body(
            pkg,
            state,
            group_name=group_name,
            group_description=group_description,
            target_checked=target,
        )
        self.app.push_screen(PackageDetailDialog(pkg.name, body))

    def action_cursor_up(self) -> None:
        if self._cursor > 0:
            self._move_cursor(self._cursor - 1)

    def action_cursor_down(self) -> None:
        if self._cursor < self._package_count() - 1:
            self._move_cursor(self._cursor + 1)

    def action_cursor_page_up(self) -> None:
        self._move_cursor(max(0, self._cursor - self._PAGE_JUMP))

    def action_cursor_page_down(self) -> None:
        last = self._package_count() - 1
        self._move_cursor(min(last, self._cursor + self._PAGE_JUMP))

    def action_cursor_home(self) -> None:
        self._move_cursor(0)

    def action_cursor_end(self) -> None:
        last = self._package_count() - 1
        if last >= 0:
            self._move_cursor(last)

    def _move_cursor(self, new_index: int) -> None:
        if self._catalog is None:
            return
        old = self._cursor
        if new_index == old:
            return
        self._cursor = new_index
        pkgs = list(self._catalog.iter_packages())
        if old < len(pkgs):
            self._rerender_row(old, pkgs[old])
        if new_index < len(pkgs):
            self._rerender_row(new_index, pkgs[new_index])
        # Scroll the new row into view.
        try:
            new_row = self.query_one(f"#pkg-row-{new_index}", Static)
            new_row.scroll_visible(animate=False)
        except Exception:
            pass

    # ---- toggle + apply -------------------------------------------------

    def action_toggle_pkg(self) -> None:
        if not self._states_ready:
            return
        if self._catalog is None:
            return
        pkgs = list(self._catalog.iter_packages())
        if not pkgs:
            return
        pkg = pkgs[self._cursor]
        # Locked packages can't be un-toggled.
        if pkg.locked and self._targets.get(pkg.name, False):
            self.app.push_screen(
                MessageDialog(
                    "Package Locked",
                    f"{pkg.name} is marked locked in the catalog and cannot be removed.",
                ),
            )
            return
        self._targets[pkg.name] = not self._targets.get(pkg.name, False)
        self._rerender_row(self._cursor, pkg)

    def action_reset_pending(self) -> None:
        if not self._states_ready or self._catalog is None:
            return
        for pkg in self._catalog.iter_packages():
            self._targets[pkg.name] = _default_package_target(self._states[pkg.name])
        self._rerender_all()

    def action_apply(self) -> None:
        if not self._states_ready:
            self.app.push_screen(
                MessageDialog(
                    "Please Wait",
                    "Still detecting installed package versions.\n"
                    "Try again in a moment.",
                ),
            )
            return

        changes = self._pending_changes()
        if not changes.has_changes:
            self.app.push_screen(
                MessageDialog(
                    "No Changes",
                    "Nothing to install, upgrade, or remove — your selection matches the system.",
                ),
            )
            return

        lines = []
        if changes.to_install:
            lines.append(f"Install: {', '.join(changes.to_install)}")
        if changes.to_upgrade:
            lines.append(f"Upgrade: {', '.join(changes.to_upgrade)}")
        if changes.to_remove:
            lines.append(f"Remove: {', '.join(changes.to_remove)}")
        body = "Proceed with the following changes?\n\n" + "\n".join(lines)

        def after_confirm(confirmed: bool | None) -> None:
            if confirmed is not True:
                return
            self._proceed_with_apply(changes)

        self.app.push_screen(
            MessageDialog(
                "Confirm Changes",
                body,
                before_confirm=self._show_apply_overlay,
            ),
            callback=after_confirm,
        )

    def _show_apply_overlay(self) -> None:
        self.add_class("--applying")

    def _hide_apply_overlay(self) -> None:
        self.remove_class("--applying")

    def _resolve_privilege(self) -> Privilege:
        if self._privilege_ready and self._privilege is not None:
            return self._privilege
        log.info("Privilege probe still running; detecting synchronously")
        privilege = detect_privilege()
        self._privilege = privilege
        self._privilege_ready = True
        return privilege

    def _proceed_with_apply(self, changes: PackageChangeSet) -> None:
        operations = plan_operations(
            install=changes.install_names(),
            remove=list(changes.to_remove),
        )

        def handle_apply(_result: bool | None) -> None:
            self._hide_apply_overlay()
            self._refresh_states()

        def handle_abort() -> None:
            self._hide_apply_overlay()

        _finish_privileged_launch(
            self.app,
            operations,
            self._resolve_privilege(),
            no_privilege_title="Cannot Apply Changes",
            on_complete=handle_apply,
            on_abort=handle_abort,
            immediate=True,
        )

    def action_close(self) -> None:
        self.dismiss()

"""Menu screen - System Customization menu after login."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Static

from ...plugin_loader import PluginMenuItem, discover_plugins
from ..menu_items import MENU_SECTIONS, PLUGINS_SECTION_TITLE
from ..menu_items import CoreMenuItem
from ..widgets.dcui_dialog import AboutDialog
from ..widgets.dcui_menu import DCUIMenu, MenuEntry, MenuGroupHeader, MenuItem

if TYPE_CHECKING:
    from ...app import ZBoxTUI


def build_menu_items() -> tuple[list[MenuEntry], dict[str, Callable[[ZBoxTUI], None]]]:
    """Compose the menu from :data:`MENU_SECTIONS` plus discovered Plugins."""
    items: list[MenuEntry] = []
    handlers: dict[str, Callable[[ZBoxTUI], None]] = {}
    core_i = 0
    plugin_i = 0

    def add_core_entries(section_items: list[CoreMenuItem | None]) -> None:
        nonlocal core_i
        for entry in section_items:
            if entry is None:
                items.append(None)
                continue
            action_id = f"core_{core_i}"
            core_i += 1
            items.append(MenuItem(entry.label, entry.description, action_id))
            handlers[action_id] = entry.handler

    def add_plugin_entries(plugins: list[PluginMenuItem]) -> None:
        nonlocal plugin_i
        for plugin in plugins:
            action_id = f"plugin_{plugin_i}"
            plugin_i += 1
            items.append(MenuItem(plugin.label, plugin.description, action_id))
            handlers[action_id] = plugin.handler

    for section in MENU_SECTIONS:
        if section is None:
            items.append(None)
            continue
        title, section_items = section
        items.append(MenuGroupHeader(title))
        add_core_entries(section_items)

    plugin_items = [p for p in discover_plugins() if p.section == PLUGINS_SECTION_TITLE]
    if plugin_items:
        items.append(MenuGroupHeader(PLUGINS_SECTION_TITLE))
        items.append(None)
        add_plugin_entries(plugin_items)

    return items, handlers


class MenuScreen(Screen):
    """The System Customization menu screen."""

    app: ZBoxTUI

    BINDINGS = [
        Binding("escape", "leave_menu", "Back", show=False),
        Binding("q", "leave_menu", "Back", show=False),
        Binding("f1", "show_about", "Help/About", show=False),
        Binding("f8", "exit_application", "Exit Application", show=False),
    ]

    DEFAULT_CSS = """
    MenuScreen {
        layout: vertical;
        background: $z-bg;
    }

    MenuScreen #menu-header {
        layout: horizontal;
        height: 1;
    }

    MenuScreen #header-left {
        width: 1fr;
        padding: 0 1;
        background: $z-bg;
        color: $z-fg;
        border-top: solid $z-border;
        border-left: solid $z-border;
    }

    MenuScreen #header-right {
        width: 1fr;
        padding: 0 1;
        text-align: right;
        background: $z-panel;
        color: $z-panel-fg;
        border-top: solid $z-border;
        border-right: solid $z-border;
    }

    MenuScreen #menu-body {
        layout: horizontal;
        height: 1fr;
    }

    MenuScreen #menu-list-container {
        width: 1fr;
        layout: vertical;
        background: $z-bg;
        color: $z-fg;
        border-left: solid $z-border;
        border-bottom: solid $z-border;
    }

    MenuScreen #main-menu {
        height: 1fr;
        padding: 1 2;
    }

    MenuScreen #menu-detail-container {
        width: 1fr;
        background: $z-panel;
        color: $z-panel-fg;
        padding: 1 2 0 2;
        border-right: solid $z-border;
        border-bottom: solid $z-border;
    }

    MenuScreen #detail-content {
        height: 1fr;
    }

    MenuScreen #detail-title {
        text-style: bold;
        margin-bottom: 1;
    }

    MenuScreen #detail-description {
        color: $z-panel-fg-dim;
    }

    MenuScreen #menu-footer {
        layout: horizontal;
        height: 1;
        width: 100%;
        background: $z-panel;
        color: $z-panel-fg;
        dock: bottom;
    }

    MenuScreen #footer-left {
        width: 2fr;
    }

    MenuScreen #footer-right {
        width: 1fr;
        text-align: right;
    }
    """

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._current_item: MenuItem | None = None
        self._menu_items, self._handlers = build_menu_items()

    def compose(self) -> ComposeResult:
        first_item: MenuItem | None = next(
            (item for item in self._menu_items if isinstance(item, MenuItem)),
            None,
        )
        first_label = first_item.label if first_item else ""
        first_desc = first_item.description if first_item else ""

        with Horizontal(id="menu-header"):
            yield Static("System Configuration", id="header-left")
            yield Static(first_label, id="header-right")

        with Horizontal(id="menu-body"):
            with Vertical(id="menu-list-container"):
                yield DCUIMenu(self._menu_items, id="main-menu")

            with Vertical(id="menu-detail-container"):
                with Container(id="detail-content"):
                    yield Static(first_label, id="detail-title")
                    yield Static(first_desc, id="detail-description")
                with Horizontal(id="menu-footer"):
                    yield Static(
                        "<F1> Help/Information    <Enter> Change",
                        id="footer-left",
                    )
                    yield Static("<Esc> Log Out", id="footer-right")

    def on_mount(self) -> None:
        self.app.set_menu_handlers(self._handlers)
        self.query_one("#main-menu", DCUIMenu).focus()
        self.app.save_debug_screenshot("menu")

    def action_show_about(self) -> None:
        """Open the About dialog (F1)."""
        self.app.push_screen(AboutDialog())

    @on(DCUIMenu.Highlighted)
    def on_menu_highlighted(self, event: DCUIMenu.Highlighted) -> None:
        self._current_item = event.item

        self.query_one("#header-right", Static).update(event.item.label)
        self.query_one("#detail-title", Static).update(event.item.label)
        self.query_one("#detail-description", Static).update(event.item.description)

    @on(DCUIMenu.Selected)
    def on_menu_selected(self, event: DCUIMenu.Selected) -> None:
        self.app.handle_menu_action(event.item.action)

    def action_exit_application(self) -> None:
        """Exit zBoxTUI (F8) — only available from the authenticated menu."""
        self.app.exit_application()

    def action_leave_menu(self) -> None:
        """Return to the dashboard; menu auth stays valid until it expires."""
        self.app.reload_dashboard()
        self.app.pop_screen()

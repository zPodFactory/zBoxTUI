"""Menu screen - System Customization menu after login."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Static

from ... import __version__
from ...plugin_loader import discover_plugins
from ..menu_items import CORE_MENU_ITEMS
from ..widgets.dcui_menu import DCUIMenu, MenuEntry, MenuGroupHeader, MenuItem

if TYPE_CHECKING:
    from ...app import ZBoxTUI


def build_menu_items() -> tuple[list[MenuEntry], dict[str, Callable[[ZBoxTUI], None]]]:
    """Compose the menu list and the action_id → handler mapping.

    Built-in items render under a "General" group; discovered plugins render
    under a "Plugins" group separated by a blank row.
    """
    items: list[MenuEntry] = []
    handlers: dict[str, Callable[[ZBoxTUI], None]] = {}

    items.append(MenuGroupHeader("General"))
    for i, core_item in enumerate(CORE_MENU_ITEMS):
        if core_item is None:
            # Sentinel for a blank row between sub-groups inside General.
            items.append(None)
            continue
        action_id = f"core_{i}"
        items.append(MenuItem(core_item.label, core_item.description, action_id))
        handlers[action_id] = core_item.handler

    plugins = discover_plugins()
    if plugins:
        items.append(None)
        items.append(MenuGroupHeader("Plugins"))
        for i, plugin in enumerate(plugins):
            action_id = f"plugin_{i}"
            items.append(MenuItem(plugin.label, plugin.description, action_id))
            handlers[action_id] = plugin.handler

    return items, handlers


class MenuScreen(Screen):
    """The System Customization menu screen."""

    app: ZBoxTUI

    BINDINGS = [
        ("escape", "logout", "Log Out"),
        ("q", "logout", "Log Out"),
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
        background: $z-bg;
        color: $z-fg;
        padding: 1 2;
        border-left: solid $z-border;
        border-bottom: solid $z-border;
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
        width: 1fr;
    }

    MenuScreen #footer-center {
        width: 1fr;
        text-align: center;
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
                    yield Static("<Enter> Change", id="footer-left")
                    yield Static(f"zBoxTUI v{__version__}", id="footer-center")
                    yield Static("<Esc> Log Out", id="footer-right")

    def on_mount(self) -> None:
        self.app.set_menu_handlers(self._handlers)
        self.query_one("#main-menu", DCUIMenu).focus()
        self.app.save_debug_screenshot("menu")

    @on(DCUIMenu.Highlighted)
    def on_menu_highlighted(self, event: DCUIMenu.Highlighted) -> None:
        self._current_item = event.item

        self.query_one("#header-right", Static).update(event.item.label)
        self.query_one("#detail-title", Static).update(event.item.label)
        self.query_one("#detail-description", Static).update(event.item.description)

    @on(DCUIMenu.Selected)
    def on_menu_selected(self, event: DCUIMenu.Selected) -> None:
        self.app.handle_menu_action(event.item.action)

    def action_logout(self) -> None:
        self.app.pop_screen()

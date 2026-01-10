"""Menu screen - System Customization menu after login."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Static

from ..widgets.dcui_menu import DCUIMenu, MenuItem

if TYPE_CHECKING:
    from ..app import ZBoxTUI

# Menu items with descriptions
MENU_ITEMS: list[MenuItem | None] = [
    MenuItem(
        "Configure Password",
        "Change the root password for this system.",
        "configure_password",
    ),
    MenuItem(
        "Configure Network",
        "Configure network interfaces, IP addresses, DNS, and routing.",
        "configure_network",
    ),
    MenuItem(
        "Restart Network",
        "Restart all network services and apply configuration changes.",
        "restart_network",
    ),
    MenuItem(
        "Test Network",
        "Test network connectivity by pinging the gateway and DNS servers.",
        "test_network",
    ),
    None,  # Separator
    MenuItem(
        "Configure Keyboard",
        "Change the keyboard layout and input settings.",
        "configure_keyboard",
    ),
    MenuItem(
        "Configure Packages",
        "Install, update, or remove system packages.",
        "configure_packages",
    ),
    None,  # Separator
    MenuItem(
        "View System Logs",
        "View and search through system log files.",
        "view_system_logs",
    ),
    MenuItem(
        "View zBox Logs",
        "View zBox configuration file.",
        "view_zbox_logs",
    ),
    None,  # Separator
    MenuItem(
        "Test Dialog",
        "Display a template dialog for testing modal styling and layout.",
        "test_dialog",
    ),
]


class MenuScreen(Screen):
    """The System Customization menu screen."""

    app: ZBoxTUI

    BINDINGS = [
        ("escape", "logout", "Log Out"),
    ]

    DEFAULT_CSS = """
    MenuScreen {
        layout: vertical;
        background: #5a5a5a;
    }

    MenuScreen #menu-header {
        layout: horizontal;
        height: 1;
    }

    MenuScreen #header-left {
        width: 1fr;
        padding: 0 1;
        background: #ffd700;
        color: black;
        border-top: solid white;
        border-left: solid white;
    }

    MenuScreen #header-right {
        width: 1fr;
        padding: 0 1;
        text-align: right;
        background: #5a5a5a;
        color: white;
        border-top: solid white;
        border-right: solid white;
    }

    MenuScreen #menu-body {
        layout: horizontal;
        height: 1fr;
    }

    MenuScreen #menu-list-container {
        width: 1fr;
        background: #ffd700;
        color: black;
        padding: 1 2;
        border-left: solid white;
        border-bottom: solid white;
    }

    MenuScreen #menu-detail-container {
        width: 1fr;
        background: #5a5a5a;
        color: white;
        padding: 1 2;
        border-right: solid white;
        border-bottom: solid white;
    }

    MenuScreen #detail-content {
        height: 1fr;
    }

    MenuScreen #detail-title {
        text-style: bold;
        margin-bottom: 1;
    }

    MenuScreen #detail-description {
        color: #cccccc;
    }

    MenuScreen #menu-footer {
        layout: horizontal;
        height: 1;
        width: 100%;
        background: #5a5a5a;
        color: white;
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

    def compose(self) -> ComposeResult:
        # Header with screen title and selected item (gray with white border top)
        with Horizontal(id="menu-header"):
            yield Static("System Configuration", id="header-left")
            yield Static("Configure Password", id="header-right")

        # Main body with menu and detail panel
        with Horizontal(id="menu-body"):
            # Left panel - yellow with menu
            with Vertical(id="menu-list-container"):
                yield DCUIMenu(MENU_ITEMS, id="main-menu")

            # Right panel - gray with details and footer
            with Vertical(id="menu-detail-container"):
                with Container(id="detail-content"):
                    yield Static("Configure Password", id="detail-title")
                    yield Static(
                        "Change the root password for this system.",
                        id="detail-description",
                    )
                # Footer keybinds at bottom of right section
                with Horizontal(id="menu-footer"):
                    yield Static("<Enter> Change", id="footer-left")
                    yield Static("zBoxTUI v0.1.0", id="footer-center")
                    yield Static("<Esc> Log Out", id="footer-right")

    def on_mount(self) -> None:
        """Focus the menu on mount and take debug screenshot."""
        self.query_one("#main-menu", DCUIMenu).focus()
        self.app.save_debug_screenshot("menu")

    @on(DCUIMenu.Highlighted)
    def on_menu_highlighted(self, event: DCUIMenu.Highlighted) -> None:
        """Update detail panel when menu item is highlighted."""
        self._current_item = event.item

        # Update header
        header_right = self.query_one("#header-right", Static)
        header_right.update(event.item.label)

        # Update detail panel
        title = self.query_one("#detail-title", Static)
        description = self.query_one("#detail-description", Static)
        title.update(event.item.label)
        description.update(event.item.description)

    @on(DCUIMenu.Selected)
    def on_menu_selected(self, event: DCUIMenu.Selected) -> None:
        """Handle menu item selection."""
        self.app.handle_menu_action(event.item.action)

    def action_logout(self) -> None:
        """Handle ESC - log out and return to dashboard."""
        self.app.pop_screen()

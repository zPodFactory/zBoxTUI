"""Main application class for zBoxTUI."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from textual.app import App

from .core.screens.dashboard import DashboardScreen
from .core.screens.menu import MenuScreen
from .core.utils.logging import get_logger
from .core.utils.system import get_system_info
from .core.widgets.dcui_dialog import LoginDialog, MessageDialog
from .theme import select_palette

log = get_logger("app")


class ZBoxTUI(App):
    """ESXi DCUI-style TUI for Debian system configuration."""

    TITLE = "zBoxTUI"
    CSS_PATH = Path(__file__).parent / "styles.tcss"

    SCREENS = {
        "dashboard": DashboardScreen,
        "menu": MenuScreen,
    }

    def __init__(self, debug_svg: bool = False, palette: str = "auto") -> None:
        # Must be set before super().__init__(), which calls get_css_variables().
        self._palette_name, self._palette = select_palette(palette)
        super().__init__()
        self._authenticated = False
        self.debug_svg = debug_svg
        self._menu_handlers: dict[str, Callable[[ZBoxTUI], None]] = {}
        log.info(
            "zBoxTUI application initialized (debug_svg=%s, palette=%s)",
            debug_svg,
            self._palette_name,
        )

    def get_css_variables(self) -> dict[str, str]:
        """Inject the active palette as CSS variables ($z-bg, $z-accent, ...)."""
        variables = super().get_css_variables()
        variables.update(self._palette)
        return variables

    def save_debug_screenshot(self, name: str) -> None:
        """Save a debug screenshot if debug_svg mode is enabled."""
        if self.debug_svg:
            def _take_screenshot() -> None:
                filename = f"{name}.svg"
                self.save_screenshot(filename, path="./")
                self.log.info(f"Debug screenshot saved: {filename}")
                log.debug("Debug screenshot saved: %s", filename)

            self.call_after_refresh(_take_screenshot)

    def set_menu_handlers(self, handlers: dict[str, Callable[[ZBoxTUI], None]]) -> None:
        """Register action_id → handler mappings (called by MenuScreen on mount)."""
        self._menu_handlers = handlers
        log.debug("Registered %d menu handlers", len(handlers))

    def on_mount(self) -> None:
        """Set up the initial screen."""
        log.info("Application mounted, pushing dashboard screen")
        self.push_screen("dashboard")

    def action_show_login(self) -> None:
        """Show the login dialog."""
        log.debug("action_show_login called (authenticated=%s)", self._authenticated)
        if self._authenticated:
            log.info("User already authenticated, pushing menu screen")
            self.push_screen("menu")
        else:
            info = get_system_info()
            log.info("Showing login dialog for host: %s", info.hostname)
            self.push_screen(
                LoginDialog(hostname=info.hostname),
                callback=self._handle_login,
            )

    def _handle_login(self, result: tuple[str, str] | None) -> None:
        """Handle login dialog result."""
        if result is None:
            log.debug("Login dialog cancelled by user")
            return

        username, password = result
        log.debug("Login attempt for user: %s", username)
        if username and password:
            self._authenticated = True
            log.info("User '%s' authenticated successfully", username)
            self.push_screen("menu")
        else:
            log.warning("Authentication failed: empty username or password")
            self.push_screen(
                MessageDialog(
                    "Authentication Failed",
                    "Please enter both username and password.",
                ),
            )

    def action_show_shutdown(self) -> None:
        """Show the shutdown confirmation dialog."""
        log.info("Showing shutdown dialog")
        self.push_screen(
            MessageDialog(
                "Shut Down / Restart",
                "This would shut down or restart the system.\n\nFeature not yet implemented.",
            ),
        )

    def handle_menu_action(self, action: str) -> None:
        """Dispatch a menu action_id to its registered handler."""
        log.info("Menu action triggered: %s", action)

        handler = self._menu_handlers.get(action)
        if handler is not None:
            log.debug("Executing handler for action: %s", action)
            handler(self)
            return

        log.warning("No handler found for action: %s", action)
        self.push_screen(
            MessageDialog(
                "Not Implemented",
                f"The action '{action}' is not yet implemented.",
            ),
        )

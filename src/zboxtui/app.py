"""Main application class for zBoxTUI."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from textual.app import App

from .core.screens.dashboard import DashboardScreen
from .core.screens.menu import MenuScreen
from .core.themes import DEFAULT_THEME_NAME, all_themes
from .core.utils.config import get_config
from .core.utils.logging import get_logger
from .core.utils.system import get_system_info
from .core.widgets.dcui_dialog import LoginDialog, MessageDialog

log = get_logger("app")


class ZBoxTUI(App):
    """ESXi DCUI-style TUI for Debian system configuration."""

    TITLE = "zBoxTUI"
    CSS_PATH = Path(__file__).parent / "styles.tcss"

    SCREENS = {
        "dashboard": DashboardScreen,
        "menu": MenuScreen,
    }

    def __init__(self, debug_svg: bool = False, theme_override: str | None = None) -> None:
        super().__init__()
        self._authenticated = False
        self._session_sudo_password: str | None = None
        self.debug_svg = debug_svg
        self._menu_handlers: dict[str, Callable[[ZBoxTUI], None]] = {}

        # Themes must be registered before any CSS is parsed — otherwise
        # references to $z-bg and friends in styles.tcss/DEFAULT_CSS resolve
        # against Textual's built-in themes only and fail.
        for theme in all_themes():
            self.register_theme(theme)

        configured = theme_override or get_config().theme
        try:
            self.theme = configured
            log.info("Theme applied: %s", configured)
        except Exception:
            log.exception(
                "Unknown theme '%s', falling back to '%s'", configured, DEFAULT_THEME_NAME
            )
            self.theme = DEFAULT_THEME_NAME

        log.info(
            "zBoxTUI application initialized (debug_svg=%s, theme=%s)",
            debug_svg,
            self.theme,
        )

    def on_mount(self) -> None:
        """Push the dashboard once the app is ready."""
        log.info("Application mounted, pushing dashboard screen")
        self.push_screen("dashboard")

    def save_debug_screenshot(self, name: str) -> None:
        """Save an SVG screenshot if --debug-svg was passed."""
        if not self.debug_svg:
            return

        def _take_screenshot() -> None:
            filename = f"{name}.svg"
            self.save_screenshot(filename, path="./")
            log.debug("Debug screenshot saved: %s", filename)

        self.call_after_refresh(_take_screenshot)

    @property
    def session_sudo_password(self) -> str | None:
        """Validated sudo password for this process, or ``None`` if not entered yet."""
        return self._session_sudo_password

    def remember_sudo_password(self, password: str) -> None:
        """Cache the sudo password for the lifetime of this zBoxTUI session."""
        self._session_sudo_password = password
        log.debug("Cached sudo password for this session")

    def clear_sudo_password(self) -> None:
        """Drop the cached sudo password."""
        self._session_sudo_password = None

    def set_menu_handlers(self, handlers: dict[str, Callable[[ZBoxTUI], None]]) -> None:
        """Register action_id → handler mappings (called by MenuScreen on mount)."""
        self._menu_handlers = handlers
        log.debug("Registered %d menu handlers", len(handlers))

    def action_show_login(self) -> None:
        """Show the login dialog, or skip to the menu if already authenticated."""
        log.debug("action_show_login called (authenticated=%s)", self._authenticated)
        if self._authenticated:
            log.info("User already authenticated, pushing menu screen")
            self.push_screen("menu")
            return

        info = get_system_info()
        log.info("Showing login dialog for host: %s", info.hostname)
        self.push_screen(
            LoginDialog(hostname=info.hostname),
            callback=self._handle_login,
        )

    def _handle_login(self, result: bool | None) -> None:
        """LoginDialog already validated; just gate access to the menu."""
        if result is None:
            log.debug("Login dialog cancelled by user")
            return
        if result is True:
            self._authenticated = True
            log.info("Root authenticated successfully")
            self.push_screen("menu")

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

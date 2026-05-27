"""Main application class for zBoxTUI."""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from pathlib import Path

from textual.app import App
from textual.binding import Binding

from .core.widgets.reboot_flow import run_confirmed_reboot
from .core.screens.dashboard import DashboardScreen
from .core.screens.menu import MenuScreen
from .core.themes import DEFAULT_THEME_NAME, all_themes
from .core.utils.config import get_config
from .core.utils.logging import get_logger
from .core.utils.system import get_system_info
from .core.utils.privilege import sudo_timestamp_valid
from .core.widgets.dcui_dialog import LoginDialog

log = get_logger("app")

# Match default sudo timestamp_timeout (minutes) on Debian.
AUTH_SESSION_SECONDS = 15 * 60



def _quit_allowed() -> bool:
    return os.environ.get("ZBOXTUI_ALLOW_QUIT", "").lower() in ("1", "true", "yes")


# Override Textual App defaults (ctrl+c → help_quit, ctrl+q → quit). Must be on the
# class — instance assignment in __init__ does not affect _merge_bindings().
_PRODUCTION_QUIT_LOCK_BINDINGS = [
    Binding("ctrl+q", "noop", show=False, priority=True),
    Binding("ctrl+c", "noop", show=False, priority=True, system=True),
]


class ZBoxTUI(App):
    """DCUI-style TUI for Debian (ESXi / XCP-ng xsconsole-inspired; see TRADEMARKS.md)."""

    TITLE = "zBoxTUI"
    CSS_PATH = Path(__file__).parent / "styles.tcss"

    BINDINGS = list(_PRODUCTION_QUIT_LOCK_BINDINGS)

    SCREENS = {
        "dashboard": DashboardScreen,
        "menu": MenuScreen,
    }

    def __init__(self, debug_svg: bool = False, theme_override: str | None = None) -> None:
        type(self).BINDINGS = (
            [] if _quit_allowed() else list(_PRODUCTION_QUIT_LOCK_BINDINGS)
        )
        type(self)._merged_bindings = type(self)._merge_bindings()
        super().__init__()
        self._authenticated = False
        self._auth_expires_at: float | None = None
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

    def is_authenticated(self) -> bool:
        """True while the F2 menu session is valid (timer, or sudo timestamp after login)."""
        if not self._authenticated:
            return False
        if self._auth_expires_at is not None and time.monotonic() >= self._auth_expires_at:
            if sudo_timestamp_valid():
                self._extend_auth_session()
                log.debug("Menu session extended via active sudo timestamp")
                return True
            self.logout()
            return False
        return True

    def grant_authenticated(self) -> None:
        """Mark the operator as logged in for the menu (F2 / F12 gate)."""
        self._authenticated = True
        self._extend_auth_session()
        log.info(
            "Menu authentication granted (%d minute session)",
            AUTH_SESSION_SECONDS // 60,
        )

    def _extend_auth_session(self) -> None:
        self._auth_expires_at = time.monotonic() + AUTH_SESSION_SECONDS

    def remember_sudo_password(self, password: str) -> None:
        """Cache the sudo password for apt and extend the menu auth timer."""
        self._session_sudo_password = password
        if self._authenticated:
            self._extend_auth_session()
        log.debug("Cached sudo password for this session")

    def clear_sudo_password(self) -> None:
        """Drop the cached sudo password."""
        self._session_sudo_password = None

    def logout(self) -> None:
        """Clear menu authentication and cached sudo password."""
        self._authenticated = False
        self._auth_expires_at = None
        self.clear_sudo_password()
        log.info("Session logged out; authentication cleared")

    def action_noop(self) -> None:
        """Ignore keys reserved for quit in production console mode."""

    def action_help_quit(self) -> None:
        """Suppress Textual's ctrl+c → 'Press ctrl+q to quit' hint in production."""
        if _quit_allowed():
            super().action_help_quit()

    async def action_quit(self) -> None:
        """Quit only when explicitly allowed (development)."""
        if _quit_allowed():
            await super().action_quit()

    def exit_application(self) -> None:
        """Exit the process after menu login (F8); bypasses global quit lock."""
        if not self.is_authenticated():
            log.warning("Application exit refused: login required (F2)")
            return
        log.info("Application exit requested from menu (F8)")
        self.exit()

    def set_menu_handlers(self, handlers: dict[str, Callable[[ZBoxTUI], None]]) -> None:
        """Register action_id → handler mappings (called by MenuScreen on mount)."""
        self._menu_handlers = handlers
        log.debug("Registered %d menu handlers", len(handlers))

    def reload_dashboard(self) -> None:
        """Re-read config and system info into the dashboard screen.

        Refreshes hostname, network interfaces, layout toggles, and live
        stat timers after settings, hostname, or network changes.
        """
        for screen in self.screen_stack:
            if isinstance(screen, DashboardScreen):
                log.info("Reloading dashboard from updated config")
                screen.reload_from_config()
                return
        log.debug("reload_dashboard called but no DashboardScreen on the stack")

    def action_show_login(self) -> None:
        """Show the login dialog, or skip to the menu if already authenticated."""
        log.debug("action_show_login called (authenticated=%s)", self.is_authenticated())
        if self.is_authenticated():
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
            self.grant_authenticated()
            log.info("Root authenticated successfully")
            self.push_screen("menu")

    def action_show_reboot(self) -> None:
        """Reboot the system after operator confirmation (F12)."""
        log.info("Showing reboot confirmation")
        run_confirmed_reboot(self)

    def handle_menu_action(self, action: str) -> None:
        """Dispatch a menu action_id to its registered handler."""
        log.info("Menu action triggered: %s", action)

        handler = self._menu_handlers.get(action)
        if handler is not None:
            log.debug("Executing handler for action: %s", action)
            handler(self)
            return

        log.warning("No handler found for action: %s", action)
        from .core.widgets.dcui_dialog import MessageDialog

        self.push_screen(
            MessageDialog(
                "Not Implemented",
                f"The action '{action}' is not yet implemented.",
            ),
        )

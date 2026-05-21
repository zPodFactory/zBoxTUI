"""Main application class for zBoxTUI."""

from pathlib import Path

from textual.app import App

from .screens.dashboard import DashboardScreen
from .screens.menu import MenuScreen
from .theme import select_palette
from .utils.logging import get_logger
from .utils.system import get_system_info
from .widgets.dcui_dialog import (
    LoginDialog,
    MessageDialog,
    NetworkConfigDialog,
    NetworkInterfaceDialog,
    NetworkTestDialog,
    PasswordDialog,
    SystemLogsDialog,
    SystemStatsDialog,
    TestDialog,
    ZBoxLogsDialog,
)

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
            # Use call_after_refresh to ensure UI is fully rendered
            def _take_screenshot() -> None:
                filename = f"{name}.svg"
                self.save_screenshot(filename, path="./")
                self.log.info(f"Debug screenshot saved: {filename}")
                log.debug("Debug screenshot saved: %s", filename)

            self.call_after_refresh(_take_screenshot)

    def on_mount(self) -> None:
        """Set up the initial screen."""
        log.info("Application mounted, pushing dashboard screen")
        self.push_screen("dashboard")

    def action_show_login(self) -> None:
        """Show the login dialog."""
        log.debug("action_show_login called (authenticated=%s)", self._authenticated)
        if self._authenticated:
            # Already authenticated, go directly to menu
            log.info("User already authenticated, pushing menu screen")
            self.push_screen("menu")
        else:
            # Show login dialog
            info = get_system_info()
            log.info("Showing login dialog for host: %s", info.hostname)
            self.push_screen(
                LoginDialog(hostname=info.hostname),
                callback=self._handle_login,
            )

    def _handle_login(self, result: tuple[str, str] | None) -> None:
        """Handle login dialog result."""
        if result is not None:
            username, password = result
            log.debug("Login attempt for user: %s", username)
            # For now, accept any non-empty credentials
            # In a real app, this would validate against PAM or similar
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
        else:
            log.debug("Login dialog cancelled by user")

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
        """Handle a menu action."""
        log.info("Menu action triggered: %s", action)
        # Map actions to handlers
        handlers = {
            "configure_password": self._show_password_dialog,
            "configure_network": self._show_network_dialog,
            "restart_network": self._show_restart_network_dialog,
            "test_network": self._show_test_network,
            "configure_packages": self._show_packages_dialog,
            "view_system_logs": self._show_system_logs,
            "view_zbox_logs": self._show_zbox_logs,
            "view_system_stats": self._show_system_stats,
            "test_dialog": self._show_test_dialog,
        }

        handler = handlers.get(action)
        if handler:
            log.debug("Executing handler for action: %s", action)
            handler()
        else:
            log.warning("No handler found for action: %s", action)
            self.push_screen(
                MessageDialog(
                    "Not Implemented",
                    f"The action '{action}' is not yet implemented.",
                ),
            )

    def _show_password_dialog(self) -> None:
        """Show password configuration dialog."""
        log.info("Opening Configure Password dialog")
        self.push_screen(PasswordDialog())

    def _show_network_dialog(self) -> None:
        """Show network configuration dialog."""
        log.info("Opening Configure Network dialog")
        self.push_screen(
            NetworkInterfaceDialog(),
            callback=self._handle_interface_selection,
        )

    def _handle_interface_selection(self, interface_name: str | None) -> None:
        """Handle interface selection result."""
        if interface_name is None:
            log.debug("Interface selection cancelled")
            return
        log.info("Interface selected: %s, opening config dialog", interface_name)
        self.push_screen(
            NetworkConfigDialog(interface_name),
        )

    def _show_restart_network_dialog(self) -> None:
        """Show restart network confirmation."""
        log.info("Opening Restart Network dialog (not implemented)")
        self.push_screen(
            MessageDialog(
                "Restart Network",
                "This will restart all network services.\n\n"
                "Feature not yet implemented.",
            ),
        )

    def _show_test_network(self) -> None:
        """Show network connectivity test dialog."""
        log.info("Opening Test Network dialog")
        self.push_screen(NetworkTestDialog())

    def _show_packages_dialog(self) -> None:
        """Show package management dialog."""
        log.info("Opening Configure Packages dialog (not implemented)")
        self.push_screen(
            MessageDialog(
                "Configure Packages",
                "Package management will be implemented here.\n\n"
                "This will allow:\n"
                "- Installing packages\n"
                "- Updating packages\n"
                "- Removing packages",
            ),
        )

    def _show_system_logs(self) -> None:
        """Show system logs viewer."""
        log.info("Opening System Logs viewer")
        self.push_screen(SystemLogsDialog())

    def _show_zbox_logs(self) -> None:
        """Show zBox configuration viewer."""
        log.info("Opening zBox Logs viewer")
        self.push_screen(ZBoxLogsDialog())

    def _show_system_stats(self) -> None:
        """Show the live system metrics panel."""
        log.info("Opening System Stats dialog")
        self.push_screen(SystemStatsDialog())

    def _show_test_dialog(self) -> None:
        """Show test dialog for modal template demonstration."""
        log.info("Opening Test Dialog")
        self.push_screen(TestDialog())

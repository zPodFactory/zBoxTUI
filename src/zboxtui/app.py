"""Main application class for zBoxTUI."""

from pathlib import Path

from textual.app import App

from .screens.dashboard import DashboardScreen
from .screens.menu import MenuScreen
from .utils.system import get_system_info
from .widgets.dcui_dialog import (
    LoginDialog,
    MessageDialog,
    NetworkTestDialog,
    SystemLogsDialog,
    TestDialog,
    ZBoxLogsDialog,
)


class ZBoxTUI(App):
    """ESXi DCUI-style TUI for Debian system configuration."""

    TITLE = "zBoxTUI"
    CSS_PATH = Path(__file__).parent / "styles.tcss"

    SCREENS = {
        "dashboard": DashboardScreen,
        "menu": MenuScreen,
    }

    def __init__(self, debug_svg: bool = False) -> None:
        super().__init__()
        self._authenticated = False
        self.debug_svg = debug_svg

    def save_debug_screenshot(self, name: str) -> None:
        """Save a debug screenshot if debug_svg mode is enabled."""
        if self.debug_svg:
            # Use call_after_refresh to ensure UI is fully rendered
            def _take_screenshot() -> None:
                filename = f"{name}.svg"
                self.save_screenshot(filename, path="./")
                self.log.info(f"Debug screenshot saved: {filename}")

            self.call_after_refresh(_take_screenshot)

    def on_mount(self) -> None:
        """Set up the initial screen."""
        self.push_screen("dashboard")

    def action_show_login(self) -> None:
        """Show the login dialog."""
        if self._authenticated:
            # Already authenticated, go directly to menu
            self.push_screen("menu")
        else:
            # Show login dialog
            info = get_system_info()
            self.push_screen(
                LoginDialog(hostname=info.hostname),
                callback=self._handle_login,
            )

    def _handle_login(self, result: tuple[str, str] | None) -> None:
        """Handle login dialog result."""
        if result is not None:
            username, password = result
            # For now, accept any non-empty credentials
            # In a real app, this would validate against PAM or similar
            if username and password:
                self._authenticated = True
                self.push_screen("menu")
            else:
                self.push_screen(
                    MessageDialog(
                        "Authentication Failed",
                        "Please enter both username and password.",
                    ),
                )

    def action_show_shutdown(self) -> None:
        """Show the shutdown confirmation dialog."""
        self.push_screen(
            MessageDialog(
                "Shut Down / Restart",
                "This would shut down or restart the system.\n\nFeature not yet implemented.",
            ),
        )

    def handle_menu_action(self, action: str) -> None:
        """Handle a menu action."""
        # Map actions to handlers
        handlers = {
            "configure_password": self._show_password_dialog,
            "configure_network": self._show_network_dialog,
            "restart_network": self._show_restart_network_dialog,
            "test_network": self._show_test_network,
            "configure_keyboard": self._show_keyboard_dialog,
            "configure_packages": self._show_packages_dialog,
            "view_system_logs": self._show_system_logs,
            "view_zbox_logs": self._show_zbox_logs,
            "test_dialog": self._show_test_dialog,
        }

        handler = handlers.get(action)
        if handler:
            handler()
        else:
            self.push_screen(
                MessageDialog(
                    "Not Implemented",
                    f"The action '{action}' is not yet implemented.",
                ),
            )

    def _show_password_dialog(self) -> None:
        """Show password configuration dialog."""
        self.push_screen(
            MessageDialog(
                "Configure Password",
                "Password configuration will be implemented here.\n\n"
                "This will allow changing the root password.",
            ),
        )

    def _show_network_dialog(self) -> None:
        """Show network configuration dialog."""
        self.push_screen(
            MessageDialog(
                "Configure Network",
                "Network configuration will be implemented here.\n\n"
                "This will allow configuring:\n"
                "- Network adapters\n"
                "- IP addresses (DHCP/Static)\n"
                "- DNS settings\n"
                "- Default gateway",
            ),
        )

    def _show_restart_network_dialog(self) -> None:
        """Show restart network confirmation."""
        self.push_screen(
            MessageDialog(
                "Restart Network",
                "This will restart all network services.\n\n"
                "Feature not yet implemented.",
            ),
        )

    def _show_test_network(self) -> None:
        """Show network connectivity test dialog."""
        self.push_screen(NetworkTestDialog())

    def _show_keyboard_dialog(self) -> None:
        """Show keyboard configuration dialog."""
        self.push_screen(
            MessageDialog(
                "Configure Keyboard",
                "Keyboard configuration will be implemented here.\n\n"
                "This will allow changing the keyboard layout.",
            ),
        )

    def _show_packages_dialog(self) -> None:
        """Show package management dialog."""
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
        self.push_screen(SystemLogsDialog())

    def _show_zbox_logs(self) -> None:
        """Show zBox configuration viewer."""
        self.push_screen(ZBoxLogsDialog())

    def _show_test_dialog(self) -> None:
        """Show test dialog for modal template demonstration."""
        self.push_screen(TestDialog())

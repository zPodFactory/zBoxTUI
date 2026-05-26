"""
UI Screenshot Tests for zBoxTUI.

This module contains tests that simulate user interactions and capture
SVG screenshots for visual verification of all screens and dialogs.

Run with: uv run pytest tests/test_ui_screenshots.py -v
Screenshots are saved to: tests/screenshots/
"""

import asyncio
from pathlib import Path

import pytest

from zboxtui.app import ZBoxTUI
from zboxtui.core.widgets.dcui_dialog import (
    LoginDialog,
    MessageDialog,
    NetworkTestDialog,
    TestDialog,
)

# Screenshot output directory
SCREENSHOT_DIR = Path(__file__).parent / "screenshots"


@pytest.fixture(autouse=True)
def setup_screenshot_dir():
    """Ensure screenshot directory exists."""
    SCREENSHOT_DIR.mkdir(exist_ok=True)
    yield


@pytest.fixture(autouse=True)
def stub_pam_auth(monkeypatch):
    """All UI tests that go through the login dialog need PAM stubbed.

    Real ``verify_root_password`` shells out to ``su -c true root`` —
    that depends on the host actually having root password ``test``,
    which neither CI nor any sane dev box does. Stub it module-wide so
    the menu navigation tests aren't quietly screenshotting the login
    dialog.
    """
    import zboxtui.core.widgets.dcui_dialog as dcui_dialog

    monkeypatch.setattr(dcui_dialog, "verify_root_password", lambda _pw: True)


def save_screenshot(app: ZBoxTUI, name: str) -> Path:
    """Save a screenshot to the tests/screenshots directory."""
    filepath = SCREENSHOT_DIR / f"{name}.svg"
    app.save_screenshot(str(filepath))
    return filepath


class TestDashboardScreen:
    """Tests for the main dashboard screen."""

    @pytest.mark.asyncio
    async def test_dashboard_initial_view(self):
        """Test dashboard displays correctly on startup."""
        app = ZBoxTUI()
        async with app.run_test(size=(100, 30)):
            await asyncio.sleep(0.2)
            save_screenshot(app, "01_dashboard_initial")

            # Verify dashboard is showing
            assert app.screen.__class__.__name__ == "DashboardScreen"

    @pytest.mark.asyncio
    async def test_dashboard_f12_shutdown_dialog(self):
        """Test F12 opens shutdown/restart dialog."""
        app = ZBoxTUI()
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.press("f12")
            await asyncio.sleep(0.2)
            save_screenshot(app, "02_dashboard_f12_shutdown_dialog")


class TestLoginDialog:
    """Tests for the login dialog."""

    @pytest.mark.asyncio
    async def test_login_dialog_open(self):
        """Test F2 opens login dialog."""
        app = ZBoxTUI()
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.press("f2")
            await asyncio.sleep(0.2)
            save_screenshot(app, "03_login_dialog_open")

            # Verify login dialog is showing
            assert len(app.screen_stack) > 1

    @pytest.mark.asyncio
    async def test_login_dialog_focus_username(self):
        """Test login dialog with username field focused."""
        app = ZBoxTUI()
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.press("f2")
            await asyncio.sleep(0.2)
            # Username should be focused by default
            save_screenshot(app, "04_login_dialog_username_focused")

    @pytest.mark.asyncio
    async def test_login_dialog_focus_password(self):
        """Test login dialog with password field focused."""
        app = ZBoxTUI()
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.press("f2")
            await asyncio.sleep(0.2)
            await pilot.press("tab")  # Move to password field
            await asyncio.sleep(0.1)
            save_screenshot(app, "05_login_dialog_password_focused")

    @pytest.mark.asyncio
    async def test_login_dialog_cancel(self):
        """Test login dialog cancel with Escape."""
        app = ZBoxTUI()
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.press("f2")
            await asyncio.sleep(0.2)
            await pilot.press("escape")
            await asyncio.sleep(0.2)
            save_screenshot(app, "06_login_dialog_cancelled")

            # Should be back to dashboard
            assert app.screen.__class__.__name__ == "DashboardScreen"

    @pytest.mark.asyncio
    async def test_login_dialog_submit(self):
        """Test login dialog submission. PAM is stubbed module-wide."""
        app = ZBoxTUI()
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.press("f2")
            await asyncio.sleep(0.2)
            # Enter password
            await pilot.press("tab")
            await pilot.press("t", "e", "s", "t")
            await pilot.press("enter")
            # Give the worker + screen push time to settle.
            await asyncio.sleep(0.5)
            save_screenshot(app, "07_login_success_menu")

            # Should now be on menu screen
            assert app.screen.__class__.__name__ == "MenuScreen"


class TestMenuScreen:
    """Tests for the system customization menu screen."""

    async def _login(self, pilot):
        """Helper to login and get to menu screen."""
        await pilot.press("f2")
        await asyncio.sleep(0.2)
        await pilot.press("tab")
        await pilot.press("t", "e", "s", "t")
        await pilot.press("enter")
        # PAM stub returns instantly, but screen push happens after.
        await asyncio.sleep(0.5)

    @pytest.mark.asyncio
    async def test_menu_initial_view(self):
        """Test menu screen displays correctly after login."""
        app = ZBoxTUI()
        async with app.run_test(size=(100, 30)) as pilot:
            await self._login(pilot)
            save_screenshot(app, "08_menu_initial")

            assert app.screen.__class__.__name__ == "MenuScreen"

    @pytest.mark.asyncio
    async def test_menu_navigate_down(self):
        """Test menu navigation with down arrow."""
        app = ZBoxTUI()
        async with app.run_test(size=(100, 30)) as pilot:
            await self._login(pilot)
            await pilot.press("down")
            await asyncio.sleep(0.1)
            save_screenshot(app, "09_menu_navigate_down_1")

            await pilot.press("down")
            await asyncio.sleep(0.1)
            save_screenshot(app, "10_menu_navigate_down_2")

    @pytest.mark.asyncio
    async def test_menu_navigate_up(self):
        """Test menu navigation with up arrow."""
        app = ZBoxTUI()
        async with app.run_test(size=(100, 30)) as pilot:
            await self._login(pilot)
            # Go down first
            await pilot.press("down", "down", "down")
            await asyncio.sleep(0.1)
            # Then go up
            await pilot.press("up")
            await asyncio.sleep(0.1)
            save_screenshot(app, "11_menu_navigate_up")

    @pytest.mark.asyncio
    async def test_menu_escape_logout(self):
        """Test Escape key logs out and returns to dashboard."""
        app = ZBoxTUI()
        async with app.run_test(size=(100, 30)) as pilot:
            await self._login(pilot)
            await pilot.press("escape")
            await asyncio.sleep(0.2)
            save_screenshot(app, "12_menu_escape_logout")

            # Should be back to dashboard
            assert app.screen.__class__.__name__ == "DashboardScreen"


class TestMenuDialogs:
    """Tests for dialogs opened from the menu."""

    async def _login(self, pilot):
        """Helper to login and get to menu screen."""
        await pilot.press("f2")
        await asyncio.sleep(0.2)
        await pilot.press("tab")
        await pilot.press("t", "e", "s", "t")
        await pilot.press("enter")
        await asyncio.sleep(0.2)

    @pytest.mark.asyncio
    async def test_configure_password_dialog(self):
        """Test Configure Password menu item."""
        app = ZBoxTUI()
        async with app.run_test(size=(100, 30)) as pilot:
            await self._login(pilot)
            # First item is Configure Password
            await pilot.press("enter")
            await asyncio.sleep(0.2)
            save_screenshot(app, "13_dialog_configure_password")

    @pytest.mark.asyncio
    async def test_configure_network_dialog(self):
        """Test Configure Network menu item."""
        app = ZBoxTUI()
        async with app.run_test(size=(100, 30)) as pilot:
            await self._login(pilot)
            await pilot.press("down")  # Navigate to Configure Network
            await pilot.press("enter")
            await asyncio.sleep(0.2)
            save_screenshot(app, "14_dialog_configure_network")

    @pytest.mark.asyncio
    async def test_restart_network_dialog(self):
        """Test Restart Network menu item."""
        app = ZBoxTUI()
        async with app.run_test(size=(100, 30)) as pilot:
            await self._login(pilot)
            await pilot.press("down", "down")  # Navigate to Restart Network
            await pilot.press("enter")
            await asyncio.sleep(0.2)
            save_screenshot(app, "15_dialog_restart_network")

    @pytest.mark.asyncio
    async def test_test_network_dialog(self):
        """Test Test Network Connectivity menu item."""
        app = ZBoxTUI()
        async with app.run_test(size=(100, 30)) as pilot:
            await self._login(pilot)
            await pilot.press("down", "down", "down")  # Navigate to Test Network
            await pilot.press("enter")
            await asyncio.sleep(0.3)  # Give time for network tests to start
            save_screenshot(app, "16_dialog_test_network")

    @pytest.mark.asyncio
    async def test_configure_keyboard_dialog(self):
        """Test Configure Keyboard menu item."""
        app = ZBoxTUI()
        async with app.run_test(size=(100, 30)) as pilot:
            await self._login(pilot)
            # Navigate past separator to Configure Keyboard
            for _ in range(4):
                await pilot.press("down")
            await pilot.press("enter")
            await asyncio.sleep(0.2)
            save_screenshot(app, "17_dialog_configure_keyboard")

    @pytest.mark.asyncio
    async def test_configure_packages_dialog(self):
        """Test Configure Packages menu item."""
        app = ZBoxTUI()
        async with app.run_test(size=(100, 30)) as pilot:
            await self._login(pilot)
            for _ in range(5):
                await pilot.press("down")
            await pilot.press("enter")
            await asyncio.sleep(0.2)
            save_screenshot(app, "18_dialog_configure_packages")

    @pytest.mark.asyncio
    async def test_view_system_logs_dialog(self):
        """Test View System Logs menu item."""
        app = ZBoxTUI()
        async with app.run_test(size=(100, 30)) as pilot:
            await self._login(pilot)
            for _ in range(6):
                await pilot.press("down")
            await pilot.press("enter")
            await asyncio.sleep(0.2)
            save_screenshot(app, "19_dialog_view_system_logs")

    @pytest.mark.asyncio
    async def test_view_zbox_logs_dialog(self):
        """Test View zBox System Logs menu item."""
        app = ZBoxTUI()
        async with app.run_test(size=(100, 30)) as pilot:
            await self._login(pilot)
            for _ in range(7):
                await pilot.press("down")
            await pilot.press("enter")
            await asyncio.sleep(0.2)
            save_screenshot(app, "20_dialog_view_zbox_logs")

    @pytest.mark.asyncio
    async def test_test_dialog(self):
        """Test the Test Dialog template menu item."""
        app = ZBoxTUI()
        async with app.run_test(size=(100, 30)) as pilot:
            await self._login(pilot)
            # Navigate to Test Dialog (last item, past separator)
            for _ in range(9):
                await pilot.press("down")
            await pilot.press("enter")
            await asyncio.sleep(0.2)
            save_screenshot(app, "21_dialog_test_dialog")


class TestDialogInteractions:
    """Tests for dialog keyboard interactions."""

    @pytest.mark.asyncio
    async def test_message_dialog_enter_close(self):
        """Test closing message dialog with Enter."""
        app = ZBoxTUI()
        async with app.run_test(size=(100, 30)) as pilot:
            # Open shutdown dialog from dashboard
            await pilot.press("f12")
            await asyncio.sleep(0.2)
            save_screenshot(app, "22_message_dialog_before_close")

            await pilot.press("enter")
            await asyncio.sleep(0.2)
            save_screenshot(app, "23_message_dialog_after_enter")

    @pytest.mark.asyncio
    async def test_message_dialog_escape_close(self):
        """Test closing message dialog with Escape."""
        app = ZBoxTUI()
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.press("f12")
            await asyncio.sleep(0.2)
            await pilot.press("escape")
            await asyncio.sleep(0.2)
            save_screenshot(app, "24_message_dialog_after_escape")

            # Should be back to dashboard
            assert app.screen.__class__.__name__ == "DashboardScreen"

    @pytest.mark.asyncio
    async def test_network_dialog_retest(self):
        """Test network dialog retest with R key."""
        app = ZBoxTUI()
        async with app.run_test(size=(100, 30)) as pilot:
            # Login first
            await pilot.press("f2")
            await asyncio.sleep(0.2)
            await pilot.press("tab")
            await pilot.press("t", "e", "s", "t")
            await pilot.press("enter")
            await asyncio.sleep(0.2)

            # Open network test dialog
            await pilot.press("down", "down", "down")
            await pilot.press("enter")
            await asyncio.sleep(0.5)
            save_screenshot(app, "25_network_dialog_initial")

            # Press R to retest
            await pilot.press("r")
            await asyncio.sleep(0.3)
            save_screenshot(app, "26_network_dialog_after_retest")

    @pytest.mark.asyncio
    async def test_network_dialog_completed(self):
        """Test network dialog after tests complete (6s wait)."""
        app = ZBoxTUI()
        async with app.run_test(size=(100, 30)) as pilot:
            # Login first
            await pilot.press("f2")
            await asyncio.sleep(0.2)
            await pilot.press("tab")
            await pilot.press("t", "e", "s", "t")
            await pilot.press("enter")
            await asyncio.sleep(0.2)

            # Open network test dialog
            await pilot.press("down", "down", "down")
            await pilot.press("enter")

            # Wait 6 seconds for network tests to complete
            await asyncio.sleep(6)
            save_screenshot(app, "26b_network_dialog_completed")


class TestDirectDialogs:
    """Tests for dialogs opened directly (not through menu)."""

    @pytest.mark.asyncio
    async def test_login_dialog_direct(self):
        """Test LoginDialog opened directly."""
        app = ZBoxTUI()
        async with app.run_test(size=(100, 30)):
            app.push_screen(LoginDialog(hostname="testserver"))
            await asyncio.sleep(0.2)
            save_screenshot(app, "27_login_dialog_direct")

    @pytest.mark.asyncio
    async def test_message_dialog_direct(self):
        """Test MessageDialog opened directly."""
        app = ZBoxTUI()
        async with app.run_test(size=(100, 30)):
            app.push_screen(MessageDialog(
                "Custom Title",
                "This is a custom message dialog.\n\n"
                "It can contain multiple lines of text."
            ))
            await asyncio.sleep(0.2)
            save_screenshot(app, "28_message_dialog_direct")

    @pytest.mark.asyncio
    async def test_network_dialog_direct(self):
        """Test NetworkTestDialog opened directly."""
        app = ZBoxTUI()
        async with app.run_test(size=(100, 30)):
            app.push_screen(NetworkTestDialog())
            await asyncio.sleep(0.3)
            save_screenshot(app, "29_network_dialog_direct")

    @pytest.mark.asyncio
    async def test_test_dialog_direct(self):
        """Test TestDialog opened directly."""
        app = ZBoxTUI()
        async with app.run_test(size=(100, 30)):
            app.push_screen(TestDialog())
            await asyncio.sleep(0.2)
            save_screenshot(app, "30_test_dialog_direct")


class TestEdgeCases:
    """Tests for edge cases and special scenarios."""

    @pytest.mark.asyncio
    async def test_multiple_dialog_stack(self):
        """Test opening dialog from within dialog."""
        app = ZBoxTUI()
        async with app.run_test(size=(100, 30)) as pilot:
            # Open login dialog
            await pilot.press("f2")
            await asyncio.sleep(0.2)
            save_screenshot(app, "31_dialog_stack_login")

    @pytest.mark.asyncio
    async def test_rapid_navigation(self):
        """Test rapid menu navigation."""
        app = ZBoxTUI()
        async with app.run_test(size=(100, 30)) as pilot:
            # Login
            await pilot.press("f2")
            await asyncio.sleep(0.2)
            await pilot.press("tab")
            await pilot.press("t", "e", "s", "t")
            await pilot.press("enter")
            await asyncio.sleep(0.2)

            # Rapid navigation
            for _ in range(10):
                await pilot.press("down")
            await asyncio.sleep(0.1)
            save_screenshot(app, "32_rapid_navigation_down")

            for _ in range(10):
                await pilot.press("up")
            await asyncio.sleep(0.1)
            save_screenshot(app, "33_rapid_navigation_up")

    @pytest.mark.asyncio
    async def test_different_terminal_sizes(self):
        """Test app at different terminal sizes."""
        # Small terminal
        app = ZBoxTUI()
        async with app.run_test(size=(80, 24)):
            await asyncio.sleep(0.2)
            save_screenshot(app, "34_terminal_size_80x24")

        # Large terminal
        app = ZBoxTUI()
        async with app.run_test(size=(120, 40)):
            await asyncio.sleep(0.2)
            save_screenshot(app, "35_terminal_size_120x40")

        # Wide terminal
        app = ZBoxTUI()
        async with app.run_test(size=(160, 30)):
            await asyncio.sleep(0.2)
            save_screenshot(app, "36_terminal_size_160x30")

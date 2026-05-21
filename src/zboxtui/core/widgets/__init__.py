"""Widget modules for zBoxTUI - importable by plugins."""

from .dcui_dialog import (
    DCUI_DIALOG_CSS,
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
    ping_host,
    verify_root_password,
)
from .dcui_footer import DCUIFooter
from .dcui_header import DCUIHeader
from .dcui_menu import DCUIMenu, MenuEntry, MenuGroupHeader, MenuItem

__all__ = [
    # CSS templates
    "DCUI_DIALOG_CSS",
    # Utility functions
    "ping_host",
    "verify_root_password",
    # Reusable widgets
    "DCUIHeader",
    "DCUIFooter",
    "DCUIMenu",
    "MenuEntry",
    "MenuItem",
    "MenuGroupHeader",
    # Dialogs
    "LoginDialog",
    "PasswordDialog",
    "MessageDialog",
    "NetworkTestDialog",
    "NetworkInterfaceDialog",
    "NetworkConfigDialog",
    "SystemLogsDialog",
    "SystemStatsDialog",
    "ZBoxLogsDialog",
    "TestDialog",
]

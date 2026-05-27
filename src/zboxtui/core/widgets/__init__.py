"""Widget modules for zBoxTUI - importable by plugins."""

from .bar_chart import BarChart
from .dcui_dialog import (
    DCUI_DIALOG_CSS,
    DIALOG_FOOTER_CLOSE,
    LoginDialog,
    MessageDialog,
    NetworkConfigDialog,
    NetworkInterfaceDialog,
    NetworkTestDialog,
    PasswordDialog,
    SystemLogsDialog,
    SystemStatsDialog,
    AboutDialog,
    ZBoxLogsDialog,
    ZBoxTuiLogsDialog,
    ping_host,
    verify_root_password,
)
from .dcui_footer import DCUIFooter
from .dcui_header import DCUIHeader
from .dcui_menu import DCUIMenu, MenuEntry, MenuGroupHeader, MenuItem
from .probes import ping_probe, probe_dots, run_probes, summarise

__all__ = [
    # Charts
    "BarChart",
    # CSS templates
    "DCUI_DIALOG_CSS",
    "DIALOG_FOOTER_CLOSE",
    # Utility functions
    "ping_host",
    "ping_probe",
    "probe_dots",
    "run_probes",
    "summarise",
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
    "ZBoxTuiLogsDialog",
    "AboutDialog",
]

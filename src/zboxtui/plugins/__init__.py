"""Auto-discovered menu plugins.

Each .py file at this package's level whose name does not start with `_` is
loaded by zboxtui.plugin_loader.discover_plugins() at MenuScreen build time.
Files are loaded in ASCII filename order (so 01_… before 02_… before 99_…).

A plugin module must export:
    MENU_LABEL: str
    MENU_DESCRIPTION: str
    def show_dialog(app: ZBoxTUI) -> None: ...

Optional:
    MENU_ENABLED = False   # skip without deleting the file
"""

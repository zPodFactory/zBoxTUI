"""Auto-discovered menu plugins (Plugins section only).

Each ``.py`` file here whose name does not start with ``_`` may appear in the
``[ Plugins ]`` menu when it exports ``MENU_SECTION = "Plugins"``.

Built-in actions (General, Network, Logs) are defined in
``zboxtui.core.menu_items`` — not in this package.

Required exports:
    MENU_LABEL: str
    MENU_DESCRIPTION: str
    MENU_SECTION = "Plugins"
    def show_dialog(app: ZBoxTUI) -> None: ...

Optional:
    MENU_ENABLED = False
"""

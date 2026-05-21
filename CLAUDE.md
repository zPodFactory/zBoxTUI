# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

zBoxTUI is an ESXi DCUI-style TUI (Text User Interface) for Debian system configuration. It uses the Textual framework to provide a console-based interface mimicking VMware ESXi's Direct Console User Interface.

## Build & Run Commands

```bash
# Install dependencies
uv sync

# Run the application
uv run python -m zboxtui
# or
uv run zboxtui

# Lint, typecheck, tests
uv run ruff check src/
uv run mypy src/
uv run pytest
uv run pytest tests/test_app.py::test_system_info -v   # single test

# Debug mode - auto-capture SVG screenshots of screens/dialogs
uv run zboxtui --debug-svg
# Screenshots are saved to the current directory (dashboard.svg, login_dialog.svg, etc.)

# Force a theme for this run (overrides app.conf)
uv run zboxtui --theme catppuccin   # default: violet Catppuccin Mocha
uv run zboxtui --theme esxi         # VMware ESXi yellow/grey

# Use a non-default config file
uv run zboxtui --config /path/to/app.conf

# Print a sample app.conf and exit
uv run zboxtui --generate-config
```

## Architecture

### Directory layout

```
src/zboxtui/
├── __init__.py                 # __version__
├── __main__.py                 # CLI entry: parses args, inits config + logging, launches app
├── app.py                      # ZBoxTUI(App): registers themes, dispatches menu actions
├── plugin_loader.py            # discover_plugins() — loads src/zboxtui/plugins/*.py
├── styles.tcss                 # Global CSS using $z-* theme variables
│
├── core/                       # Permanent, built-in surface
│   ├── themes.py               # CATPPUCCIN_THEME + ESXI_THEME (Textual Theme objects)
│   ├── screens/
│   │   ├── dashboard.py        # System info home screen (F2 → login, F12 → shutdown)
│   │   └── menu.py             # Builds menu from CORE_MENU_ITEMS + discovered plugins
│   ├── widgets/                # DCUIMenu, DCUIHeader, DCUIFooter, dialog classes
│   │   ├── dcui_dialog.py      # LoginDialog (PAM auth), PasswordDialog, NetworkConfigDialog,
│   │   │                       # NetworkTestDialog, SystemStatsDialog, etc.
│   │   ├── dcui_menu.py        # MenuItem, MenuGroupHeader, DCUIMenu
│   │   ├── dcui_header.py
│   │   └── dcui_footer.py
│   ├── utils/
│   │   ├── config.py           # AppConfig, load_config, init_config, write_theme
│   │   ├── logging.py          # init_logging (config-driven, truncates on start)
│   │   └── system.py           # SystemInfo, /proc + `ip` parsing, ping_host(), metrics helpers
│   └── menu_items/             # Built-in (non-plugin) menu handlers
│       ├── password.py
│       ├── network.py          # Configure / Restart
│       └── network_test.py
│
└── plugins/                    # Auto-discovered menu plugins (ASCII filename order)
    ├── 01_view_system_logs.py
    ├── 02_view_zbox_logs.py
    ├── 03_configure_packages.py
    ├── 60_themes.py            # Theme switcher dialog
    ├── 80_system_metrics.py    # Live CPU/mem/disk/net stats with sparklines
    ├── 90_test_google_ping.py
    ├── 91_test_cloudflare_ping.py
    └── 99_test_dialog.py
```

### Application flow
1. `__main__.py` parses CLI args, calls `init_config()` and `init_logging()`, then imports and runs `ZBoxTUI`.
2. `ZBoxTUI.__init__` registers both themes via `register_theme()` and applies the configured one — must happen before any CSS parses.
3. `on_mount` pushes `DashboardScreen`.
4. F2 → `LoginDialog` (modal). The dialog calls `verify_root_password()` (`su -c true root`, PAM-backed) in a background thread, returning `bool | None`.
5. On successful auth, `MenuScreen` builds its menu dynamically:
   - "General" group from `CORE_MENU_ITEMS` (password, network configure/restart, network test)
   - "Plugins" group from `discover_plugins()` (anything in `plugins/*.py`)
   - Registers an `action_id → Callable` map with the app via `set_menu_handlers`.
6. `app.handle_menu_action(action_id)` dispatches via the registry — no hardcoded if/elif.

### Plugin contract
A plugin is a `.py` file in `src/zboxtui/plugins/` whose name does not start with `_`. Files load in ASCII filename order (so `01_` before `02_` before `99_`). Each plugin must export:

```python
MENU_LABEL: str
MENU_DESCRIPTION: str
def show_dialog(app: ZBoxTUI) -> None: ...
```

Optional:
```python
MENU_ENABLED = False   # opt out without deleting the file
```

Plugins should import from `zboxtui.core.widgets` (which re-exports `DCUI_DIALOG_CSS`, `ping_host`, `MessageDialog`, etc.) and `zboxtui.core.utils.logging` for `get_logger`.

### Theming
- Two Textual `Theme` objects ship in `core/themes.py`: **catppuccin** (default, violet) and **esxi** (yellow/grey).
- Both populate the same custom variables consumed by widget CSS:
  - `$z-bg` / `$z-fg`             — main content background + foreground
  - `$z-panel` / `$z-panel-fg`    — header/footer/detail backgrounds + foreground (a separate fg is needed because ESXi's yellow bg and grey panels have very different luminance)
  - `$z-fg-dim`, `$z-fg-faint`, `$z-panel-fg-dim`, `$z-panel-fg-faint` — de-emphasis variants per context
  - `$z-accent` / `$z-accent-fg`  — selection highlight
  - `$z-crust`, `$z-mantle`, `$z-panel-focus`, `$z-border`, `$z-scrollbar`, `$z-error`, `$z-success`
- Themes are registered in `ZBoxTUI.__init__` (must be before CSS parse).
- The `60_themes.py` plugin lets the user switch live and persist via `write_theme()` in `core/utils/config.py`.

### Configuration
- INI file at `/etc/zboxtui/app.conf` (override via `--config` or `$ZBOXTUI_CONFIG`).
- Sections: `[general]` (log_file, log_level) and `[theme]` (name).
- `--generate-config` prints a sample to stdout.

### Textual patterns used
- `ModalScreen[T]` for dialogs with typed return values.
- `@work(exclusive=True)` / `@work(thread=True)` for async/background work (ping, password verification).
- `@on(Message)` for message handling.
- Custom `Message` classes (`DCUIMenu.Selected`, `DCUIMenu.Highlighted`).
- Live theme switching via `App.register_theme()` + setting `App.theme`.

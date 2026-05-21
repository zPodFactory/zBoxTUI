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

# Run linting
uv run ruff check src/

# Run type checking
uv run mypy src/

# Run all tests
uv run pytest

# Run a single test
uv run pytest tests/test_app.py::test_system_info -v

# Debug mode - auto-capture SVG screenshots of screens/dialogs
uv run zboxtui --debug-svg
# Screenshots are saved to the current directory (dashboard.svg, login_dialog.svg, etc.)

# Force a color palette (default is 'auto', detected from the terminal)
uv run zboxtui --palette catppuccin   # 24-bit Catppuccin Mocha
uv run zboxtui --palette console      # 16-color ANSI (Linux console)
```

## Architecture

### Application Flow
1. `ZBoxTUI` (app.py) is the main Textual App that manages screens and authentication state
2. On mount, pushes `DashboardScreen` showing system info
3. F2 triggers login flow via `LoginDialog` (modal screen)
4. After successful login, pushes `MenuScreen` for system configuration

### Key Components

**Screens** (`src/zboxtui/screens/`):
- `DashboardScreen`: Main home screen displaying hostname, CPU, memory, network interfaces
- `MenuScreen`: System configuration menu with selectable options

**Widgets** (`src/zboxtui/widgets/`):
- `DCUIMenu`: Custom focusable menu with keyboard navigation (up/down/enter)
- `LoginDialog`, `MessageDialog`, `NetworkTestDialog`: Modal dialogs extending `ModalScreen`
- `DCUIHeader`, `DCUIFooter`: Reusable header/footer bar widgets

**Utilities** (`src/zboxtui/utils/`):
- `system.py`: System info gathering (hostname, CPU, memory, network interfaces via `/proc` and `ip` command)

### Styling
- All CSS references colors via `$z-*` variables (`$z-bg`, `$z-accent`, ...), never hardcoded hex
- `theme.py` defines two palettes and picks one at startup based on terminal capabilities:
  - `CATPPUCCIN_PALETTE`: Catppuccin Mocha (violet-tinted), used on truecolor terminals
  - `CONSOLE_PALETTE`: 16-color ANSI (`ansi_*` names), used on the Linux console / non-truecolor
- `ZBoxTUI.get_css_variables()` injects the active palette; selection is `auto` (detected) or forced via `--palette`
- Styles defined in `styles.tcss` and inline `DEFAULT_CSS` in widgets
- Modal dialogs use `align: center middle` for centering

### Textual Patterns Used
- `ModalScreen[T]` for dialogs with typed return values
- `@work(exclusive=True)` decorator for async background tasks (network ping tests)
- `@on(Message)` decorator for message handling
- Custom `Message` classes for inter-widget communication (`DCUIMenu.Selected`, `DCUIMenu.Highlighted`)

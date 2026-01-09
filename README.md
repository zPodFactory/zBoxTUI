# zBoxTUI

ESXi DCUI-style TUI for Debian system configuration.

## Installation

```bash
uv sync
```

## Running

```bash
uv run python -m zboxtui
# or
uv run zboxtui
```

## Features

- ESXi DCUI look and feel
- System configuration menu:
  - Configure Password
  - Configure Network
  - Restart Network
  - Configure Keyboard
  - Configure Packages
  - View System Logs
  - View zBox System Logs

## Development

```bash
# Install with dev dependencies
uv sync

# Run linting
uv run ruff check src/

# Run tests
uv run pytest
```

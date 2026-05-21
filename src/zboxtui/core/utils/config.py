"""Configuration management for zBoxTUI.

Resolution order for the config file path (highest priority first):

1. Explicit argument passed to :func:`init_config` (e.g. ``--config PATH``).
2. ``$ZBOXTUI_CONFIG`` environment variable.
3. ``~/.config/zboxtui/app.conf`` (or ``$XDG_CONFIG_HOME/zboxtui/app.conf``)
   — the per-user config; preferred for desktop / non-root use.
4. ``/etc/zboxtui/app.conf`` — the system-wide config; the right home when
   the TUI is deployed on a box that everyone configures the same way.

Writes (e.g. :func:`write_theme`) follow the same priority but additionally
test for writability — if the system path was loaded but isn't writable
(typical for a non-root user), the change is persisted to the user path
instead so the user's choices survive a restart.
"""

from __future__ import annotations

import configparser
import contextlib
import os
from dataclasses import dataclass, field
from pathlib import Path

from ..themes import DEFAULT_THEME_NAME

SYSTEM_CONFIG_PATH = "/etc/zboxtui/app.conf"

DEFAULT_LOG_FILE = "/tmp/zboxtui.log"
DEFAULT_LOG_LEVEL = "INFO"


@dataclass
class AppConfig:
    """Runtime configuration values."""

    log_file: str = DEFAULT_LOG_FILE
    log_level: str = DEFAULT_LOG_LEVEL
    theme: str = DEFAULT_THEME_NAME

    # Path of the config file actually loaded (empty if defaults are in use).
    # Logged at startup so users can confirm which file took effect.
    config_file_used: str = field(default="", repr=False)

    def __post_init__(self) -> None:
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        normalized = self.log_level.upper()
        self.log_level = normalized if normalized in valid_levels else DEFAULT_LOG_LEVEL


def user_config_path() -> Path:
    """Per-user config file: $XDG_CONFIG_HOME/zboxtui/app.conf or ~/.config/...

    Always returns a path even if the file doesn't exist yet — callers that
    want to *write* there can mkdir the parent.
    """
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "zboxtui" / "app.conf"


def _resolve_load_path(explicit: str | None) -> Path | None:
    """Find the first existing config file in priority order, or None."""
    if explicit:
        return Path(explicit)

    env = os.environ.get("ZBOXTUI_CONFIG")
    if env:
        return Path(env)

    user = user_config_path()
    if user.is_file():
        return user

    system = Path(SYSTEM_CONFIG_PATH)
    if system.is_file():
        return system

    return None


def _is_writable(path: Path) -> bool:
    """Return True if `path` is writable (either as an existing file or
    by creating it in an existing writable parent directory).
    """
    if path.exists():
        return os.access(path, os.W_OK)
    parent = path.parent
    if parent.exists():
        return os.access(parent, os.W_OK)
    # Walk up until we find an existing ancestor; that's the one whose
    # writability decides if we can mkdir down to `path`.
    for ancestor in parent.parents:
        if ancestor.exists():
            return os.access(ancestor, os.W_OK)
    return False


def _resolve_write_path(explicit: str | None, used: str) -> Path:
    """Pick the best target for persisting a config change.

    Order: explicit > $ZBOXTUI_CONFIG > the file we loaded (if writable) >
    the user path (always writable for the current user, will be created
    on demand).
    """
    if explicit:
        return Path(explicit)

    env = os.environ.get("ZBOXTUI_CONFIG")
    if env:
        return Path(env)

    if used and not used.startswith("error"):
        loaded = Path(used)
        if _is_writable(loaded):
            return loaded

    return user_config_path()


def load_config(config_path: str | None = None) -> AppConfig:
    """Read the config file (if any) and return an :class:`AppConfig`."""
    config = AppConfig()
    path = _resolve_load_path(config_path)

    if path is None or not path.is_file():
        return config

    try:
        parser = configparser.ConfigParser()
        parser.read(path)
    except (configparser.Error, OSError) as exc:
        config.config_file_used = f"error reading {path}: {exc}"
        return config

    if "general" in parser:
        section = parser["general"]
        config.log_file = section.get("log_file", config.log_file)
        config.log_level = section.get("log_level", config.log_level).upper()

    if "theme" in parser:
        config.theme = parser["theme"].get("name", config.theme)

    config.config_file_used = str(path)
    # Re-run validation (post_init only fires on construction).
    return AppConfig(
        log_file=config.log_file,
        log_level=config.log_level,
        theme=config.theme,
        config_file_used=config.config_file_used,
    )


def generate_sample_config() -> str:
    """Return a sample config file as a single string."""
    user = user_config_path()
    return f"""\
# zBoxTUI Configuration File
#
# Locations (first hit wins):
#   1. --config <path> on the CLI
#   2. $ZBOXTUI_CONFIG
#   3. {user}
#   4. {SYSTEM_CONFIG_PATH}

[general]
# Log file location (default: {DEFAULT_LOG_FILE})
log_file = {DEFAULT_LOG_FILE}

# Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL (default: {DEFAULT_LOG_LEVEL})
log_level = {DEFAULT_LOG_LEVEL}

[theme]
# Built-in themes: catppuccin-mocha (default), vmware-esxi, nord,
# gruvbox, tokyo-night, textual-dark, atom-one-dark
name = {DEFAULT_THEME_NAME}
"""


_config: AppConfig | None = None


def init_config(config_path: str | None = None) -> AppConfig:
    """Load the config file (idempotent for the same path within a process)."""
    global _config
    _config = load_config(config_path)
    return _config


def get_config() -> AppConfig:
    """Return the active config, loading defaults on first access if needed."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def write_theme(theme_name: str, config_path: str | None = None) -> Path | None:
    """Persist a new theme name to the best-available config file.

    Returns the path written to on success, or None if no writable target
    could be found. Always updates the in-memory config so the running app
    reflects the change either way.
    """
    cfg = get_config()
    cfg.theme = theme_name

    path = _resolve_write_path(config_path, cfg.config_file_used)

    parser = configparser.ConfigParser()
    if path.exists():
        with contextlib.suppress(configparser.Error, OSError):
            parser.read(path)

    if "theme" not in parser:
        parser["theme"] = {}
    parser["theme"]["name"] = theme_name

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            parser.write(f)
    except (OSError, PermissionError):
        return None

    cfg.config_file_used = str(path)
    return path

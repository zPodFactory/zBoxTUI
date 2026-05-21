"""Configuration management for zBoxTUI.

Resolution order for the config file path:
1. Explicit argument passed to :func:`init_config`.
2. ``$ZBOXTUI_CONFIG`` environment variable.
3. ``/etc/zboxtui/app.conf``.
"""

from __future__ import annotations

import configparser
import contextlib
import os
from dataclasses import dataclass, field
from pathlib import Path

from ..themes import DEFAULT_THEME_NAME

DEFAULT_CONFIG_PATH = "/etc/zboxtui/app.conf"

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


def load_config(config_path: str | None = None) -> AppConfig:
    """Read the config file (if any) and return an :class:`AppConfig`."""
    config = AppConfig()

    if config_path:
        path = Path(config_path)
    else:
        env_path = os.environ.get("ZBOXTUI_CONFIG")
        path = Path(env_path) if env_path else Path(DEFAULT_CONFIG_PATH)

    if not (path.exists() and path.is_file()):
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
    config = AppConfig(
        log_file=config.log_file,
        log_level=config.log_level,
        theme=config.theme,
        config_file_used=config.config_file_used,
    )
    return config


def generate_sample_config() -> str:
    """Return a sample config file as a single string."""
    return f"""\
# zBoxTUI Configuration File
# Location: {DEFAULT_CONFIG_PATH}

[general]
# Log file location (default: {DEFAULT_LOG_FILE})
log_file = {DEFAULT_LOG_FILE}

# Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL (default: {DEFAULT_LOG_LEVEL})
log_level = {DEFAULT_LOG_LEVEL}

[theme]
# Built-in themes: catppuccin (default), esxi
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


def write_theme(theme_name: str, config_path: str | None = None) -> bool:
    """Persist a new theme name to the resolved config file.

    Returns True on success, False if the file is not writable. Updates the
    in-memory config either way so the running app reflects the change.
    """
    cfg = get_config()
    cfg.theme = theme_name

    if config_path:
        path = Path(config_path)
    elif cfg.config_file_used and not cfg.config_file_used.startswith("error"):
        path = Path(cfg.config_file_used)
    else:
        env_path = os.environ.get("ZBOXTUI_CONFIG")
        path = Path(env_path) if env_path else Path(DEFAULT_CONFIG_PATH)

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
        return False

    cfg.config_file_used = str(path)
    return True

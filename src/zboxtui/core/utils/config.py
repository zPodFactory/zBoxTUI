"""Configuration management for zBoxTUI.

Resolution order for the config file path (highest priority first):

1. Explicit argument passed to :func:`init_config` (e.g. ``--config PATH``).
2. ``$ZBOXTUI_CONFIG`` environment variable.
3. ``~/.config/zboxtui/app.conf`` (or ``$XDG_CONFIG_HOME/zboxtui/app.conf``)
   — the per-user config; preferred for desktop / non-root use.
4. ``/etc/zboxtui/app.conf`` — the system-wide config; the right home when
   the TUI is deployed on a box that everyone configures the same way.

Writes (e.g. :func:`write_theme`, :func:`write_settings`) follow the same
priority but additionally test for writability — if the system path was
loaded but isn't writable (typical for a non-root user), the change is
persisted to the user path instead so the user's choices survive a
restart.
"""

from __future__ import annotations

import configparser
import contextlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..themes import DEFAULT_THEME_NAME

SYSTEM_CONFIG_PATH = "/etc/zboxtui/app.conf"

# Default log path: relative to the process's working directory so it
# lands next to wherever the user runs `zboxtui` from. Override via
# config to use an absolute path (e.g. /var/log/zboxtui.log on a real
# zbox deployment).
DEFAULT_LOG_FILE = "zboxtui.log"
DEFAULT_LOG_LEVEL = "INFO"

# Default curated package list (raw GitHub URL — not github.com/blob/…).
DEFAULT_CATALOG_URL = (
    "https://raw.githubusercontent.com/zPodFactory/zBoxTUI/main/zbox-packages.json"
)

DEFAULT_DASHBOARD_LIVE_INFO = True
DEFAULT_DASHBOARD_REFRESH_INTERVAL_SECONDS = 2.0
DEFAULT_DASHBOARD_RESCAN_INTERVAL_SECONDS = 10.0
DEFAULT_NETWORK_TEST_TARGET = "1.1.1.1"
DEFAULT_DNS_TEST_TARGET = "example.com"


def _parse_bool(value: str | None, default: bool) -> bool:
    """Lenient bool parser for INI values.

    Accepts true/yes/on/1 and false/no/off/0 (case-insensitive). Falls
    back to ``default`` for anything else so a typo in the config file
    doesn't silently flip a setting.
    """
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"true", "yes", "on", "1"}:
        return True
    if normalized in {"false", "no", "off", "0"}:
        return False
    return default


def _parse_positive_int(value: str | None, default: int, *, minimum: int = 1) -> int:
    if value is None:
        return default
    try:
        result = int(value.strip())
    except (TypeError, ValueError):
        return default
    return result if result >= minimum else default


def _parse_positive_float(
    value: str | None, default: float, *, minimum: float = 0.1
) -> float:
    if value is None:
        return default
    try:
        result = float(value.strip())
    except (TypeError, ValueError):
        return default
    return result if result >= minimum else default


@dataclass
class AppConfig:
    """Runtime configuration values."""

    log_file: str = DEFAULT_LOG_FILE
    log_level: str = DEFAULT_LOG_LEVEL
    theme: str = DEFAULT_THEME_NAME
    catalog_url: str = DEFAULT_CATALOG_URL

    # Dashboard
    dashboard_display_live_information: bool = DEFAULT_DASHBOARD_LIVE_INFO
    dashboard_refresh_interval_seconds: float = DEFAULT_DASHBOARD_REFRESH_INTERVAL_SECONDS
    dashboard_rescan_interval_seconds: float = DEFAULT_DASHBOARD_RESCAN_INTERVAL_SECONDS

    # Network plugin defaults
    network_test_default_target: str = DEFAULT_NETWORK_TEST_TARGET
    dns_test_default_target: str = DEFAULT_DNS_TEST_TARGET

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

    if "dashboard" in parser:
        section = parser["dashboard"]
        config.dashboard_display_live_information = _parse_bool(
            section.get("display_live_information"),
            config.dashboard_display_live_information,
        )
        config.dashboard_refresh_interval_seconds = _parse_positive_float(
            section.get("refresh_interval_seconds"),
            config.dashboard_refresh_interval_seconds,
            minimum=0.5,
        )
        config.dashboard_rescan_interval_seconds = _parse_positive_float(
            section.get("rescan_interval_seconds"),
            config.dashboard_rescan_interval_seconds,
            minimum=1.0,
        )

    if "network" in parser:
        section = parser["network"]
        config.network_test_default_target = section.get(
            "test_default_target", config.network_test_default_target
        ).strip()
        config.dns_test_default_target = section.get(
            "dns_test_default_target", config.dns_test_default_target
        ).strip()

    if "theme" in parser:
        config.theme = parser["theme"].get("name", config.theme)

    if "packages" in parser:
        config.catalog_url = parser["packages"].get("catalog_url", config.catalog_url)

    config.config_file_used = str(path)
    # Re-run validation (post_init only fires on construction).
    return AppConfig(
        log_file=config.log_file,
        log_level=config.log_level,
        theme=config.theme,
        catalog_url=config.catalog_url,
        dashboard_display_live_information=config.dashboard_display_live_information,
        dashboard_refresh_interval_seconds=config.dashboard_refresh_interval_seconds,
        dashboard_rescan_interval_seconds=config.dashboard_rescan_interval_seconds,
        network_test_default_target=config.network_test_default_target,
        dns_test_default_target=config.dns_test_default_target,
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
# Log file location. Default is "zboxtui.log" in the directory you
# launched zboxtui from. Use an absolute path on a real deployment
# (e.g. /var/log/zboxtui.log).
log_file = {DEFAULT_LOG_FILE}

# Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL (default: {DEFAULT_LOG_LEVEL})
log_level = {DEFAULT_LOG_LEVEL}

[dashboard]
# Show the right-hand columns on the dashboard: the CPU/MEM Usage bars
# on the top panel and the Storage panel on the bottom-right. Disable
# for a minimal, static dashboard (useful on kiosks / low-power tty).
display_live_information = {str(DEFAULT_DASHBOARD_LIVE_INFO).lower()}

# How often (seconds) the dashboard refreshes CPU load and memory bars.
# Minimum 0.5; bumped to 5+ if you don't care about responsiveness and
# want lower idle load.
refresh_interval_seconds = {DEFAULT_DASHBOARD_REFRESH_INTERVAL_SECONDS}

# How often (seconds) the dashboard re-reads the slower-changing facts:
# hostname, interfaces and addresses, routes, mounted filesystems. The
# screen only repaints what changed. Minimum 1.
rescan_interval_seconds = {DEFAULT_DASHBOARD_RESCAN_INTERVAL_SECONDS}

[network]
# Default target prefilled into the Ping plugin's input box.
test_default_target = {DEFAULT_NETWORK_TEST_TARGET}

# Default hostname prefilled into the DNS Lookup plugin.
dns_test_default_target = {DEFAULT_DNS_TEST_TARGET}

[packages]
# Where "Refresh zBox curated package list" downloads the catalog from.
# Default: the official list in the zBoxTUI repository (raw.githubusercontent.com).
catalog_url = {DEFAULT_CATALOG_URL}

[theme]
# Built-in themes: catppuccin-mocha (default; https://catppuccin.com/palette/), vmware-esxi, nord,
# gruvbox, tokyo-night, atom-one-dark
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
    """Persist a new theme name to the best-available config file."""
    return write_settings({"theme": {"name": theme_name}}, config_path=config_path)


# Map of AppConfig attribute → (INI section, key). Used by write_settings
# to apply in-memory mutations alongside the on-disk write.
_SETTING_TO_INI: dict[str, tuple[str, str]] = {
    "log_file": ("general", "log_file"),
    "log_level": ("general", "log_level"),
    "dashboard_display_live_information": ("dashboard", "display_live_information"),
    "dashboard_refresh_interval_seconds": ("dashboard", "refresh_interval_seconds"),
    "dashboard_rescan_interval_seconds": ("dashboard", "rescan_interval_seconds"),
    "network_test_default_target": ("network", "test_default_target"),
    "dns_test_default_target": ("network", "dns_test_default_target"),
    "theme": ("theme", "name"),
    "catalog_url": ("packages", "catalog_url"),
}


def _format_ini_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def write_settings(
    updates: dict[str, Any] | dict[str, dict[str, Any]],
    *,
    config_path: str | None = None,
) -> Path | None:
    """Persist one or more settings to the best-available config file.

    Two input shapes are accepted:

    * Flat ``{attr_name: value}`` keyed by AppConfig field name (eg.
      ``{"dashboard_display_live_information": False}``). Each known
      attribute is also updated in the in-memory ``AppConfig``.
    * Nested ``{section: {key: value}}`` for setting raw INI entries
      (used by :func:`write_theme`).

    Returns the path written to on success, or None if no writable
    target could be found.
    """
    cfg = get_config()
    nested: dict[str, dict[str, Any]] = {}

    # Detect input shape: nested if every value is a dict.
    if updates and all(isinstance(v, dict) for v in updates.values()):
        for section, kv in updates.items():
            nested.setdefault(section, {}).update(kv)  # type: ignore[arg-type]
    else:
        for attr, value in updates.items():
            mapping = _SETTING_TO_INI.get(attr)
            if mapping is None:
                continue
            section, key = mapping
            nested.setdefault(section, {})[key] = value
            # Keep the in-memory config coherent with what we just wrote.
            if hasattr(cfg, attr):
                setattr(cfg, attr, value)

    if not nested:
        return None

    path = _resolve_write_path(config_path, cfg.config_file_used)

    parser = configparser.ConfigParser()
    if path.exists():
        with contextlib.suppress(configparser.Error, OSError):
            parser.read(path)

    for section, kv in nested.items():
        if section not in parser:
            parser[section] = {}
        for key, value in kv.items():
            parser[section][key] = _format_ini_value(value)

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            parser.write(f)
    except (OSError, PermissionError):
        return None

    cfg.config_file_used = str(path)
    return path

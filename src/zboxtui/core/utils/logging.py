"""Logging configuration for zBoxTUI.

Configuration values (log file path, level) come from :mod:`config`. The log
file is truncated on each application start so the log only ever contains the
current session.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .config import DEFAULT_LOG_FILE, get_config

logger = logging.getLogger("zboxtui")
# Set a permissive level on the base logger; the file handler enforces the
# configured threshold. This lets unit tests/get_logger() work even when
# init_logging() hasn't been called.
logger.setLevel(logging.DEBUG)

_initialized = False


def init_logging() -> None:
    """Wire up the file handler using values from the loaded config.

    Idempotent within a process; safe to call multiple times. The log file is
    opened in write mode so each run starts with a fresh file.
    """
    global _initialized
    if _initialized:
        return

    config = get_config()

    level = getattr(logging, config.log_level, logging.INFO)
    logger.setLevel(level)

    log_file = Path(config.log_file)
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, mode="w", encoding="utf-8")
    except (OSError, PermissionError):
        # Fall back to a writable default rather than crashing the app.
        log_file = Path(DEFAULT_LOG_FILE)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, mode="w", encoding="utf-8")

    file_handler.setLevel(level)
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    logger.addHandler(file_handler)
    _initialized = True

    logger.info("zBoxTUI logging initialized")
    logger.info("Log file:  %s", log_file)
    logger.info("Log level: %s", config.log_level)
    if config.config_file_used:
        logger.info("Config file: %s", config.config_file_used)
    else:
        logger.info("Config file: not found, using defaults")


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the ``zboxtui`` root."""
    return logger.getChild(name)


def read_zboxtui_log_lines(*, max_lines: int = 2000) -> tuple[Path, list[str]]:
    """Read lines from the configured zBoxTUI log file.

    Returns:
        Resolved log path and lines (most recent ``max_lines`` when truncated).
    """
    path = Path(get_config().log_file)
    if not path.is_absolute():
        path = path.resolve()
    if not path.exists():
        return path, [f"Log file not found: {path}"]
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except PermissionError:
        return path, [f"Permission denied reading: {path}"]
    except OSError as exc:
        return path, [f"Error reading log file: {exc}"]
    lines = text.splitlines()
    if not lines:
        return path, ["(empty log file)"]
    if len(lines) > max_lines:
        lines = lines[-max_lines:]
    return path, lines

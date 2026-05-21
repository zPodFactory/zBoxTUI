"""Logging configuration for zBoxTUI."""

import logging
from pathlib import Path

# Create logger
logger = logging.getLogger("zboxtui")
logger.setLevel(logging.DEBUG)

# Create file handler
log_file = Path.cwd() / "zboxtui.log"
file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
file_handler.setLevel(logging.DEBUG)

# Create formatter
formatter = logging.Formatter(
    "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
file_handler.setFormatter(formatter)

# Add handler to logger
logger.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """Get a child logger with the given name.

    Args:
        name: The name for the child logger (e.g., 'dialogs', 'app').

    Returns:
        A configured logger instance.
    """
    return logger.getChild(name)

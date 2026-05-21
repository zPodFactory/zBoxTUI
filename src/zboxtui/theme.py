"""Terminal-adaptive color palettes.

The UI styling references colors via CSS variables ($z-bg, $z-accent, ...).
The concrete values are supplied at startup by ZBoxTUI.get_css_variables(),
picking one of the palettes below based on terminal capabilities:

- Truecolor terminals (SSH from a modern emulator, tmux with COLORTERM set,
  etc.) get the full Catppuccin Mocha palette.
- The Linux virtual console and other non-truecolor terminals get a 16-color
  ANSI palette, which renders cleanly instead of being badly downsampled.
"""

from __future__ import annotations

import os

from .core.utils.logging import get_logger

log = get_logger("theme")

# Catppuccin Mocha (violet-tinted surfaces) - for 24-bit color terminals.
CATPPUCCIN_PALETTE: dict[str, str] = {
    "z-bg": "#2a2040",          # base - main background (dark mauve)
    "z-crust": "#15142a",       # crust - modal overlay, log panes
    "z-mantle": "#1e1a33",      # mantle - input field background
    "z-panel": "#3a3158",       # surface0 - raised bars, detail pane
    "z-panel-focus": "#4c4170", # surface1 - focused input background
    "z-border": "#5f5288",      # surface2 - panel borders
    "z-fg": "#cdd6f4",          # text - primary foreground
    "z-fg-dim": "#bac2de",      # subtext - secondary text
    "z-fg-faint": "#6c7086",    # overlay - faint text (pending, labels)
    "z-scrollbar": "#7f849c",   # overlay - scrollbar handle
    "z-accent": "#cba6f7",      # mauve - selection, titles, key hints
    "z-accent-fg": "#15142a",   # text on the accent color
    "z-error": "#f38ba8",       # red
    "z-success": "#a6e3a1",     # green
}

# 16-color ANSI palette - for the Linux console and non-truecolor terminals.
# Uses ansi_* names so it maps directly to the terminal's palette slots
# (and inherits any catppuccin-themed console palette the user has set).
CONSOLE_PALETTE: dict[str, str] = {
    "z-bg": "ansi_black",
    "z-crust": "ansi_black",
    "z-mantle": "ansi_bright_black",
    "z-panel": "ansi_bright_black",
    "z-panel-focus": "ansi_bright_blue",
    "z-border": "ansi_white",
    "z-fg": "ansi_bright_white",
    "z-fg-dim": "ansi_white",
    "z-fg-faint": "ansi_bright_black",
    "z-scrollbar": "ansi_white",
    "z-accent": "ansi_bright_magenta",
    "z-accent-fg": "ansi_black",
    "z-error": "ansi_bright_red",
    "z-success": "ansi_bright_green",
}


def supports_truecolor() -> bool:
    """Return True if the terminal can display 24-bit color."""
    term = os.environ.get("TERM", "")
    # The Linux virtual console is a fixed 16-color device.
    if term == "linux":
        return False
    # COLORTERM is the de-facto signal for 24-bit color support.
    return os.environ.get("COLORTERM", "").lower() in ("truecolor", "24bit")


def select_palette(mode: str = "auto") -> tuple[str, dict[str, str]]:
    """Pick a palette.

    Args:
        mode: "auto" detects from the terminal; "catppuccin" or "console"
            force a specific palette.

    Returns:
        A (name, palette) tuple.
    """
    if mode == "catppuccin":
        return "catppuccin", CATPPUCCIN_PALETTE
    if mode == "console":
        return "console", CONSOLE_PALETTE

    if supports_truecolor():
        log.info("Truecolor terminal detected, using catppuccin palette")
        return "catppuccin", CATPPUCCIN_PALETTE
    log.info(
        "No truecolor support (TERM=%s), using 16-color console palette",
        os.environ.get("TERM", ""),
    )
    return "console", CONSOLE_PALETTE

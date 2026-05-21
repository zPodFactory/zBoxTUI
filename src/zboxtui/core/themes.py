"""Built-in Textual themes for zBoxTUI.

Two themes ship with the app:

* ``catppuccin`` — the default, a violet-tinted Catppuccin Mocha palette
  designed for 24-bit terminals.
* ``esxi`` — a recreation of the classic VMware ESXi DCUI yellow/grey scheme.

Both themes populate Textual's standard slots (primary/secondary/accent/...)
and a set of custom ``z-*`` variables consumed by the DCUI widgets. Custom
variables are needed because the two themes have very different luminance
profiles for ``bg`` vs ``panel``, so each background context needs its own
foreground colors (``$z-fg`` on ``$z-bg``, ``$z-panel-fg`` on ``$z-panel``).
"""

from __future__ import annotations

from textual.theme import Theme


def _catppuccin_theme() -> Theme:
    """Catppuccin Mocha — the violet-tinted default."""
    return Theme(
        name="catppuccin",
        primary="#cba6f7",
        secondary="#3a3158",
        accent="#cba6f7",
        foreground="#cdd6f4",
        background="#2a2040",
        surface="#3a3158",
        panel="#3a3158",
        success="#a6e3a1",
        warning="#f9e2af",
        error="#f38ba8",
        dark=True,
        variables={
            "z-bg": "#2a2040",
            "z-crust": "#15142a",
            "z-mantle": "#1e1a33",
            "z-panel": "#3a3158",
            "z-panel-focus": "#4c4170",
            "z-border": "#5f5288",
            "z-fg": "#cdd6f4",
            "z-fg-dim": "#bac2de",
            "z-fg-faint": "#6c7086",
            "z-panel-fg": "#cdd6f4",
            "z-panel-fg-dim": "#bac2de",
            "z-panel-fg-faint": "#7f849c",
            "z-scrollbar": "#7f849c",
            "z-accent": "#cba6f7",
            "z-accent-fg": "#15142a",
            "z-error": "#f38ba8",
            "z-success": "#a6e3a1",
        },
    )


def _esxi_theme() -> Theme:
    """VMware ESXi DCUI — yellow panels, grey chrome."""
    return Theme(
        name="esxi",
        primary="#ffd700",
        secondary="#5a5a5a",
        accent="#ffd700",
        foreground="#000000",
        background="#5a5a5a",
        surface="#ffd700",
        panel="#5a5a5a",
        success="#006400",
        warning="#b8860b",
        error="#8b0000",
        dark=True,
        variables={
            "z-bg": "#ffd700",
            "z-crust": "#000000",
            "z-mantle": "#3a3a3a",
            "z-panel": "#5a5a5a",
            "z-panel-focus": "#4a4a4a",
            "z-border": "#ffffff",
            "z-fg": "#000000",
            "z-fg-dim": "#333333",
            "z-fg-faint": "#555555",
            "z-panel-fg": "#ffffff",
            "z-panel-fg-dim": "#cccccc",
            "z-panel-fg-faint": "#aaaaaa",
            "z-scrollbar": "#aaaaaa",
            "z-accent": "#5a5a5a",
            "z-accent-fg": "#ffd700",
            "z-error": "#8b0000",
            "z-success": "#006400",
        },
    )


def all_themes() -> list[Theme]:
    """Return every shipped theme, default first."""
    return [_catppuccin_theme(), _esxi_theme()]


DEFAULT_THEME_NAME = "catppuccin"

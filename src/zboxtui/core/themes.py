"""Built-in Textual themes for zBoxTUI.

Each theme populates Textual's standard slots (primary/foreground/...) plus
a set of custom ``z-*`` variables consumed by the DCUI widget CSS. Custom
variables are needed because some themes (notably vmware-esxi) have very
different luminance profiles for ``bg`` vs ``panel``, so each background
context needs its own foreground colors (``$z-fg`` on ``$z-bg``,
``$z-panel-fg`` on ``$z-panel``).

A small ``_make_theme()`` helper keeps each theme readable — it derives
sensible defaults so a theme only has to specify the colors that actually
differ from the obvious fallback (e.g. ``panel_fg`` defaults to ``fg``,
``title`` defaults to ``accent``).
"""

from __future__ import annotations

from textual.theme import Theme

DEFAULT_THEME_NAME = "catppuccin-mocha"


def _make_theme(
    name: str,
    *,
    bg: str,
    panel: str,
    fg: str,
    accent: str,
    success: str,
    error: str,
    warning: str,
    accent_fg: str | None = None,
    title: str | None = None,
    crust: str | None = None,
    mantle: str | None = None,
    panel_focus: str | None = None,
    border: str | None = None,
    fg_dim: str | None = None,
    fg_faint: str | None = None,
    panel_fg: str | None = None,
    panel_fg_dim: str | None = None,
    panel_fg_faint: str | None = None,
    scrollbar: str | None = None,
) -> Theme:
    """Build a Theme with all the ``$z-*`` variables zBoxTUI's CSS expects."""
    if accent_fg is None:
        accent_fg = bg
    if title is None:
        title = accent
    if crust is None:
        crust = panel
    if mantle is None:
        mantle = panel
    if panel_focus is None:
        panel_focus = panel
    if border is None:
        border = panel
    if fg_dim is None:
        fg_dim = fg
    if fg_faint is None:
        fg_faint = fg
    if panel_fg is None:
        panel_fg = fg
    if panel_fg_dim is None:
        panel_fg_dim = panel_fg
    if panel_fg_faint is None:
        panel_fg_faint = panel_fg
    if scrollbar is None:
        scrollbar = border

    return Theme(
        name=name,
        primary=accent,
        secondary=panel,
        accent=accent,
        foreground=fg,
        background=bg,
        surface=panel,
        panel=panel,
        success=success,
        warning=warning,
        error=error,
        dark=True,
        variables={
            "z-bg": bg,
            "z-crust": crust,
            "z-mantle": mantle,
            "z-panel": panel,
            "z-panel-focus": panel_focus,
            "z-border": border,
            "z-fg": fg,
            "z-fg-dim": fg_dim,
            "z-fg-faint": fg_faint,
            "z-panel-fg": panel_fg,
            "z-panel-fg-dim": panel_fg_dim,
            "z-panel-fg-faint": panel_fg_faint,
            "z-scrollbar": scrollbar,
            "z-accent": accent,
            "z-accent-fg": accent_fg,
            "z-title": title,
            "z-error": error,
            "z-success": success,
            "z-warning": warning,
        },
    )


def _catppuccin_mocha() -> Theme:
    """Catppuccin Mocha — the violet-tinted default."""
    return _make_theme(
        name="catppuccin-mocha",
        bg="#1e1e2e", crust="#11111b", mantle="#181825",
        panel="#313244", panel_focus="#45475a", border="#585b70",
        fg="#cdd6f4", fg_dim="#bac2de", fg_faint="#7f849c",
        panel_fg="#cdd6f4", panel_fg_dim="#bac2de", panel_fg_faint="#7f849c",
        scrollbar="#7f849c",
        accent="#cba6f7", accent_fg="#11111b", title="#cba6f7",
        success="#a6e3a1", warning="#f9e2af", error="#f38ba8",
    )


def _vmware_esxi() -> Theme:
    """VMware ESXi DCUI — yellow panels, grey chrome."""
    return _make_theme(
        name="vmware-esxi",
        bg="#ffd700", crust="#000000", mantle="#3a3a3a",
        panel="#5a5a5a", panel_focus="#4a4a4a", border="#ffffff",
        fg="#000000", fg_dim="#333333", fg_faint="#555555",
        panel_fg="#ffffff", panel_fg_dim="#cccccc", panel_fg_faint="#aaaaaa",
        scrollbar="#aaaaaa",
        accent="#5a5a5a", accent_fg="#ffffff", title="#ffffff",
        success="#006400", warning="#b8860b", error="#8b0000",
    )


def _nord() -> Theme:
    """Nord — arctic, bluish dark."""
    return _make_theme(
        name="nord",
        bg="#2e3440", crust="#242933", mantle="#2e3440",
        panel="#3b4252", panel_focus="#434c5e", border="#4c566a",
        fg="#eceff4", fg_dim="#d8dee9", fg_faint="#7b88a1",
        panel_fg="#eceff4", panel_fg_dim="#d8dee9", panel_fg_faint="#a0a8b8",
        scrollbar="#4c566a",
        accent="#88c0d0", accent_fg="#2e3440", title="#88c0d0",
        success="#a3be8c", warning="#ebcb8b", error="#bf616a",
    )


def _gruvbox() -> Theme:
    """Gruvbox Dark — retro warm tones."""
    return _make_theme(
        name="gruvbox",
        bg="#282828", crust="#1d2021", mantle="#282828",
        panel="#3c3836", panel_focus="#504945", border="#665c54",
        fg="#ebdbb2", fg_dim="#bdae93", fg_faint="#7c6f64",
        panel_fg="#ebdbb2", panel_fg_dim="#bdae93", panel_fg_faint="#a89984",
        scrollbar="#665c54",
        accent="#fabd2f", accent_fg="#282828", title="#fabd2f",
        success="#b8bb26", warning="#fe8019", error="#fb4934",
    )


def _tokyo_night() -> Theme:
    """Tokyo Night — neon-on-deep-blue."""
    return _make_theme(
        name="tokyo-night",
        bg="#1a1b26", crust="#0d0e15", mantle="#16161e",
        panel="#292e42", panel_focus="#3b4261", border="#545c7e",
        fg="#c0caf5", fg_dim="#a9b1d6", fg_faint="#565f89",
        panel_fg="#c0caf5", panel_fg_dim="#a9b1d6", panel_fg_faint="#737aa2",
        scrollbar="#545c7e",
        accent="#7aa2f7", accent_fg="#1a1b26", title="#bb9af7",
        success="#9ece6a", warning="#e0af68", error="#f7768e",
    )


def _textual_dark() -> Theme:
    """Textual's house dark theme — deep blue accent."""
    return _make_theme(
        name="textual-dark",
        bg="#1e1e1e", crust="#101010", mantle="#1e1e1e",
        panel="#272727", panel_focus="#3a3a3a", border="#4a4a4a",
        fg="#e0e0e0", fg_dim="#b0b0b0", fg_faint="#707070",
        panel_fg="#e0e0e0", panel_fg_dim="#b0b0b0", panel_fg_faint="#707070",
        scrollbar="#4a4a4a",
        accent="#0178d4", accent_fg="#ffffff", title="#0178d4",
        success="#4ebf71", warning="#ffa62b", error="#ba3c5b",
    )


def _atom_one_dark() -> Theme:
    """Atom One Dark — the classic editor theme."""
    return _make_theme(
        name="atom-one-dark",
        bg="#282c34", crust="#1e2127", mantle="#21252b",
        panel="#3a3f4b", panel_focus="#4b5263", border="#5c6370",
        fg="#abb2bf", fg_dim="#9da5b4", fg_faint="#5c6370",
        panel_fg="#abb2bf", panel_fg_dim="#9da5b4", panel_fg_faint="#5c6370",
        scrollbar="#4b5263",
        accent="#61afef", accent_fg="#282c34", title="#61afef",
        success="#98c379", warning="#d19a66", error="#e06c75",
    )


def all_themes() -> list[Theme]:
    """Return every shipped theme, default first."""
    return [
        _catppuccin_mocha(),
        _vmware_esxi(),
        _nord(),
        _gruvbox(),
        _tokyo_night(),
        _textual_dark(),
        _atom_one_dark(),
    ]


def theme_names() -> list[str]:
    """Return just the names, in display order."""
    return [t.name for t in all_themes()]

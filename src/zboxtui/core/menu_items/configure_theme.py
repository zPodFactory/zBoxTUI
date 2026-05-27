"""Theme selection menu item handler.

The dialog lives here rather than in core/widgets/dcui_dialog.py because
it's tightly coupled to the theme registry and the config-file persistence
in core/utils/config.write_theme(). Keeping it next to its handler keeps
the dependency chain local.

UX model (matches standard form behavior):
    * Up/Down (or k/j) move the cursor only — no live theme change.
    * Space toggles the cursor row as the selected theme: the [*] marker
      moves there and the theme applies live so you can see it.
    * Enter persists the currently-selected theme to the config file.
    * Esc/Q reverts to whatever theme was active when the dialog opened.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from ..themes import all_themes
from ..utils.config import write_theme
from ..utils.logging import get_logger
from ..widgets.dcui_dialog import (
    DCUI_DIALOG_CSS,
    MessageDialog,
    dismiss_screen_after_modal,
)

if TYPE_CHECKING:
    from ...app import ZBoxTUI

log = get_logger("menu.theme")


class ThemeDialog(ModalScreen[None]):
    """Pick from the registered themes; preview with Space, save with Enter."""

    app: ZBoxTUI

    BINDINGS = [
        Binding("escape", "close", "Close", show=False),
        Binding("q", "close", "Close", show=False),
        Binding("space", "toggle_select", "Select", show=False),
        Binding("enter", "save", "Save", show=False),
        Binding("up", "move_up", "Up", show=False),
        Binding("down", "move_down", "Down", show=False),
        Binding("k", "move_up", "Up", show=False),
        Binding("j", "move_down", "Down", show=False),
    ]

    DEFAULT_CSS = DCUI_DIALOG_CSS.format(dialog_class="ThemeDialog", width=50) + """
    ThemeDialog #dialog-body {
        padding: 1 2;
    }

    ThemeDialog .theme-item {
        height: 1;
        padding: 0 1;
        color: $z-fg;
    }

    ThemeDialog .theme-item.--cursor {
        background: $z-accent;
        color: $z-accent-fg;
    }

    ThemeDialog .hint {
        height: 1;
        margin-top: 1;
        color: $z-fg-faint;
        text-style: italic;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._themes = [t.name for t in all_themes()]
        # Snapshot the theme that was active when the dialog opened so we can
        # restore it if the user previews different ones then cancels.
        self._initial_theme: str = ""
        try:
            current = next(i for i, name in enumerate(self._themes) if name == self.app.theme)
        except (StopIteration, AttributeError):
            current = 0
        # _cursor_index: which row the user is highlighting (Up/Down).
        # _applied_index: which row is currently applied to the app (Space).
        self._cursor_index = current
        self._applied_index = current

    def on_mount(self) -> None:
        self._initial_theme = self.app.theme

    def compose(self) -> ComposeResult:
        with Container(id="dialog-outer"):
            with Vertical(id="dialog-header"):
                yield Static("")
                yield Static("Configure Theme", id="dialog-title")
                yield Static("")
                yield Static(
                    "Up/Down to navigate, Space to preview, Enter to save",
                    id="dialog-subtitle",
                )
                yield Static("")
            with Vertical(id="dialog-body"):
                for i, name in enumerate(self._themes):
                    yield Static(
                        self._format_row(i, name),
                        classes=self._classes_for_row(i),
                        id=f"theme-{i}",
                        markup=False,
                    )
                yield Static(
                    "Press Esc to revert.",
                    classes="hint",
                )
                yield Static("")
                yield Static(
                    "<Space> Preview    <Enter> Save    <Esc> Cancel",
                    id="dialog-footer",
                )

    def _format_row(self, index: int, name: str) -> str:
        prefix = "[*]" if index == self._applied_index else "[ ]"
        return f"{prefix} {name}"

    def _classes_for_row(self, index: int) -> str:
        classes = "theme-item"
        if index == self._cursor_index:
            classes += " --cursor"
        return classes

    def _refresh_rows(self) -> None:
        for i, name in enumerate(self._themes):
            row = self.query_one(f"#theme-{i}", Static)
            row.update(self._format_row(i, name))
            if i == self._cursor_index:
                row.add_class("--cursor")
            else:
                row.remove_class("--cursor")

    def _apply(self, theme_name: str) -> None:
        try:
            self.app.theme = theme_name
        except Exception:
            log.exception("Failed to apply theme '%s'", theme_name)

    def action_move_up(self) -> None:
        if self._cursor_index > 0:
            self._cursor_index -= 1
            self._refresh_rows()

    def action_move_down(self) -> None:
        if self._cursor_index < len(self._themes) - 1:
            self._cursor_index += 1
            self._refresh_rows()

    def action_toggle_select(self) -> None:
        """Space: live-apply the row at the cursor and move the [*] marker."""
        chosen = self._themes[self._cursor_index]
        if self._applied_index == self._cursor_index and self.app.theme == chosen:
            # Already the active selection — nothing to do.
            return
        self._applied_index = self._cursor_index
        self._apply(chosen)
        self._refresh_rows()

    def action_save(self) -> None:
        """Enter: write the currently-applied theme to the config file."""
        chosen = self._themes[self._applied_index]
        log.info("Saving theme to config: %s", chosen)

        written = write_theme(chosen)
        if written is not None:
            log.info("Theme persisted to %s", written)
            self.dismiss()
            return

        # All candidate paths refused the write.
        log.warning("Could not persist theme to any config path")
        self.app.push_screen(
            MessageDialog(
                "Theme Applied (Session Only)",
                f"Theme '{chosen}' is active for this session.\n\n"
                "No writable config file could be found. Set $ZBOXTUI_CONFIG "
                "to a path you can write to, or run with --config <path>, "
                "to make the choice persist across restarts.",
                ack_only=True,
            ),
            callback=dismiss_screen_after_modal(self),
        )

    def action_close(self) -> None:
        """Esc/Q: revert any preview and close without saving."""
        if self._initial_theme and self.app.theme != self._initial_theme:
            self._apply(self._initial_theme)
        self.dismiss()


def show_theme_dialog(app: ZBoxTUI) -> None:
    """Open the theme selector dialog."""
    log.info("Opening Configure Theme dialog")
    app.push_screen(ThemeDialog())

"""Plugin: switch between the shipped Textual themes (catppuccin, esxi)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from zboxtui.core.themes import all_themes
from zboxtui.core.utils.config import write_theme
from zboxtui.core.utils.logging import get_logger
from zboxtui.core.widgets import DCUI_DIALOG_CSS, MessageDialog

if TYPE_CHECKING:
    from zboxtui.app import ZBoxTUI

MENU_LABEL = "Change Theme"
MENU_DESCRIPTION = "Switch between the catppuccin and esxi color schemes."

log = get_logger("plugin.themes")


class ThemeDialog(ModalScreen[None]):
    """Pick from the registered themes and apply live."""

    app: ZBoxTUI

    BINDINGS = [
        Binding("escape", "close", "Close", show=False),
        Binding("enter", "select", "Select", show=False),
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

    ThemeDialog .theme-item.--selected {
        background: $z-accent;
        color: $z-accent-fg;
    }

    ThemeDialog .current-label {
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
        # restore it if the user previews a different one then cancels.
        self._initial_theme: str = ""
        try:
            current = next(i for i, name in enumerate(self._themes) if name == self.app.theme)
        except (StopIteration, AttributeError):
            current = 0
        self._selected_index = current
        self._current_index = current

    def on_mount(self) -> None:
        self._initial_theme = self.app.theme

    def compose(self) -> ComposeResult:
        with Container(id="dialog-outer"):
            with Vertical(id="dialog-header"):
                yield Static("")
                yield Static("Change Theme", id="dialog-title")
                yield Static("")
                yield Static("Select a color theme (live preview)", id="dialog-subtitle")
                yield Static("")
            with Vertical(id="dialog-body"):
                for i, name in enumerate(self._themes):
                    prefix = "[*]" if i == self._current_index else "[ ]"
                    classes = "theme-item"
                    if i == self._selected_index:
                        classes += " --selected"
                    yield Static(
                        f"{prefix} {name}",
                        classes=classes,
                        id=f"theme-{i}",
                        markup=False,
                    )
                yield Static(
                    "Tip: changes preview live. Enter applies; Esc cancels.",
                    classes="current-label",
                )
                yield Static("")
                yield Static("<Enter> Apply    <Esc> Cancel", id="dialog-footer")

    def _refresh_rows(self) -> None:
        for i in range(len(self._themes)):
            item = self.query_one(f"#theme-{i}", Static)
            if i == self._selected_index:
                item.add_class("--selected")
            else:
                item.remove_class("--selected")

    def _preview(self, theme_name: str) -> None:
        try:
            self.app.theme = theme_name
        except Exception:
            log.exception("Failed to preview theme '%s'", theme_name)

    def action_move_up(self) -> None:
        if self._selected_index > 0:
            self._selected_index -= 1
            self._refresh_rows()
            self._preview(self._themes[self._selected_index])

    def action_move_down(self) -> None:
        if self._selected_index < len(self._themes) - 1:
            self._selected_index += 1
            self._refresh_rows()
            self._preview(self._themes[self._selected_index])

    def action_select(self) -> None:
        chosen = self._themes[self._selected_index]
        self._preview(chosen)
        log.info("Applying theme: %s", chosen)

        persisted = write_theme(chosen)
        if persisted:
            self.dismiss()
            return

        # Apply succeeded for this session but disk write failed.
        log.warning("Could not persist theme to config file")
        self.app.push_screen(
            MessageDialog(
                "Theme Applied",
                f"Theme '{chosen}' is active for this session.\n\n"
                "The config file is not writable, so the choice won't persist "
                "across restarts. Run zBoxTUI with --config <path> pointing at "
                "a writable file to make it permanent.",
            ),
            callback=lambda _: self.dismiss(),
        )

    def action_close(self) -> None:
        if self._initial_theme and self.app.theme != self._initial_theme:
            self.app.theme = self._initial_theme
        self.dismiss()


def show_dialog(app: ZBoxTUI) -> None:
    log.info("Opening Theme Selector dialog")
    app.push_screen(ThemeDialog())

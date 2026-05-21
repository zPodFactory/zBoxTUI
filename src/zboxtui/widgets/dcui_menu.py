"""DCUI-style menu widget."""

from dataclasses import dataclass

from textual.app import ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Static


@dataclass
class MenuItem:
    """A menu item with label and description."""

    label: str
    description: str
    action: str  # Action identifier


class DCUIMenu(Widget, can_focus=True):
    """A DCUI-style vertical menu with keyboard navigation."""

    BINDINGS = [
        Binding("up", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("enter", "select", "Select", show=False),
    ]

    DEFAULT_CSS = """
    DCUIMenu {
        width: 100%;
        height: auto;
        background: $z-bg;
        color: $z-fg;
    }

    DCUIMenu > .menu-item {
        width: 100%;
        height: 1;
        padding: 0 1;
        background: $z-bg;
        color: $z-fg;
    }

    DCUIMenu > .menu-item.--selected {
        background: $z-accent;
        color: $z-accent-fg;
    }

    DCUIMenu > .menu-separator {
        width: 100%;
        height: 1;
        background: $z-bg;
    }
    """

    class Selected(Message):
        """Message sent when a menu item is selected."""

        def __init__(self, item: MenuItem) -> None:
            super().__init__()
            self.item = item

    class Highlighted(Message):
        """Message sent when a menu item is highlighted."""

        def __init__(self, item: MenuItem) -> None:
            super().__init__()
            self.item = item

    def __init__(
        self,
        items: list[MenuItem | None],  # None represents a separator
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._items = items
        self._selected_index = 0
        # Find first non-separator item
        for i, item in enumerate(items):
            if item is not None:
                self._selected_index = i
                break

    def compose(self) -> ComposeResult:
        for i, item in enumerate(self._items):
            if item is None:
                yield Static("", classes="menu-separator")
            else:
                classes = "menu-item"
                if i == self._selected_index:
                    classes += " --selected"
                yield Static(item.label, classes=classes, id=f"menu-item-{i}")

    def on_mount(self) -> None:
        """Send initial highlight message."""
        item = self._items[self._selected_index]
        if item is not None:
            self.post_message(self.Highlighted(item))

    def _get_selectable_indices(self) -> list[int]:
        """Get indices of selectable (non-separator) items."""
        return [i for i, item in enumerate(self._items) if item is not None]

    def action_cursor_up(self) -> None:
        """Move cursor up to previous selectable item."""
        indices = self._get_selectable_indices()
        if not indices:
            return
        current_pos = indices.index(self._selected_index) if self._selected_index in indices else 0
        new_pos = (current_pos - 1) % len(indices)
        self._update_selection(indices[new_pos])

    def action_cursor_down(self) -> None:
        """Move cursor down to next selectable item."""
        indices = self._get_selectable_indices()
        if not indices:
            return
        current_pos = indices.index(self._selected_index) if self._selected_index in indices else 0
        new_pos = (current_pos + 1) % len(indices)
        self._update_selection(indices[new_pos])

    def _update_selection(self, new_index: int) -> None:
        """Update the selected item."""
        # Remove selection from old item
        old_widget = self.query_one(f"#menu-item-{self._selected_index}", Static)
        old_widget.remove_class("--selected")

        # Add selection to new item
        self._selected_index = new_index
        new_widget = self.query_one(f"#menu-item-{new_index}", Static)
        new_widget.add_class("--selected")

        # Post highlight message
        item = self._items[new_index]
        if item is not None:
            self.post_message(self.Highlighted(item))

    def action_select(self) -> None:
        """Select the current item."""
        item = self._items[self._selected_index]
        if item is not None:
            self.post_message(self.Selected(item))

    @property
    def selected_item(self) -> MenuItem | None:
        """Get the currently selected item."""
        return self._items[self._selected_index]

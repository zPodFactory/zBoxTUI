"""DCUI-style header widget."""

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static


class DCUIHeader(Widget):
    """A DCUI-style header bar with left and right sections."""

    DEFAULT_CSS = """
    DCUIHeader {
        layout: horizontal;
        background: $z-panel;
        color: $z-panel-fg;
        height: 1;
        width: 100%;
    }

    DCUIHeader > .header-left {
        width: 1fr;
        padding: 0 1;
    }

    DCUIHeader > .header-right {
        width: 1fr;
        padding: 0 1;
        text-align: right;
    }
    """

    def __init__(
        self,
        left_text: str = "",
        right_text: str = "",
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._left_text = left_text
        self._right_text = right_text

    def compose(self) -> ComposeResult:
        yield Static(self._left_text, classes="header-left")
        yield Static(self._right_text, classes="header-right")

    def update_left(self, text: str) -> None:
        """Update the left section text."""
        self._left_text = text
        left = self.query_one(".header-left", Static)
        left.update(text)

    def update_right(self, text: str) -> None:
        """Update the right section text."""
        self._right_text = text
        right = self.query_one(".header-right", Static)
        right.update(text)

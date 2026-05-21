"""DCUI-style footer widget with F-key hints."""

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static


class DCUIFooter(Widget):
    """A DCUI-style footer bar with left, center, and right sections."""

    DEFAULT_CSS = """
    DCUIFooter {
        layout: horizontal;
        background: $z-panel;
        color: $z-panel-fg;
        height: 1;
        width: 100%;
    }

    DCUIFooter > .footer-left {
        width: 1fr;
        padding: 0 1;
    }

    DCUIFooter > .footer-center {
        width: 2fr;
        padding: 0 1;
        text-align: center;
    }

    DCUIFooter > .footer-right {
        width: 1fr;
        padding: 0 1;
        text-align: right;
    }
    """

    def __init__(
        self,
        left_text: str = "",
        center_text: str = "",
        right_text: str = "",
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._left_text = left_text
        self._center_text = center_text
        self._right_text = right_text

    def compose(self) -> ComposeResult:
        yield Static(self._left_text, classes="footer-left")
        yield Static(self._center_text, classes="footer-center")
        yield Static(self._right_text, classes="footer-right")

    def update_left(self, text: str) -> None:
        """Update the left section text."""
        self._left_text = text
        left = self.query_one(".footer-left", Static)
        left.update(text)

    def update_center(self, text: str) -> None:
        """Update the center section text."""
        self._center_text = text
        center = self.query_one(".footer-center", Static)
        center.update(text)

    def update_right(self, text: str) -> None:
        """Update the right section text."""
        self._right_text = text
        right = self.query_one(".footer-right", Static)
        right.update(text)

"""Multi-row Unicode bar chart for inline time-series visualizations.

Textual's built-in Sparkline is a single-line widget — its ``height`` CSS
property only sizes the container, not the bars themselves. This widget
renders bars across ``height`` rows using vertical block characters
(``▁▂▃▄▅▆▇█``) so a 3-row chart has 24 levels of vertical resolution
instead of 8, making subtle traffic variations visible.
"""

from __future__ import annotations

from collections.abc import Iterable

from rich.text import Text
from textual.reactive import reactive
from textual.widget import Widget

# 9 fill levels per row: empty (space) + 8 stacked block heights.
_BLOCKS = " ▁▂▃▄▅▆▇█"


class BarChart(Widget):
    """A multi-row vertical bar chart for sparkline-style time-series data."""

    DEFAULT_CSS = """
    BarChart {
        width: 1fr;
        height: 3;
    }
    """

    data: reactive[list[float]] = reactive(list, layout=True)

    def __init__(
        self,
        data: Iterable[float] | None = None,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        if data is not None:
            self.data = list(data)

    def render(self) -> Text:
        width = self.size.width
        height = self.size.height
        if width <= 0 or height <= 0 or not self.data:
            return Text("")

        # Show the most recent `width` samples; left-pad with zeros if we
        # have fewer (so the chart sits flush right and grows in over time
        # rather than stretching to fill).
        samples = list(self.data[-width:])
        if len(samples) < width:
            samples = [0.0] * (width - len(samples)) + samples

        max_val = max(samples)
        if max_val <= 0:
            # All-zero history: render blank rows so the widget still occupies
            # its bounds (otherwise the layout would collapse around it).
            blank = " " * width
            return Text("\n".join([blank] * height))

        # Per column, compute total fill in (height * 8) units, then peel
        # off 8 units per row from the bottom up. Each row's leftover is
        # the index into _BLOCKS for that column.
        lines: list[str] = []
        for row in range(height):
            row_from_bottom = height - 1 - row  # 0 = bottom row
            chars: list[str] = []
            for v in samples:
                total_units = (v / max_val) * height * 8
                this_row_units = max(0, min(8, int(total_units - row_from_bottom * 8)))
                chars.append(_BLOCKS[this_row_units])
            lines.append("".join(chars))

        return Text("\n".join(lines))

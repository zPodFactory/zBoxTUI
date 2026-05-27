"""Tests for System Configuration menu layout."""

from __future__ import annotations

from zboxtui.core.screens.menu import build_menu_items
from zboxtui.core.widgets.dcui_menu import MenuGroupHeader, MenuItem


def _labels(items) -> list[str]:
    out: list[str] = []
    for item in items:
        if isinstance(item, MenuGroupHeader):
            out.append(f"[{item.label}]")
        elif isinstance(item, MenuItem):
            out.append(item.label)
        elif item is None:
            out.append("")
    return out


def _assert_blank_between(labels: list[str], before: str, after: str) -> None:
    start = labels.index(before) + 1
    end = labels.index(after)
    assert "" in labels[start:end]


def test_menu_section_layout() -> None:
    items, _handlers = build_menu_items()
    labels = _labels(items)

    # General: header, spacer, items, spacer, more items
    assert labels.index("[General]") < labels.index("Configure Hostname")
    assert labels[labels.index("[General]") + 1] == ""
    _assert_blank_between(labels, "Configure Password", "Configure Packages")

    _assert_blank_between(labels, "Configure Settings", "View System Metrics")
    assert labels.index("View System Metrics") < labels.index("[Network]")
    _assert_blank_between(labels, "[Network]", "Configure Network")
    _assert_blank_between(labels, "Configure Network", "Network: Test connectivity")

    assert labels.index("Network: DNS Lookup") < labels.index("[Logs]")
    assert "[System]" not in labels
    assert labels[labels.index("[Logs]") + 1] == ""
    assert labels.index("[Logs]") < labels.index("View System Logs")
    assert labels.index("View zBoxTUI Logs") < labels.index("[Plugins]")
    assert labels[labels.index("[Plugins]") + 1] == ""
    assert labels.index("[Plugins]") < labels.index("Sample Plugin")
    assert "About" not in labels

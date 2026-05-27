"""Tests for dialog paragraph formatting."""

from zboxtui.core.widgets.dcui_dialog import format_dialog_paragraphs


def test_joins_fragments_with_spaces() -> None:
    text = format_dialog_paragraphs(["Hello", "world."])
    assert text == "Hello world."


def test_none_starts_new_paragraph() -> None:
    text = format_dialog_paragraphs(["Line one.", None, "Line two."])
    assert text == "Line one.\n\nLine two."


def test_empty_string_also_breaks_paragraph() -> None:
    text = format_dialog_paragraphs(["A", "", "B"])
    assert text == "A\n\nB"

"""Tests for zBoxTUI application."""

import pytest

from zboxtui.app import ZBoxTUI
from zboxtui.core.utils.system import get_system_info


def test_system_info():
    """Test that system info can be gathered."""
    info = get_system_info()
    assert info.hostname
    assert info.os_name
    assert info.cpu_info
    assert info.memory_total
    assert len(info.interfaces) > 0


@pytest.mark.asyncio
async def test_app_creation():
    """Test that the app can be created."""
    app = ZBoxTUI()
    assert app.title == "zBoxTUI"


@pytest.mark.asyncio
async def test_app_screens():
    """Test that app has expected screens."""
    app = ZBoxTUI()
    assert "dashboard" in app.SCREENS
    assert "menu" in app.SCREENS

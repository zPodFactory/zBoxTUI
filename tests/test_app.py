"""Tests for zBoxTUI application."""

from __future__ import annotations

from dataclasses import replace

import pytest
from textual.widgets import Static

from zboxtui.app import ZBoxTUI
from zboxtui.core.screens.dashboard import DashboardScreen
from zboxtui.core.utils import system as system_mod
from zboxtui.core.utils.system import SystemInfo, get_system_info


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


@pytest.mark.asyncio
async def test_dashboard_reload_updates_hostname(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """reload_dashboard() re-runs compose() with fresh get_system_info()."""
    base = get_system_info()
    current = {"info": base}

    def fake_get_system_info() -> SystemInfo:
        return current["info"]

    monkeypatch.setattr(system_mod, "get_system_info", fake_get_system_info)
    monkeypatch.setattr(
        "zboxtui.core.screens.dashboard.get_system_info",
        fake_get_system_info,
    )

    app = ZBoxTUI()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, DashboardScreen)
        host = app.screen.query_one("#dashboard-hostname", Static)
        assert host.content == base.hostname

        current["info"] = replace(base, hostname="newhost.example.com")
        app.reload_dashboard()
        await pilot.pause(delay=0.3)

        host = app.screen.query_one("#dashboard-hostname", Static)
        assert host.content == "newhost.example.com"

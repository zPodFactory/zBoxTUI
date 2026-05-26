"""Tests for NetworkConfigDialog keyboard navigation."""

from __future__ import annotations

import pytest
from textual.widgets import Input, Static

from zboxtui.app import ZBoxTUI
from zboxtui.core.widgets.dcui_dialog import NetworkConfigDialog, _NetworkFocusStatic


@pytest.mark.asyncio
async def test_network_config_tab_cycles_through_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "zboxtui.core.utils.system.get_interface_config",
        lambda _name: type(
            "Cfg",
            (),
            {
                "is_dhcp": False,
                "ipv4": "192.168.1.10",
                "cidr": 24,
                "netmask": "255.255.255.0",
                "gateway": "192.168.1.1",
                "dns1": "8.8.8.8",
                "dns2": "",
            },
        )(),
    )

    app = ZBoxTUI()
    async with app.run_test(size=(80, 30)) as pilot:
        app.push_screen(NetworkConfigDialog("eth0"))
        await pilot.pause()
        dlg = app.screen
        assert isinstance(dlg, NetworkConfigDialog)
        assert dlg._focused_field_id() == "dhcp-label"

        await pilot.press("tab")
        await pilot.pause()
        assert isinstance(dlg.focused, Input)
        assert dlg.focused.id == "ip-input"

        await pilot.press("tab")
        await pilot.pause()
        assert dlg.focused.id == "netmask-input"

        await pilot.press("shift+tab")
        await pilot.pause()
        assert dlg.focused.id == "ip-input"


@pytest.mark.asyncio
async def test_network_config_dhcp_toggle_updates_checkbox_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "zboxtui.core.utils.system.get_interface_config",
        lambda _name: type(
            "Cfg",
            (),
            {
                "is_dhcp": False,
                "ipv4": "192.168.1.10",
                "cidr": 24,
                "netmask": "255.255.255.0",
                "gateway": "192.168.1.1",
                "dns1": "8.8.8.8",
                "dns2": "",
            },
        )(),
    )

    app = ZBoxTUI()
    async with app.run_test(size=(80, 30)) as pilot:
        app.push_screen(NetworkConfigDialog("eth0"))
        await pilot.pause()
        dlg = app.screen
        assert isinstance(dlg, NetworkConfigDialog)
        dhcp_label = dlg.query_one("#dhcp-label", _NetworkFocusStatic)
        section_label = dlg.query_one("#section-label", Static)
        assert str(dhcp_label.content) == "[ ] Use DHCP"
        assert str(section_label.content) == "Static Configuration:"

        await pilot.press("space")
        await pilot.pause()
        assert dlg._is_dhcp is True
        assert str(dhcp_label.content) == "[X] Use DHCP"
        assert str(section_label.content) == "DHCP Configuration:"
        assert dlg.query_one("#ip-input-row").display is False
        assert dlg.query_one("#ip-dhcp-row").display is True

        await pilot.press("space")
        await pilot.pause()
        assert dlg._is_dhcp is False
        assert str(dhcp_label.content) == "[ ] Use DHCP"
        assert str(section_label.content) == "Static Configuration:"


@pytest.mark.asyncio
async def test_network_config_dhcp_mode_only_focuses_dhcp_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "zboxtui.core.utils.system.get_interface_config",
        lambda _name: type(
            "Cfg",
            (),
            {
                "is_dhcp": True,
                "ipv4": "10.0.0.5",
                "cidr": 24,
                "netmask": "255.255.255.0",
                "gateway": "10.0.0.1",
                "dns1": "1.1.1.1",
                "dns2": "",
            },
        )(),
    )

    app = ZBoxTUI()
    async with app.run_test(size=(80, 30)) as pilot:
        app.push_screen(NetworkConfigDialog("eth0"))
        await pilot.pause()
        dlg = app.screen
        assert isinstance(dlg, NetworkConfigDialog)
        assert dlg._focus_order() == ["dhcp-label"]

        await pilot.press("tab")
        await pilot.pause()
        assert isinstance(dlg.focused, _NetworkFocusStatic)
        assert dlg.focused.id == "dhcp-label"

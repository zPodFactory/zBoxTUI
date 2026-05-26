"""Tests for confirm → privileged command flow."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from zboxtui.app import ZBoxTUI
from zboxtui.core.menu_items.network import show_restart_network_dialog
from zboxtui.core.menu_items.privileged_flow import RebootingDialog
from zboxtui.core.utils.privilege import Privilege
from zboxtui.core.widgets.dcui_dialog import MessageDialog


@pytest.mark.asyncio
async def test_restart_network_confirm_launches_privileged_command() -> None:
    app = ZBoxTUI()
    with patch(
        "zboxtui.core.menu_items.network.run_confirmed_privileged_command"
    ) as run_cmd:
        show_restart_network_dialog(app)
        run_cmd.assert_called_once()
        assert run_cmd.call_args.kwargs["argv"] == ("systemctl", "restart", "networking")


@pytest.mark.asyncio
async def test_reboot_confirm_shows_spinner_then_reboots(monkeypatch: pytest.MonkeyPatch) -> None:
    reboot_calls: list[tuple] = []

    def fake_run(argv, privilege, **kwargs):
        reboot_calls.append((list(argv), privilege, kwargs))
        return True, "OK"

    monkeypatch.setattr(
        "zboxtui.core.menu_items.privileged_flow.run_privileged_command",
        fake_run,
    )
    monkeypatch.setattr(
        "zboxtui.core.menu_items.privileged_flow.detect_privilege",
        lambda: Privilege.ROOT,
    )
    monkeypatch.setattr(
        "zboxtui.core.menu_items.privileged_flow._REBOOT_SPINNER_DWELL_S",
        0.05,
    )

    app = ZBoxTUI()
    async with app.run_test(size=(80, 24)) as pilot:
        app.action_show_reboot()
        await pilot.pause()
        assert isinstance(app.screen, MessageDialog)

        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, RebootingDialog)

        await pilot.pause(0.2)
        assert reboot_calls
        assert reboot_calls[0][0] == ["systemctl", "reboot"]

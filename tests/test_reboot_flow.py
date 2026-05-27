"""Tests for confirm → privileged command flow."""

from __future__ import annotations

import pytest

from zboxtui.app import ZBoxTUI
from zboxtui.core.widgets.reboot_flow import RebootingDialog
from zboxtui.core.utils.privilege import Privilege
from zboxtui.core.widgets.dcui_dialog import LoginDialog, MessageDialog


async def _submit_root_login(pilot) -> None:
    await pilot.press("tab")
    for c in "root":
        await pilot.press(c)
    await pilot.press("enter")
    await pilot.pause()


@pytest.mark.asyncio
async def test_reboot_skips_login_when_authenticated() -> None:
    app = ZBoxTUI()
    app.grant_authenticated()
    async with app.run_test(size=(80, 24)) as pilot:
        app.action_show_reboot()
        await pilot.pause()
        assert isinstance(app.screen, MessageDialog)


@pytest.mark.asyncio
async def test_reboot_prompts_login_when_not_authenticated() -> None:
    app = ZBoxTUI()
    async with app.run_test(size=(80, 24)) as pilot:
        app.action_show_reboot()
        await pilot.pause()
        assert isinstance(app.screen, LoginDialog)


@pytest.mark.asyncio
async def test_reboot_login_confirm_then_reboots(monkeypatch: pytest.MonkeyPatch) -> None:
    reboot_calls: list[tuple] = []

    def fake_run(argv, privilege, **kwargs):
        reboot_calls.append((list(argv), privilege, kwargs))
        return True, "OK"

    monkeypatch.setattr(
        "zboxtui.core.widgets.dcui_dialog.verify_root_password",
        lambda _pw: True,
    )
    monkeypatch.setattr(
        "zboxtui.core.widgets.reboot_flow.run_privileged_command",
        fake_run,
    )
    monkeypatch.setattr(
        "zboxtui.core.widgets.reboot_flow.detect_privilege",
        lambda: Privilege.ROOT,
    )
    monkeypatch.setattr(
        "zboxtui.core.widgets.reboot_flow._REBOOT_SPINNER_DWELL_S",
        0.05,
    )

    app = ZBoxTUI()
    async with app.run_test(size=(80, 24)) as pilot:
        app.action_show_reboot()
        await pilot.pause()
        assert isinstance(app.screen, LoginDialog)

        await _submit_root_login(pilot)
        assert isinstance(app.screen, MessageDialog)

        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, RebootingDialog)

        await pilot.pause(0.2)
        assert reboot_calls
        assert reboot_calls[0][0] == ["systemctl", "reboot"]

"""Security-related app behaviour (no shell escape from dashboard)."""

from __future__ import annotations

import pytest

from zboxtui.app import ZBoxTUI, _PRODUCTION_QUIT_LOCK_BINDINGS
from zboxtui.core.screens.dashboard import DashboardScreen
from zboxtui.core.screens.menu import MenuScreen


@pytest.mark.asyncio
async def test_dashboard_has_no_quit_binding() -> None:
    keys = {b.key if hasattr(b, "key") else b[0] for b in DashboardScreen.BINDINGS}
    assert "q" not in keys
    assert "escape" not in keys


@pytest.mark.asyncio
async def test_ctrl_q_does_not_exit_without_allow_quit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ZBOXTUI_ALLOW_QUIT", raising=False)
    app = ZBoxTUI()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, DashboardScreen)
        await pilot.press("ctrl+q")
        await pilot.pause()
        assert isinstance(app.screen, DashboardScreen)


@pytest.mark.asyncio
async def test_ctrl_c_does_not_show_quit_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ZBOXTUI_ALLOW_QUIT", raising=False)
    notifications: list[str] = []

    def capture_notify(_self: ZBoxTUI, message: str, **_kwargs: object) -> None:
        notifications.append(message)

    monkeypatch.setattr(ZBoxTUI, "notify", capture_notify)
    app = ZBoxTUI()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        await pilot.press("ctrl+c")
        await pilot.pause()
        assert notifications == []
        assert isinstance(app.screen, DashboardScreen)


def test_production_bindings_override_textual_quit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ZBOXTUI_ALLOW_QUIT", raising=False)
    ZBoxTUI.BINDINGS = list(_PRODUCTION_QUIT_LOCK_BINDINGS)
    ZBoxTUI._merged_bindings = ZBoxTUI._merge_bindings()
    merged = ZBoxTUI._merge_bindings()
    assert [b.action for b in merged.key_to_bindings["ctrl+c"]] == ["noop"]
    assert [b.action for b in merged.key_to_bindings["ctrl+q"]] == ["noop"]


@pytest.mark.asyncio
async def test_leave_menu_keeps_authentication(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "zboxtui.core.widgets.dcui_dialog.verify_root_password",
        lambda _pw: True,
    )
    app = ZBoxTUI()
    async with app.run_test(size=(100, 30)) as pilot:
        app.action_show_login()
        await pilot.pause()
        await pilot.press("tab")
        for c in "root":
            await pilot.press(c)
        await pilot.press("enter")
        await pilot.pause()
        assert app._authenticated is True
        assert isinstance(app.screen, MenuScreen)

        app.screen.action_leave_menu()
        await pilot.pause()
        assert app._authenticated is True
        assert isinstance(app.screen, DashboardScreen)

        app.action_show_login()
        await pilot.pause()
        assert isinstance(app.screen, MenuScreen)


@pytest.mark.asyncio
async def test_f8_exits_from_menu_when_authenticated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ZBOXTUI_ALLOW_QUIT", raising=False)
    monkeypatch.setattr(
        "zboxtui.core.widgets.dcui_dialog.verify_root_password",
        lambda _pw: True,
    )
    app = ZBoxTUI()
    async with app.run_test(size=(100, 30)) as pilot:
        app.action_show_login()
        await pilot.pause()
        await pilot.press("tab")
        for c in "root":
            await pilot.press(c)
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, MenuScreen)
        await pilot.press("f8")
        await pilot.pause()
    assert not app.is_running


@pytest.mark.asyncio
async def test_exit_application_refused_without_login(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ZBOXTUI_ALLOW_QUIT", raising=False)
    app = ZBoxTUI()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        app.exit_application()
        await pilot.pause()
        assert app.is_running
        assert app._authenticated is False


def test_menu_has_f8_exit_binding() -> None:
    keys = {b.key if hasattr(b, "key") else b[0] for b in MenuScreen.BINDINGS}
    assert "f8" in keys


def test_sudo_timestamp_valid_success(monkeypatch: pytest.MonkeyPatch) -> None:
    from zboxtui.core.utils import privilege as pv

    monkeypatch.setattr(
        pv.subprocess,
        "run",
        lambda *a, **k: __import__("subprocess").CompletedProcess(
            args=a[0], returncode=0, stdout=b"", stderr=b""
        ),
    )
    assert pv.sudo_timestamp_valid() is True


def test_sudo_timestamp_valid_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    from zboxtui.core.utils import privilege as pv

    monkeypatch.setattr(
        pv.subprocess,
        "run",
        lambda *a, **k: __import__("subprocess").CompletedProcess(
            args=a[0], returncode=1, stdout=b"", stderr=b""
        ),
    )
    assert pv.sudo_timestamp_valid() is False


@pytest.mark.asyncio
async def test_logout_clears_authentication(monkeypatch: pytest.MonkeyPatch) -> None:
    from zboxtui.app import ZBoxTUI

    monkeypatch.setattr(
        "zboxtui.core.widgets.dcui_dialog.verify_root_password",
        lambda _pw: True,
    )
    app = ZBoxTUI()
    app.grant_authenticated()
    assert app.is_authenticated() is True
    app.logout()
    assert app.is_authenticated() is False


@pytest.mark.asyncio
async def test_auth_session_expires(monkeypatch: pytest.MonkeyPatch) -> None:
    from zboxtui import app as app_mod
    from zboxtui.app import ZBoxTUI

    monkeypatch.setattr(app_mod, "sudo_timestamp_valid", lambda: False)
    app = ZBoxTUI()
    app.grant_authenticated()
    app._auth_expires_at = 0.0
    assert app.is_authenticated() is False

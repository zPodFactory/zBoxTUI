"""Tests for ApplyDialog UX and helpers."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from textual.widgets import ProgressBar, Static

import zboxtui.core.menu_items.packages as pkg_mod
import zboxtui.core.widgets.apply_dialog as ad
import zboxtui.core.widgets.sudo_password_dialog as spd
from zboxtui.app import ZBoxTUI
from zboxtui.core.menu_items.packages import (
    PackagesDialog,
    PackagesSubmenuDialog,
    _finish_privileged_launch,
)
from zboxtui.core.utils.apt import AptOperation, StreamResult, plan_operations
from zboxtui.core.utils.privilege import Privilege
from zboxtui.core.widgets.apply_dialog import (
    ApplyDialog,
    package_rows_from_operations,
    refresh_workflow_rows,
)
from zboxtui.core.widgets.sudo_password_dialog import SudoPasswordDialog


def test_package_rows_from_operations_orders_removes_before_installs() -> None:
    ops = [
        AptOperation(kind="install", packages=("bat", "ripgrep")),
        AptOperation(kind="remove", packages=("lsd",)),
    ]
    rows = package_rows_from_operations(ops)
    assert [(r.name, r.action) for r in rows] == [
        ("lsd", "remove"),
        ("bat", "install"),
        ("ripgrep", "install"),
    ]


def test_package_rows_skips_index_update() -> None:
    ops = [AptOperation(kind="update", packages=())]
    assert package_rows_from_operations(ops) == []


@pytest.mark.asyncio
async def test_apply_dialog_mounts_after_sudo_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ApplyDialog must mount after sudo auth — never shadow MessagePump._running."""
    monkeypatch.setattr(
        pkg_mod, "detect_privilege", lambda: Privilege.SUDO_PASSWORD
    )

    app = ZBoxTUI()
    async with app.run_test(size=(100, 30)) as pilot:
        app.push_screen(PackagesSubmenuDialog())
        await pilot.pause()
        await pilot.press("down", "enter")
        await pilot.pause()
        assert isinstance(app.screen, SudoPasswordDialog)

        sudo = app.screen
        sudo.query_one("#password-input").value = "secret"
        with patch.object(spd, "_validate_sudo_password", return_value=True), patch.object(
            ad, "run_streaming_sync", return_value=StreamResult(returncode=0)
        ):
            sudo.action_submit()
            await pilot.pause()

        assert isinstance(app.screen, ApplyDialog)
        assert len(list(app.screen.query("#apt-log"))) == 0
        assert app.screen.query("#overall-spinner")
        assert app.screen.is_running is True
        assert app.screen._is_refresh_workflow is True
        assert len(list(app.screen.query("ProgressBar"))) == 2


def test_refresh_workflow_rows_show_two_steps() -> None:
    rows = refresh_workflow_rows()
    assert len(rows) == 2
    assert rows[0].label == "Updating APT sources ..."
    assert rows[1].label == "Updating zBox curated package list ..."


@pytest.mark.asyncio
async def test_refresh_workflow_shows_two_progress_bars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from zboxtui.core.utils.catalog_refresh import RefreshResult

    app = ZBoxTUI()
    async with app.run_test(size=(100, 30)) as pilot:
        with patch.object(ad, "run_streaming_sync", return_value=StreamResult(returncode=0)):
            with patch.object(
                ad,
                "refresh_catalog",
                return_value=RefreshResult(status="ok", message="ok", path=None),
            ):
                app.push_screen(
                    ApplyDialog(
                        [AptOperation(kind="update", packages=())],
                        Privilege.ROOT,
                        catalog_refresh_url="file:///tmp/packages.json",
                    )
                )
                await pilot.pause()
                dlg = app.screen
                assert len(dlg.query("ProgressBar")) == 2
                assert dlg.query_one("#pkg-bar-apt-sources", ProgressBar).progress == 100
                assert dlg.query_one("#pkg-bar-catalog", ProgressBar).progress == 100


@pytest.mark.asyncio
async def test_apply_dialog_shows_per_package_progress_bars() -> None:
    app = ZBoxTUI()
    ops = plan_operations(install=["bat"], remove=["lsd"])
    async with app.run_test(size=(100, 30)) as pilot:
        with patch.object(ad, "run_streaming_sync", return_value=StreamResult(returncode=0)) as run:
            app.push_screen(ApplyDialog(ops, Privilege.ROOT))
            await pilot.pause()
            dlg = app.screen
            assert len(dlg.query("ProgressBar")) == 2
            assert run.call_count == 2
            lsd_bar = dlg.query_one("#pkg-bar-lsd", ProgressBar)
            bat_bar = dlg.query_one("#pkg-bar-bat", ProgressBar)
            assert lsd_bar.progress == 100
            assert bat_bar.progress == 100


def test_finish_privileged_launch_reuses_cached_sudo_password() -> None:
    app = ZBoxTUI()
    app.remember_sudo_password("cached-secret")
    op = AptOperation(kind="update", packages=())
    with patch.object(pkg_mod, "_push_apply_dialog") as push_apply:
        _finish_privileged_launch(
            app,
            [op],
            Privilege.SUDO_PASSWORD,
            no_privilege_title="Cannot Refresh Package List",
        )
        push_apply.assert_called_once()
        assert push_apply.call_args.kwargs["password"] == "cached-secret"


@pytest.mark.asyncio
async def test_confirm_changes_shows_apply_overlay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pkg_mod, "detect_privilege", lambda: Privilege.ROOT)

    app = ZBoxTUI()
    async with app.run_test(size=(100, 32)) as pilot:
        app.push_screen(PackagesDialog())
        await pilot.pause()
        dialog = app.screen
        assert isinstance(dialog, PackagesDialog)
        dialog._show_apply_overlay()
        assert dialog.has_class("--applying")
        overlay = dialog.query_one("#apply-overlay", Static)
        assert overlay.display


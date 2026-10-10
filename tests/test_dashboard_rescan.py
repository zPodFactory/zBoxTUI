"""The dashboard's periodic rescan: repaint what changed, rebuild only for new mounts."""

from __future__ import annotations

from dataclasses import replace

import pytest
from textual.widgets import ProgressBar, Static

from zboxtui.app import ZBoxTUI
from zboxtui.core.screens.dashboard import DashboardScreen, DashboardTopology
from zboxtui.core.utils.system import FilesystemInfo


def _fs(mount: str, used: int, total: int = 1000) -> FilesystemInfo:
    return FilesystemInfo(
        device=f"/dev/{mount.strip('/') or 'root'}",
        mount_point=mount,
        fstype="ext4",
        used_bytes=used,
        total_bytes=total,
    )


@pytest.fixture
def live_config(monkeypatch: pytest.MonkeyPatch):
    from zboxtui.core.utils import config as config_mod

    cfg = config_mod.AppConfig(dashboard_display_live_information=True)
    monkeypatch.setattr(config_mod, "get_config", lambda: cfg)
    monkeypatch.setattr("zboxtui.core.screens.dashboard.get_config", lambda: cfg)
    return cfg


def _fake_info(monkeypatch: pytest.MonkeyPatch, filesystems: list[FilesystemInfo]):
    from zboxtui.core.utils import system as system_mod

    base = system_mod.get_system_info()
    info = replace(base, hostname="box.example.com", filesystems=filesystems)
    monkeypatch.setattr(system_mod, "get_system_info", lambda: info)
    monkeypatch.setattr("zboxtui.core.screens.dashboard.get_system_info", lambda: info)
    return info


@pytest.mark.asyncio
async def test_rescan_updates_text_and_bars_in_place(
    monkeypatch: pytest.MonkeyPatch, live_config
) -> None:
    _fake_info(monkeypatch, [_fs("/", 100), _fs("/boot", 200)])
    app = ZBoxTUI()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, DashboardScreen)
        before = screen._topology
        assert before is not None
        rebuilt = []
        monkeypatch.setattr(screen, "reload_from_config", lambda: rebuilt.append(True))

        after = DashboardTopology(
            hostname="renamed.example.com",
            network_text=before.network_text + "\n  → eth1.42:  10.173.42.1/28  [STATIC]",
            filesystems=(_fs("/", 500), _fs("/boot", 200)),
        )
        screen._apply_topology(after)
        await pilot.pause()

        assert rebuilt == []
        assert screen.query_one("#dashboard-hostname", Static).content == "renamed.example.com"
        assert "eth1.42" in str(screen.query_one("#network-block", Static).content)
        assert screen.query_one("#storage-pct-0", Static).content == "50%"
        assert screen.query_one("#storage-bar-0", ProgressBar).progress == 50.0
        assert screen._topology == after


@pytest.mark.asyncio
async def test_rescan_rebuilds_when_a_mount_appears(
    monkeypatch: pytest.MonkeyPatch, live_config
) -> None:
    _fake_info(monkeypatch, [_fs("/", 100)])
    app = ZBoxTUI()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, DashboardScreen)
        before = screen._topology
        assert before is not None
        rebuilt = []
        monkeypatch.setattr(screen, "reload_from_config", lambda: rebuilt.append(True))

        grown = replace(before, filesystems=(_fs("/", 100), _fs("/FILER/STORAGE02", 0)))
        screen._apply_topology(grown)
        assert rebuilt == [True]

        # Unchanged topology is a no-op, even with the rebuild hook armed.
        screen._apply_topology(before)
        assert rebuilt == [True]


@pytest.mark.asyncio
async def test_rescan_timer_runs_only_with_live_information(
    monkeypatch: pytest.MonkeyPatch, live_config
) -> None:
    _fake_info(monkeypatch, [_fs("/", 100)])
    app = ZBoxTUI()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, DashboardScreen)
        assert screen._rescan_timer is not None
        assert screen._refresh_timer is not None

        live_config.dashboard_display_live_information = False
        screen.reload_from_config()
        await pilot.pause(delay=0.3)
        assert screen._rescan_timer is None
        assert screen._refresh_timer is None


def test_rescan_interval_is_configurable(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from zboxtui.core.utils.config import AppConfig, generate_sample_config, load_config

    assert AppConfig().dashboard_rescan_interval_seconds == 10.0
    assert "rescan_interval_seconds" in generate_sample_config()
    cfg_path = tmp_path / "app.conf"
    cfg_path.write_text("[dashboard]\nrescan_interval_seconds = 0.2\n", encoding="utf-8")
    monkeypatch.setenv("ZBOXTUI_CONFIG", str(cfg_path))
    assert load_config().dashboard_rescan_interval_seconds == 10.0  # below minimum: default
    cfg_path.write_text("[dashboard]\nrescan_interval_seconds = 30\n", encoding="utf-8")
    assert load_config().dashboard_rescan_interval_seconds == 30.0

"""Tests for the new config keys, hostname validation, and the dialogs
introduced by the Configure Hostname / Network Details / Configure
Settings work.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import zboxtui.core.utils.config as config_mod
from zboxtui.app import ZBoxTUI
from zboxtui.core.menu_items import configure_hostname as hostname_mod
from zboxtui.core.menu_items.configure_hostname import (
    HostnameDialog,
    build_fqdn,
    validate_domain,
    validate_fqdn,
    validate_hostname,
)
from zboxtui.core.menu_items.configure_settings import SettingsDialog
from zboxtui.core.widgets.dcui_dialog import MessageDialog
from textual.widgets import Static
from zboxtui.core.utils.config import (
    AppConfig,
    generate_sample_config,
    load_config,
    write_settings,
)

# ----------------------------------------------------------------------
# Hostname validation
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    ["a", "host01", "0digit", "ok-host", "A-B-1", "x" * 63],
)
def test_validate_hostname_accepts(value: str) -> None:
    assert validate_hostname(value) is None


@pytest.mark.parametrize(
    "value",
    ["", "-bad", "bad-", "x" * 64, "has_underscore", "spaces here"],
)
def test_validate_hostname_rejects(value: str) -> None:
    assert validate_hostname(value) is not None


@pytest.mark.parametrize(
    "value",
    ["", "example.com", "a.b.c", "sub.example.co.uk", "example.com."],
)
def test_validate_domain_accepts(value: str) -> None:
    assert validate_domain(value) is None


@pytest.mark.parametrize(
    "value",
    ["bad..com", "-bad.com", "good.-bad", "u_score.com"],
)
def test_validate_domain_rejects(value: str) -> None:
    assert validate_domain(value) is not None


def test_build_fqdn_concatenates() -> None:
    assert build_fqdn("h", "d.com") == "h.d.com"


def test_build_fqdn_no_domain_returns_hostname() -> None:
    assert build_fqdn("h", "") == "h"


def test_build_fqdn_strips_trailing_dot() -> None:
    assert build_fqdn("h", "d.com.") == "h.d.com"


def test_validate_fqdn_propagates_hostname_error() -> None:
    assert validate_fqdn("", "ok.com") is not None


def test_validate_fqdn_propagates_domain_error() -> None:
    assert validate_fqdn("ok", "-bad.com") is not None


def test_validate_fqdn_ok() -> None:
    assert validate_fqdn("host", "example.com") is None


# ----------------------------------------------------------------------
# Config round-trip for the new keys
# ----------------------------------------------------------------------


def _isolate_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Force load/write paths to a writable temp file for one test."""
    cfg_path = tmp_path / "app.conf"
    monkeypatch.setenv("ZBOXTUI_CONFIG", str(cfg_path))
    monkeypatch.setattr(config_mod, "_config", None)
    return cfg_path


def test_appconfig_defaults() -> None:
    cfg = AppConfig()
    assert cfg.dashboard_display_live_information is True
    assert cfg.dashboard_refresh_interval_seconds == 2.0
    assert cfg.network_test_default_target == "1.1.1.1"
    assert cfg.dns_test_default_target == "example.com"


def test_load_config_parses_dashboard_section(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg_path = _isolate_config(tmp_path, monkeypatch)
    cfg_path.write_text(
        "[dashboard]\n"
        "display_live_information = false\n"
        "refresh_interval_seconds = 5\n"
        "[network]\n"
        "test_default_target = 8.8.8.8\n"
        "dns_test_default_target = anthropic.com\n",
        encoding="utf-8",
    )
    cfg = load_config()
    assert cfg.dashboard_display_live_information is False
    assert cfg.dashboard_refresh_interval_seconds == 5.0
    assert cfg.network_test_default_target == "8.8.8.8"
    assert cfg.dns_test_default_target == "anthropic.com"


def test_load_config_rejects_invalid_float(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg_path = _isolate_config(tmp_path, monkeypatch)
    cfg_path.write_text(
        "[dashboard]\nrefresh_interval_seconds = notanumber\n",
        encoding="utf-8",
    )
    cfg = load_config()
    # Falls back to the default rather than blowing up.
    assert cfg.dashboard_refresh_interval_seconds == 2.0


def test_write_settings_round_trip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg_path = _isolate_config(tmp_path, monkeypatch)
    config_mod.init_config(str(cfg_path))

    path = write_settings(
        {
            "dashboard_display_live_information": False,
            "dashboard_refresh_interval_seconds": 5.0,
            "network_test_default_target": "9.9.9.9",
            "theme": "nord",
        }
    )
    assert path == cfg_path
    cfg = load_config()
    assert cfg.dashboard_display_live_information is False
    assert cfg.dashboard_refresh_interval_seconds == 5.0
    assert cfg.network_test_default_target == "9.9.9.9"
    assert cfg.theme == "nord"


def test_generate_sample_config_mentions_new_keys() -> None:
    sample = generate_sample_config()
    assert "[dashboard]" in sample
    assert "display_live_information" in sample
    assert "refresh_interval_seconds" in sample
    assert "[network]" in sample
    assert "test_default_target" in sample


# ----------------------------------------------------------------------
# Dialog smoke tests — verify each new dialog mounts without raising
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hostname_dialog_mounts() -> None:
    app = ZBoxTUI()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        app.push_screen(HostnameDialog())
        await pilot.pause()
        # The screen on top should be ours.
        assert app.screen.__class__.__name__ == "HostnameDialog"




@pytest.mark.asyncio
async def test_hostname_success_ack_closes_without_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Success notice is ack-only; Enter/Esc must not nested-dismiss crash."""
    monkeypatch.setattr(
        hostname_mod,
        "apply_hostname",
        lambda hostname, domain: (True, f"Hostname set to {hostname}.{domain}"),
    )
    app = ZBoxTUI()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        app.push_screen(HostnameDialog())
        await pilot.pause()
        dialog = app.screen
        assert isinstance(dialog, HostnameDialog)
        dialog.query_one("#hostname-input").value = "newhost"
        dialog.query_one("#domain-input").value = "example.com"
        dialog.query_one("#domain-input").focus()
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, MessageDialog)
        assert app.screen._ack_only is True
        footer = app.screen.query_one("#dialog-footer", Static).content
        assert footer == "Press Enter to close"
        assert "Cancel" not in footer
        await pilot.press("escape")
        await pilot.pause()
        assert app.screen.__class__.__name__ == "DashboardScreen"

@pytest.mark.asyncio
async def test_settings_dialog_mounts() -> None:
    app = ZBoxTUI()
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause()
        app.push_screen(SettingsDialog())
        await pilot.pause()
        assert app.screen.__class__.__name__ == "SettingsDialog"


@pytest.mark.asyncio
async def test_dashboard_hides_storage_when_live_info_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg_path = _isolate_config(tmp_path, monkeypatch)
    cfg_path.write_text(
        "[dashboard]\ndisplay_live_information = false\n",
        encoding="utf-8",
    )
    config_mod.init_config(str(cfg_path))
    app = ZBoxTUI()
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        # Right-side storage container should not be in the DOM.
        assert len(app.screen.query("#content-storage")) == 0
        # Header bars should not exist either.
        assert len(app.screen.query("#cpu-load-bar")) == 0

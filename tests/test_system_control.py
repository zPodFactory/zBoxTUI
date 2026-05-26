"""Tests for privileged system control commands."""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from typing import Any

import pytest

from zboxtui.core.utils import privilege as pv
from zboxtui.core.utils.privilege import Privilege, run_privileged_command
from zboxtui.core.utils.system_control import NETWORKING_RESTART_CMD, REBOOT_CMD


@pytest.fixture
def root_euid(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(pv.os, "geteuid", lambda: 0)
    yield


def test_restart_networking_argv() -> None:
    assert NETWORKING_RESTART_CMD == ("systemctl", "restart", "networking")


def test_reboot_argv() -> None:
    assert REBOOT_CMD == ("systemctl", "reboot",)


def test_run_privileged_command_success(root_euid: None, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert args[0] == ["systemctl", "restart", "networking"]
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr="")

    monkeypatch.setattr(pv.subprocess, "run", fake_run)
    ok, msg = run_privileged_command(
        NETWORKING_RESTART_CMD,
        Privilege.ROOT,
        timeout=60,
    )
    assert ok is True
    assert msg == "OK"


def test_run_privileged_command_failure(root_euid: None, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=1,
            stdout="",
            stderr="Failed to restart networking.service: Unit not found.\n",
        )

    monkeypatch.setattr(pv.subprocess, "run", fake_run)
    ok, msg = run_privileged_command(REBOOT_CMD, Privilege.ROOT)
    assert ok is False
    assert "Failed to restart" in msg or "Unit not found" in msg

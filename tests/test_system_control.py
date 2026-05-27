"""Tests for privileged system control commands."""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from zboxtui.core.utils import privilege as pv
from zboxtui.core.utils.privilege import Privilege, run_privileged_command
from zboxtui.core.utils.system_control import (
    REBOOT_CMD,
    NetworkApplyRequest,
    apply_network_interface,
)


@pytest.fixture
def root_euid(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(pv.os, "geteuid", lambda: 0)
    yield


def test_reboot_argv() -> None:
    assert REBOOT_CMD == ("systemctl", "reboot",)


def test_run_privileged_command_success(root_euid: None, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert args[0] == ["systemctl", "reboot"]
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr="")

    monkeypatch.setattr(pv.subprocess, "run", fake_run)
    ok, msg = run_privileged_command(
        REBOOT_CMD,
        Privilege.ROOT,
        timeout=15,
    )
    assert ok is True
    assert msg == "OK"


def test_run_privileged_command_failure(root_euid: None, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=1,
            stdout="",
            stderr="Failed to reboot: Operation not permitted.\n",
        )

    monkeypatch.setattr(pv.subprocess, "run", fake_run)
    ok, msg = run_privileged_command(REBOOT_CMD, Privilege.ROOT)
    assert ok is False
    assert "Failed to reboot" in msg or "not permitted" in msg


def test_apply_network_interface_reports_missing_ifupdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "zboxtui.core.utils.system_control.shutil.which",
        lambda name: None if name in {"ifup", "ifdown"} else f"/usr/sbin/{name}",
    )
    ok, msg = apply_network_interface(
        NetworkApplyRequest(interface="eth0", dhcp=True),
    )
    assert ok is False
    assert "ifup" in msg or "ifdown" in msg


def test_apply_network_interface_static_writes_and_ifup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    iface_file = tmp_path / "interfaces"
    iface_file.write_text(
        "auto eth0\niface eth0 inet dhcp\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "zboxtui.core.utils.system_control.shutil.which",
        lambda name: f"/usr/sbin/{name}",
    )
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("zboxtui.core.utils.system_control.subprocess.run", fake_run)

    ok, msg = apply_network_interface(
        NetworkApplyRequest(
            interface="eth0",
            dhcp=False,
            ip="192.168.1.50",
            netmask="255.255.255.0",
            gateway="192.168.1.1",
            dns1="8.8.8.8",
        ),
        interfaces_file=iface_file,
    )
    assert ok is True
    assert "eth0" in msg
    written = iface_file.read_text(encoding="utf-8")
    assert "inet static" in written
    assert "192.168.1.50" in written
    assert any(cmd[:2] == ["ifdown", "--force"] for cmd in calls)
    assert any(cmd[:2] == ["ifup", "eth0"] for cmd in calls)

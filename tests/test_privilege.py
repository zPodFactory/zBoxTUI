"""Tests for the privilege-detection and apt-command-building helpers."""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from typing import Any

import pytest

from zboxtui.core.utils import privilege as pv
from zboxtui.core.utils.privilege import (
    Privilege,
    banner_for,
    build_apt_command,
    detect_privilege,
)


@pytest.fixture
def root_euid(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(pv.os, "geteuid", lambda: 0)
    yield


@pytest.fixture
def nonroot_euid(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(pv.os, "geteuid", lambda: 1000)
    yield


def _stub_sudo_nopasswd(monkeypatch: pytest.MonkeyPatch, returncode: int) -> None:
    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(
            args=args[0] if args else [], returncode=returncode, stdout=b"", stderr=b""
        )

    monkeypatch.setattr(pv.subprocess, "run", fake_run)


def _stub_sudo_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        raise FileNotFoundError("sudo")

    monkeypatch.setattr(pv.subprocess, "run", fake_run)


def _stub_in_sudo_group(monkeypatch: pytest.MonkeyPatch, member: bool) -> None:
    monkeypatch.setattr(pv, "_user_in_sudoers_group", lambda: member)


# ---------------------------------------------------------------------------
# detect_privilege
# ---------------------------------------------------------------------------


def test_root_user_returns_root(root_euid: None) -> None:
    assert detect_privilege() == Privilege.ROOT


def test_nonroot_with_nopasswd_sudo(
    nonroot_euid: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_sudo_nopasswd(monkeypatch, returncode=0)
    assert detect_privilege() == Privilege.SUDO_NOPASSWD


def test_nonroot_sudo_requires_password(
    nonroot_euid: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_sudo_nopasswd(monkeypatch, returncode=1)
    _stub_in_sudo_group(monkeypatch, member=True)
    assert detect_privilege() == Privilege.SUDO_PASSWORD


def test_nonroot_not_in_sudoers(
    nonroot_euid: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_sudo_nopasswd(monkeypatch, returncode=1)
    _stub_in_sudo_group(monkeypatch, member=False)
    assert detect_privilege() == Privilege.NONE


def test_nonroot_without_sudo_binary(
    nonroot_euid: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A box without ``sudo`` installed at all should degrade to NONE,
    not crash, even if the user happens to be in the sudo group."""
    _stub_sudo_missing(monkeypatch)
    _stub_in_sudo_group(monkeypatch, member=False)
    assert detect_privilege() == Privilege.NONE


def test_sudo_nopasswd_timeout_treated_as_no(
    nonroot_euid: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A sudo prompt that hangs (TimeoutExpired) is NOT NOPASSWD."""

    def hanging_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        raise subprocess.TimeoutExpired(cmd="sudo", timeout=1)

    monkeypatch.setattr(pv.subprocess, "run", hanging_run)
    _stub_in_sudo_group(monkeypatch, member=True)
    assert detect_privilege() == Privilege.SUDO_PASSWORD


# ---------------------------------------------------------------------------
# build_apt_command
# ---------------------------------------------------------------------------


def test_build_command_root_unwrapped() -> None:
    cmd = build_apt_command(["apt-get", "install", "-y", "htop"], Privilege.ROOT)
    assert cmd == ["apt-get", "install", "-y", "htop"]


def test_build_command_sudo_nopasswd_prepends_n() -> None:
    cmd = build_apt_command(["apt-get", "install", "-y", "htop"], Privilege.SUDO_NOPASSWD)
    assert cmd == ["sudo", "-n", "apt-get", "install", "-y", "htop"]


def test_sudo_nopasswd_probe_clears_cache_then_tests_apt(
    nonroot_euid: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[list[str]] = []

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        seen.append(list(args))
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(pv.subprocess, "run", fake_run)
    assert detect_privilege() == Privilege.SUDO_NOPASSWD
    assert seen[0] == ["sudo", "-k"]
    assert seen[1][:3] == ["sudo", "-n", "apt-get"]


def test_cached_sudo_timestamp_does_not_count_as_nopasswd(
    nonroot_euid: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without ``sudo -k``, a stale timestamp could fool the probe."""

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        # After cache clear, passwordless apt is not available.
        if args[:2] == ["sudo", "-k"]:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout=b"", stderr=b"")
        return subprocess.CompletedProcess(args=args, returncode=1, stdout=b"", stderr=b"")

    monkeypatch.setattr(pv.subprocess, "run", fake_run)
    _stub_in_sudo_group(monkeypatch, member=True)
    assert detect_privilege() == Privilege.SUDO_PASSWORD


def test_build_command_sudo_password_prepends_S_with_silent_prompt() -> None:
    cmd = build_apt_command(["apt-get", "install", "-y", "htop"], Privilege.SUDO_PASSWORD)
    assert cmd == ["sudo", "-S", "-p", "", "apt-get", "install", "-y", "htop"]


def test_build_command_none_raises() -> None:
    with pytest.raises(PermissionError):
        build_apt_command(["apt-get", "install", "-y", "htop"], Privilege.NONE)


# ---------------------------------------------------------------------------
# banner
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("level", list(Privilege))
def test_banner_for_every_level_is_non_empty(level: Privilege) -> None:
    text = banner_for(level)
    assert text
    assert isinstance(text, str)

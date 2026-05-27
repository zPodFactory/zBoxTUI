"""Tests for root password verification."""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from typing import Any

import pytest

from zboxtui.core.utils import privilege as pv
from zboxtui.core.utils.privilege import verify_root_password


@pytest.fixture
def root_euid(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(pv.os, "geteuid", lambda: 0)
    yield


@pytest.fixture
def nonroot_euid(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(pv.os, "geteuid", lambda: 1000)
    yield


def test_empty_password_rejected(root_euid: None) -> None:
    assert verify_root_password("") is False


def test_root_uses_shadow_not_su(
    root_euid: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    called: list[str] = []

    def fake_shadow(password: str) -> bool:
        called.append(password)
        return password == "secret"

    monkeypatch.setattr(pv, "_verify_root_password_shadow", fake_shadow)

    def fail_su(_password: str) -> bool:
        raise AssertionError("su must not be used when euid is 0")

    monkeypatch.setattr(pv, "_verify_root_password_su", fail_su)

    assert verify_root_password("secret") is True
    assert verify_root_password("wrong") is False
    assert called == ["secret", "wrong"]


def test_nonroot_uses_su(nonroot_euid: None, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_su(password: str) -> bool:
        return password == "good"

    monkeypatch.setattr(pv, "_verify_root_password_su", fake_su)

    def fail_shadow(_password: str) -> bool:
        raise AssertionError("shadow check must not run when euid is not 0")

    monkeypatch.setattr(pv, "_verify_root_password_shadow", fail_shadow)

    assert verify_root_password("good") is True
    assert verify_root_password("bad") is False


def test_shadow_rejects_locked_account(root_euid: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pv, "_root_shadow_hash", lambda: "!locked")
    assert verify_root_password("anything") is False


def test_su_invocation(nonroot_euid: None, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert args[0] == ["su", "-c", "true", "root"]
        assert kwargs.get("input") == "pass\n"
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr="")

    monkeypatch.setattr(pv.subprocess, "run", fake_run)
    assert pv._verify_root_password_su("pass") is True

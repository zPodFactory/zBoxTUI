"""Tests for dashboard filesystem filtering."""

from __future__ import annotations

import zboxtui.core.utils.system as system
from zboxtui.core.utils.system import _is_nested_mount_path, get_filesystems


def test_is_nested_mount_path() -> None:
    assert _is_nested_mount_path("/boot", "/") is True
    assert _is_nested_mount_path("/", "/") is False
    assert _is_nested_mount_path("/var", "/") is True


def test_get_filesystems_drops_nested_same_device_mounts(
    monkeypatch, tmp_path
) -> None:
    mounts = tmp_path / "mounts"
    mounts.write_text(
        "/dev/sda1 / ext4 rw 0 0\n"
        "/dev/sda1 /var ext4 ro 0 0\n"
        "/dev/sdb1 /boot ext4 rw 0 0\n",
        encoding="utf-8",
    )

    import builtins

    real_open = builtins.open

    def fake_open(path, *args, **kwargs):
        if path == "/proc/mounts":
            return real_open(mounts, *args, **kwargs)
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", fake_open)
    monkeypatch.setattr(
        system.os.path,
        "isdir",
        lambda p: p in {"/", "/var", "/boot"},
    )

    class Stat:
        f_blocks = 1000
        f_frsize = 4096
        f_bavail = 400

    monkeypatch.setattr(system.os, "statvfs", lambda _p: Stat())

    result = get_filesystems()
    mount_points = {fs.mount_point for fs in result}
    assert mount_points == {"/", "/boot"}

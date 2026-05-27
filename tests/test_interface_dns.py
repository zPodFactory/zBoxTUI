"""Tests for DNS parsing from /etc/network/interfaces."""

from __future__ import annotations

from pathlib import Path

from zboxtui.core.utils.system import get_interface_dns_servers


def test_get_interface_dns_servers_parses_stanza(tmp_path: Path) -> None:
    iface_file = tmp_path / "interfaces"
    iface_file.write_text(
        """auto lo
iface lo inet loopback

auto eth0
iface eth0 inet static
    address 192.168.1.10
    netmask 255.255.255.0
    gateway 192.168.1.1
    dns-nameservers 1.1.1.1 8.8.8.8

auto eth1
iface eth1 inet dhcp
""",
        encoding="utf-8",
    )

    assert get_interface_dns_servers("eth0", interfaces_path=str(iface_file)) == [
        "1.1.1.1",
        "8.8.8.8",
    ]
    assert get_interface_dns_servers("eth1", interfaces_path=str(iface_file)) == []


def test_get_interface_dns_servers_limits_to_two(tmp_path: Path) -> None:
    iface_file = tmp_path / "interfaces"
    iface_file.write_text(
        """iface eth0 inet static
    dns-nameservers 1.1.1.1 8.8.8.8 9.9.9.9
""",
        encoding="utf-8",
    )

    assert get_interface_dns_servers("eth0", interfaces_path=str(iface_file)) == [
        "1.1.1.1",
        "8.8.8.8",
    ]


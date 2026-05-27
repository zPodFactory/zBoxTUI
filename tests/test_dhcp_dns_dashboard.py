"""Tests for DHCP DNS (dnsmasq resolv) and dashboard interface formatting."""

from __future__ import annotations

from pathlib import Path

import pytest

from zboxtui.core.utils.system import (
    NetworkInterface,
    format_dashboard_dns_servers,
    format_dashboard_interface_line,
    format_dashboard_network_iface_lines,
    get_interface_config,
    get_interface_config_mode,
    is_dhcp_interface,
    parse_nameserver_file,
    resolve_interface_dns_servers,
)


def test_parse_nameserver_file(tmp_path: Path) -> None:
    resolv = tmp_path / "resolv.conf"
    resolv.write_text(
        "# comment\nnameserver 192.168.1.1\n\nnameserver 8.8.8.8\n",
        encoding="utf-8",
    )
    assert parse_nameserver_file(str(resolv)) == ["192.168.1.1", "8.8.8.8"]


def test_resolve_interface_dns_servers_dhcp_uses_dnsmasq(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    interfaces = tmp_path / "interfaces"
    interfaces.write_text("iface eth0 inet dhcp\n", encoding="utf-8")
    resolv = tmp_path / "resolv.conf"
    resolv.write_text("nameserver 10.0.0.53\n", encoding="utf-8")

    monkeypatch.setattr(
        "zboxtui.core.utils.system.is_dhcp_interface",
        lambda _name: True,
    )

    servers = resolve_interface_dns_servers(
        "eth0",
        interfaces_path=str(interfaces),
        resolv_path=str(resolv),
    )
    assert servers == ["10.0.0.53"]


def test_resolve_interface_dns_servers_static_uses_interfaces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    interfaces = tmp_path / "interfaces"
    interfaces.write_text(
        "iface eth0 inet static\n"
        "    address 192.168.1.10\n"
        "    dns-nameservers 1.2.3.4 5.6.7.8\n",
        encoding="utf-8",
    )
    resolv = tmp_path / "resolv.conf"
    resolv.write_text("nameserver 10.0.0.53\n", encoding="utf-8")

    monkeypatch.setattr(
        "zboxtui.core.utils.system.is_dhcp_interface",
        lambda _name: False,
    )

    servers = resolve_interface_dns_servers(
        "eth0",
        interfaces_path=str(interfaces),
        resolv_path=str(resolv),
    )
    assert servers == ["1.2.3.4", "5.6.7.8"]


def test_format_dashboard_network_iface_lines_aligned(tmp_path: Path) -> None:
    interfaces = tmp_path / "interfaces"
    interfaces.write_text(
        "iface eth0 inet static\niface eth1 inet dhcp\n",
        encoding="utf-8",
    )
    ifaces = [
        NetworkInterface("eth0", "172.16.42.12", cidr=24, is_dhcp=False),
        NetworkInterface("eth1", "10.10.10.137", cidr=24, is_dhcp=True),
        NetworkInterface("tailscale0", "100.103.60.28", cidr=32, is_dhcp=True),
    ]
    lines = format_dashboard_network_iface_lines(
        ifaces,
        interfaces_path=str(interfaces),
    )
    assert len(lines) == 3
    assert all(line.startswith("  → ") for line in lines)
    assert lines[0].endswith("[STATIC]")
    assert lines[1].endswith("[DHCP]")
    assert lines[2].endswith("[UNMANAGED]")
    # Mode tags share the same column.
    assert lines[0].index("[STATIC]") == lines[1].index("[DHCP]")
    assert lines[1].index("[DHCP]") == lines[2].index("[UNMANAGED]")


def test_format_dashboard_interface_line_unmanaged() -> None:
    iface = NetworkInterface(
        name="tailscale0",
        ipv4="100.103.60.28",
        cidr=32,
        is_dhcp=True,
    )
    assert format_dashboard_interface_line(iface) == "100.103.60.28/32  [UNMANAGED]"


def test_get_interface_config_mode_unmanaged() -> None:
    assert get_interface_config_mode("tailscale0") == "[UNMANAGED]"


def test_format_dashboard_network_routing_lines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from zboxtui.core.utils.system import format_dashboard_network_routing_lines

    monkeypatch.setattr(
        "zboxtui.core.utils.system.resolve_interface_dns_servers",
        lambda _name: ["192.168.1.1", "8.8.8.8"],
    )
    from zboxtui.core.utils.system import RouteEntry

    extra = [RouteEntry("10.20.0.0/24", "10.0.0.1", "eth1")]
    lines = format_dashboard_network_routing_lines(
        "192.168.1.1", "eth0", extra_routes=extra
    )
    assert lines == [
        "Routes:",
        "  → default       via 192.168.1.1  (eth0)",
        "  → 10.20.0.0/24  via 10.0.0.1     (eth1)",
        "",
        "DNS:",
        "  → 192.168.1.1",
        "  → 8.8.8.8",
    ]




def test_format_dashboard_network_routing_filters_routes_to_visible_ifaces() -> None:
    from zboxtui.core.utils.system import RouteEntry, format_dashboard_network_routing_lines

    extra = [RouteEntry("10.20.0.0/24", "10.0.0.1", "eth1")]
    lines = format_dashboard_network_routing_lines(
        "192.168.1.1",
        "eth0",
        extra_routes=extra,
        visible_iface_names=frozenset({"eth0"}),
    )
    assert "10.20.0.0/24" not in "\n".join(lines)
    assert "(eth0)" in "\n".join(lines)

def test_format_dashboard_dns_servers_dhcp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    resolv = tmp_path / "resolv.conf"
    resolv.write_text("nameserver 10.0.0.53\nnameserver 10.0.0.54\n", encoding="utf-8")
    monkeypatch.setattr(
        "zboxtui.core.utils.system.is_dhcp_interface",
        lambda _name: True,
    )
    monkeypatch.setattr(
        "zboxtui.core.utils.system.get_dnsmasq_dns_servers",
        lambda **kwargs: ["10.0.0.53", "10.0.0.54"],
    )
    assert format_dashboard_dns_servers("eth0") == "10.0.0.53, 10.0.0.54"


def test_format_dashboard_dns_servers_none_iface() -> None:
    assert format_dashboard_dns_servers(None) == "-"


def test_is_dhcp_interface_reads_interfaces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import builtins

    interfaces = tmp_path / "interfaces"
    interfaces.write_text(
        "iface eth0 inet dhcp\niface eth1 inet static\n",
        encoding="utf-8",
    )
    real_open = builtins.open

    def fake_open(path, *args, **kwargs):
        if path == "/etc/network/interfaces":
            return real_open(interfaces, *args, **kwargs)
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", fake_open)
    assert is_dhcp_interface("eth0") is True
    assert is_dhcp_interface("eth1") is False
    assert is_dhcp_interface("wt0") is False


def test_get_interface_config_dhcp_dns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    resolv = tmp_path / "resolv.conf"
    resolv.write_text("nameserver 10.0.0.53\nnameserver 10.0.0.54\n", encoding="utf-8")

    monkeypatch.setattr(
        "zboxtui.core.utils.system.get_network_interfaces",
        lambda: [
            NetworkInterface(
                name="eth0",
                ipv4="192.168.1.10",
                gateway="192.168.1.1",
                netmask="255.255.255.0",
                cidr=24,
            )
        ],
    )
    monkeypatch.setattr(
        "zboxtui.core.utils.system.is_dhcp_interface",
        lambda _name: True,
    )
    monkeypatch.setattr(
        "zboxtui.core.utils.system.resolve_interface_dns_servers",
        lambda _name: ["10.0.0.53", "10.0.0.54"],
    )

    cfg = get_interface_config("eth0")
    assert cfg.is_dhcp is True
    assert cfg.dns1 == "10.0.0.53"
    assert cfg.dns2 == "10.0.0.54"

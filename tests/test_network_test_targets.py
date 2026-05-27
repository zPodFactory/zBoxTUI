"""Tests for NetworkTestDialog connectivity target list.

Covers probe order (gateway → configured DNS → Cloudflare → Google) and
deduplication when dns-nameservers in /etc/network/interfaces already
uses 1.1.1.1 and/or 8.8.8.8.
"""

from __future__ import annotations

import pytest

from zboxtui.core.widgets.dcui_dialog import build_network_test_targets


def _patch_gateway(
    monkeypatch: pytest.MonkeyPatch,
    gw: tuple[str | None, str | None],
) -> None:
    monkeypatch.setattr(
        "zboxtui.core.utils.system.get_default_gateway",
        lambda: gw,
    )


def _patch_dns(
    monkeypatch: pytest.MonkeyPatch,
    servers: list[str],
) -> None:
    monkeypatch.setattr(
        "zboxtui.core.utils.system.resolve_interface_dns_servers",
        lambda _iface: servers,
    )


def test_build_network_test_targets_full_order(monkeypatch: pytest.MonkeyPatch) -> None:
    """GW, two custom DNS, then public resolvers when not configured."""
    _patch_gateway(monkeypatch, ("192.168.1.1", "eth0"))
    _patch_dns(monkeypatch, ["10.0.0.53", "10.0.0.54"])

    targets = build_network_test_targets()
    assert [t.host for t in targets] == [
        "192.168.1.1",
        "10.0.0.53",
        "10.0.0.54",
        "1.1.1.1",
        "8.8.8.8",
    ]


def test_build_network_test_targets_skips_both_public_when_in_interfaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No Cloudflare/Google rows when both are dns-nameservers."""
    _patch_gateway(monkeypatch, ("192.168.1.1", "eth0"))
    _patch_dns(monkeypatch, ["1.1.1.1", "8.8.8.8"])

    targets = build_network_test_targets()
    assert [t.host for t in targets] == ["192.168.1.1", "1.1.1.1", "8.8.8.8"]
    labels = " ".join(t.label for t in targets)
    assert "Cloudflare DNS" not in labels
    assert "Google DNS" not in labels
    assert "DNS Server 1 (1.1.1.1):" in labels
    assert "DNS Server 2 (8.8.8.8):" in labels


def test_build_network_test_targets_skips_cloudflare_when_in_interfaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_gateway(monkeypatch, ("10.0.0.1", "eth0"))
    _patch_dns(monkeypatch, ["1.1.1.1", "10.0.0.53"])

    targets = build_network_test_targets()
    assert [t.host for t in targets] == ["10.0.0.1", "1.1.1.1", "10.0.0.53", "8.8.8.8"]
    assert not any("Cloudflare DNS" in t.label for t in targets)
    assert any("Google DNS" in t.label for t in targets)


def test_build_network_test_targets_skips_google_when_in_interfaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_gateway(monkeypatch, ("10.0.0.1", "eth0"))
    _patch_dns(monkeypatch, ["8.8.8.8"])

    targets = build_network_test_targets()
    assert [t.host for t in targets] == ["10.0.0.1", "8.8.8.8", "1.1.1.1"]
    assert not any("Google DNS" in t.label for t in targets)
    assert any("Cloudflare DNS" in t.label for t in targets)


def test_build_network_test_targets_no_gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_gateway(monkeypatch, (None, None))
    _patch_dns(monkeypatch, [])

    targets = build_network_test_targets()
    assert targets[0].host is None
    assert "not found" in targets[0].label
    assert [t.host for t in targets[1:]] == ["1.1.1.1", "8.8.8.8"]


def test_build_network_test_targets_no_configured_dns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_gateway(monkeypatch, ("192.168.0.1", "eth0"))
    _patch_dns(monkeypatch, [])

    targets = build_network_test_targets()
    assert [t.host for t in targets] == ["192.168.0.1", "1.1.1.1", "8.8.8.8"]


def test_build_network_test_targets_skips_duplicate_dns_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Second nameserver row is skipped when it repeats the first IP."""
    _patch_gateway(monkeypatch, ("10.0.0.1", "eth0"))
    _patch_dns(monkeypatch, ["10.0.0.53", "10.0.0.53"])

    targets = build_network_test_targets()
    assert [t.host for t in targets] == ["10.0.0.1", "10.0.0.53", "1.1.1.1", "8.8.8.8"]
    assert sum("DNS Server" in t.label for t in targets) == 1

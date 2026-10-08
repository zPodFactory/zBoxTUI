"""Tests for natural ordering of network interface names."""

from __future__ import annotations

from zboxtui.core.utils.system import interface_sort_key


def test_vlan_ids_sort_numerically() -> None:
    names = [
        "eth0", "eth1.10", "eth1.128", "eth1.192", "eth1.20", "eth1.30", "eth1.64",
    ]
    assert sorted(names, key=interface_sort_key) == [
        "eth0", "eth1.10", "eth1.20", "eth1.30", "eth1.64", "eth1.128", "eth1.192",
    ]


def test_interface_indexes_sort_numerically() -> None:
    names = ["eth10", "eth2", "eth1", "ens192", "ens33"]
    assert sorted(names, key=interface_sort_key) == [
        "ens33", "ens192", "eth1", "eth2", "eth10",
    ]


def test_parent_sorts_before_its_vlans() -> None:
    names = ["eth1.10", "eth1", "eth0.5", "eth0"]
    assert sorted(names, key=interface_sort_key) == [
        "eth0", "eth0.5", "eth1", "eth1.10",
    ]

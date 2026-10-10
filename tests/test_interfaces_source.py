"""interfaces(5) ``source`` / ``source-directory`` support for the mode and DNS readers."""

from __future__ import annotations

from pathlib import Path

from zboxtui.core.utils.system import (
    get_interface_config_mode,
    get_interface_dns_servers,
    is_dhcp_interface,
    read_interfaces_config,
)


def _write_layout(tmp_path: Path, source_line: str) -> str:
    main = tmp_path / "interfaces"
    (tmp_path / "interfaces.d").mkdir()
    (tmp_path / "interfaces.d" / "eth1.42.cfg").write_text(
        "auto eth1.42\niface eth1.42 inet static\n    address 10.173.42.1/28\n"
        "    dns-nameservers 10.173.42.2\n    mtu 1700\n",
        encoding="utf-8",
    )
    (tmp_path / "interfaces.d" / "eth2.cfg").write_text(
        "auto eth2\niface eth2 inet dhcp\n", encoding="utf-8"
    )
    main.write_text(
        f"{source_line}\nauto lo\niface lo inet loopback\n"
        "auto eth0\niface eth0 inet static\n    address 10.60.205.2/26\n",
        encoding="utf-8",
    )
    return str(main)


def test_sourced_stanza_is_static_not_unmanaged(tmp_path: Path) -> None:
    """The VM case: eth1.42 lives in interfaces.d and showed as [UNMANAGED]."""
    main = _write_layout(tmp_path, f"source {tmp_path}/interfaces.d/*")
    assert get_interface_config_mode("eth1.42", interfaces_path=main) == "[STATIC]"
    assert get_interface_config_mode("eth2", interfaces_path=main) == "[DHCP]"
    assert get_interface_config_mode("eth0", interfaces_path=main) == "[STATIC]"
    assert get_interface_config_mode("wt0", interfaces_path=main) == "[UNMANAGED]"
    assert is_dhcp_interface("eth2", interfaces_path=main) is True
    assert is_dhcp_interface("eth1.42", interfaces_path=main) is False
    assert get_interface_dns_servers("eth1.42", interfaces_path=main) == ["10.173.42.2"]


def test_relative_source_resolves_against_the_interfaces_file(tmp_path: Path) -> None:
    main = _write_layout(tmp_path, "source interfaces.d/*")
    assert get_interface_config_mode("eth1.42", interfaces_path=main) == "[STATIC]"


def test_source_directory_takes_only_plain_names(tmp_path: Path) -> None:
    main = _write_layout(tmp_path, f"source-directory {tmp_path}/interfaces.d")
    # "eth1.42.cfg" has dots, which ifupdown's source-directory rule rejects.
    assert get_interface_config_mode("eth1.42", interfaces_path=main) == "[UNMANAGED]"
    (tmp_path / "interfaces.d" / "eth3").write_text(
        "iface eth3 inet static\n", encoding="utf-8"
    )
    assert get_interface_config_mode("eth3", interfaces_path=main) == "[STATIC]"


def test_missing_source_target_and_loops_are_harmless(tmp_path: Path) -> None:
    main = tmp_path / "interfaces"
    main.write_text(
        f"source {tmp_path}/nowhere/*\nsource {main}\niface eth0 inet dhcp\n",
        encoding="utf-8",
    )
    text = read_interfaces_config(str(main))
    assert text.count("iface eth0 inet dhcp") == 1
    assert is_dhcp_interface("eth0", interfaces_path=str(main)) is True


def test_missing_interfaces_file(tmp_path: Path) -> None:
    missing = str(tmp_path / "absent")
    assert read_interfaces_config(missing) == ""
    assert get_interface_config_mode("eth0", interfaces_path=missing) == "[UNMANAGED]"
    assert is_dhcp_interface("eth0", interfaces_path=missing) is False
    assert get_interface_dns_servers("eth0", interfaces_path=missing) == []

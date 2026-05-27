"""Privileged host control actions (reboot, interface apply)."""

from __future__ import annotations

import re
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from .logging import get_logger
from .privilege import Privilege, run_privileged_command

log = get_logger("system_control")

INTERFACES_FILE = Path("/etc/network/interfaces")

REBOOT_CMD: Sequence[str] = ("systemctl", "reboot",)


def reboot_system(
    privilege: Privilege,
    *,
    password: str | None = None,
) -> tuple[bool, str]:
    """Reboot the host (TUI will exit when the system goes down)."""
    ok, _ = run_privileged_command(
        REBOOT_CMD,
        privilege,
        password=password,
        timeout=15,
    )
    if ok:
        return True, "System is rebooting."
    return False, _


@dataclass(frozen=True)
class NetworkApplyRequest:
    """Parameters for writing ``/etc/network/interfaces`` and raising an iface."""

    interface: str
    dhcp: bool
    ip: str = ""
    netmask: str = ""
    gateway: str = ""
    dns1: str = ""
    dns2: str = ""


def _missing_commands(*names: str) -> list[str]:
    return [name for name in names if shutil.which(name) is None]


def apply_network_interface(
    req: NetworkApplyRequest,
    *,
    interfaces_file: Path = INTERFACES_FILE,
) -> tuple[bool, str]:
    """Write interface stanza and restart the link with ifupdown.

    Returns ``(ok, message)`` where ``message`` is user-facing (success or error).
    """
    iface = req.interface
    missing = _missing_commands("ifup", "ifdown")
    if missing:
        return False, f"Required command(s) not found: {', '.join(missing)}"

    try:
        backup_file = interfaces_file.with_suffix(interfaces_file.suffix + ".bak")
        try:
            shutil.copy(interfaces_file, backup_file)
            log.info("Backed up %s to %s", interfaces_file, backup_file)
        except FileNotFoundError:
            log.warning("No existing %s to backup", interfaces_file)

        try:
            existing_content = interfaces_file.read_text(encoding="utf-8")
        except FileNotFoundError:
            existing_content = ""

        if req.dhcp:
            new_iface_config = f"auto {iface}\niface {iface} inet dhcp\n"
        else:
            dns_line = ""
            if req.dns1 or req.dns2:
                dns_servers = " ".join(filter(None, [req.dns1, req.dns2]))
                dns_line = f"    dns-nameservers {dns_servers}\n"
            new_iface_config = (
                f"auto {iface}\n"
                f"iface {iface} inet static\n"
                f"    address {req.ip}\n"
                f"    netmask {req.netmask}\n"
                f"    gateway {req.gateway}\n"
                f"{dns_line}"
            )

        iface_escaped = re.escape(iface)
        pattern = (
            rf"(auto\s+{iface_escaped}\n)?"
            rf"iface\s+{iface_escaped}\s+inet\s+\w+[^\n]*\n"
            r"(?:\s+[^\n]+\n)*"
        )
        new_content = re.sub(pattern, "", existing_content)

        if new_content and not new_content.endswith("\n"):
            new_content += "\n"
        if new_content and not new_content.endswith("\n\n"):
            new_content += "\n"

        new_content += new_iface_config
        interfaces_file.write_text(new_content, encoding="utf-8")
        log.info("Wrote new interface config to %s", interfaces_file)

        if not req.dhcp and shutil.which("dhclient"):
            log.debug("Releasing DHCP lease for %s", iface)
            subprocess.run(
                ["dhclient", "-r", iface],
                capture_output=True,
                timeout=10,
                check=False,
            )

        log.debug("Flushing addresses from %s", iface)
        subprocess.run(
            ["ip", "addr", "flush", "dev", iface],
            capture_output=True,
            timeout=10,
            check=False,
        )

        subprocess.run(
            ["ifdown", "--force", iface],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

        result = subprocess.run(
            ["ifup", iface],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "ifup failed"
            log.error("ifup %s failed: %s", iface, detail)
            return False, detail

        log.info("Interface %s configured successfully", iface)
        return (
            True,
            f"Network configuration for {iface} has been applied successfully.",
        )

    except PermissionError:
        log.error("Permission denied modifying %s", interfaces_file)
        return False, "Permission denied. Run as root."
    except subprocess.TimeoutExpired:
        log.error("Interface restart timed out for %s", iface)
        return False, "Interface restart timed out"
    except FileNotFoundError as exc:
        log.error("Missing file or command during network apply: %s", exc)
        target = getattr(exc, "filename", None) or str(exc)
        return False, f"Required file or command not found: {target}"
    except OSError as exc:
        log.exception("OS error applying network config: %s", exc)
        return False, str(exc)

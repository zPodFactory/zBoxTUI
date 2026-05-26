"""Privileged host control actions (networking restart, reboot)."""

from __future__ import annotations

from collections.abc import Sequence

from .privilege import Privilege, run_privileged_command

NETWORKING_RESTART_CMD: Sequence[str] = ("systemctl", "restart", "networking")
REBOOT_CMD: Sequence[str] = ("systemctl", "reboot",)


def restart_networking(
    privilege: Privilege,
    *,
    password: str | None = None,
) -> tuple[bool, str]:
    """Restart Debian ``networking.service`` to apply interface config."""
    ok, _ = run_privileged_command(
        NETWORKING_RESTART_CMD,
        privilege,
        password=password,
        timeout=60,
    )
    if ok:
        return True, "Network services restarted."
    return False, _


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

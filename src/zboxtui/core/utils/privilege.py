"""Privilege detection + apt subprocess argv construction.

The Configure Packages dialog needs to run ``apt-get`` as root. The
current user is one of:

* **root** (``geteuid() == 0``) — run apt-get directly, no wrapper.
* **sudo with NOPASSWD** — ``sudo -n apt-get`` succeeds even after clearing
  any cached sudo timestamp (see :func:`_sudo_nopasswd_works`).
* **sudo with password required** — the user is in the ``sudo``/``wheel``
  group but ``sudo -n`` fails once cached credentials are dropped. We
  prompt for the password separately and feed it to ``sudo -S`` over stdin.
* **none** — can't elevate. The dialog disables Apply and shows a
  banner asking the user to relaunch as root.

The :func:`detect_privilege` function probes for the right one;
:func:`build_apt_command` wraps an apt argv accordingly. Both are kept
narrow and pure (no Textual imports) so they can be unit-tested with
``subprocess`` monkeypatched.
"""

from __future__ import annotations

import contextlib
import grp
import os
import subprocess
from collections.abc import Sequence
from enum import Enum, auto


class Privilege(Enum):
    """How the current user can run privileged commands."""

    ROOT = auto()
    SUDO_NOPASSWD = auto()
    SUDO_PASSWORD = auto()
    NONE = auto()


SUDO_GROUPS = {"sudo", "wheel", "admin"}


def _user_in_sudoers_group() -> bool:
    """True if any of the current user's groups is a known sudo group."""
    try:
        gids = {os.getegid(), *os.getgroups()}
    except OSError:
        return False
    group_names: set[str] = set()
    for gid in gids:
        try:
            group_names.add(grp.getgrgid(gid).gr_name)
        except KeyError:
            continue
    return bool(group_names & SUDO_GROUPS)


def _sudo_nopasswd_works(timeout: float = 3.0) -> bool:
    """Probe whether ``sudo -n apt-get`` works without a password.

    Runs ``sudo -k`` first so a *cached* sudo timestamp from an earlier
    terminal session cannot masquerade as NOPASSWD.  Real NOPASSWD rules
    in sudoers still pass ``sudo -n`` after ``-k``; password-only users
    do not.
    """
    with contextlib.suppress(subprocess.TimeoutExpired, FileNotFoundError, OSError):
        subprocess.run(
            ["sudo", "-k"],
            capture_output=True,
            timeout=timeout,
            check=False,
        )

    try:
        result = subprocess.run(
            ["sudo", "-n", "apt-get", "-s", "update"],
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False
    return result.returncode == 0


def detect_privilege() -> Privilege:
    """Return how the current process can run privileged commands.

    Probes are ordered cheapest-first: euid check, then a ``sudo -n``
    probe (no password required), then a group-membership check (the
    user *can* sudo but will be prompted for a password).
    """
    if os.geteuid() == 0:
        return Privilege.ROOT
    if _sudo_nopasswd_works():
        return Privilege.SUDO_NOPASSWD
    if _user_in_sudoers_group():
        return Privilege.SUDO_PASSWORD
    return Privilege.NONE


def build_apt_command(
    argv: Sequence[str],
    privilege: Privilege,
) -> list[str]:
    """Wrap a bare apt-get argv with the right sudo prefix for this privilege.

    Examples:
        ROOT          ["apt-get", "install", "-y", "htop"]
                   -> ["apt-get", "install", "-y", "htop"]
        SUDO_NOPASSWD ["apt-get", "install", "-y", "htop"]
                   -> ["sudo", "-n", "apt-get", "install", "-y", "htop"]
        SUDO_PASSWORD ["apt-get", "install", "-y", "htop"]
                   -> ["sudo", "-S", "-p", "", "apt-get", "install", "-y", "htop"]
                      (caller pipes the password to stdin)
    """
    cmd = list(argv)
    if privilege == Privilege.ROOT:
        return cmd
    if privilege == Privilege.SUDO_NOPASSWD:
        return ["sudo", "-n", *cmd]
    if privilege == Privilege.SUDO_PASSWORD:
        # -S reads the password from stdin; -p "" silences the prompt so
        # nothing leaks into the captured stdout/stderr.
        return ["sudo", "-S", "-p", "", *cmd]
    raise PermissionError(
        "Cannot run privileged commands: current user is not root and not in any sudo group."
    )


def banner_for(privilege: Privilege) -> str:
    """One-line human-readable description of how we'll run apt."""
    if privilege == Privilege.ROOT:
        return "Running as root — apt-get commands run directly."
    if privilege == Privilege.SUDO_NOPASSWD:
        return "Sudo NOPASSWD configured — apt-get commands run via sudo."
    if privilege == Privilege.SUDO_PASSWORD:
        return "Sudo requires your password — you'll be prompted before Apply."
    return (
        "No privilege available. Relaunch zboxtui as root, or add yourself to "
        "the sudo group, to install or remove packages."
    )

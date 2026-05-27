"""Privilege detection + subprocess argv construction for root commands.

Menu actions (apt, systemctl, reboot) need to run as root. The current
user is one of:

* **root** (``geteuid() == 0``) — run apt-get directly, no wrapper.
* **sudo with NOPASSWD** — ``sudo -n apt-get`` succeeds even after clearing
  any cached sudo timestamp (see :func:`_sudo_nopasswd_works`).
* **sudo with password required** — the user is in the ``sudo``/``wheel``
  group but ``sudo -n`` fails once cached credentials are dropped. We
  prompt for the password separately and feed it to ``sudo -S`` over stdin.
* **none** — can't elevate. The dialog disables Apply and shows a
  banner asking the user to relaunch as root.

The :func:`detect_privilege` function probes for the right one;
:func:`build_privileged_command` wraps a command argv accordingly.
Both are kept narrow and pure (no Textual imports) so they can be
unit-tested with ``subprocess`` monkeypatched.
"""

from __future__ import annotations

import contextlib
import grp
import os
import subprocess
from collections.abc import Sequence
from enum import Enum, auto

NO_PRIVILEGE_MSG = (
    "You need root or sudo access to run this action.\n"
    "Relaunch zboxtui as root, or add yourself to the sudo group."
)


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


def build_privileged_command(argv: Sequence[str], privilege: Privilege) -> list[str]:
    """Wrap a command argv with the right sudo prefix for this privilege."""
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


def build_apt_command(argv: Sequence[str], privilege: Privilege) -> list[str]:
    """Alias for :func:`build_privileged_command` (apt-get callers)."""
    return build_privileged_command(argv, privilege)


def run_privileged_command(
    argv: Sequence[str],
    privilege: Privilege,
    *,
    password: str | None = None,
    timeout: float = 120,
) -> tuple[bool, str]:
    """Run ``argv`` elevated; return ``(ok, message)`` for display in a dialog."""
    if privilege == Privilege.NONE:
        return False, NO_PRIVILEGE_MSG
    try:
        cmd = build_privileged_command(argv, privilege)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            input=f"{password}\n" if password else None,
        )
    except subprocess.TimeoutExpired:
        return False, "Command timed out"
    except OSError as exc:
        return False, str(exc)
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "command failed").strip()
        return False, err.splitlines()[0] if err else f"Exit code {result.returncode}"
    return True, "OK"


def _root_shadow_hash() -> str | None:
    """Return root's hashed password field from ``/etc/shadow`` (root-only)."""
    try:
        with open("/etc/shadow", encoding="utf-8") as f:
            for line in f:
                if line.startswith("root:"):
                    return line.split(":", 2)[1]
    except OSError:
        return None
    return None


def _libc_crypt(password: str, setting: str) -> str | None:
    """Hash ``password`` with libc ``crypt(3)`` (no deprecated stdlib ``crypt``)."""
    import ctypes
    import ctypes.util

    libname = ctypes.util.find_library("crypt")
    if not libname:
        return None
    libcrypt = ctypes.CDLL(libname, use_errno=True)
    libcrypt.crypt.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
    libcrypt.crypt.restype = ctypes.c_char_p
    result = libcrypt.crypt(password.encode("utf-8"), setting.encode("utf-8"))
    if not result:
        return None
    return ctypes.string_at(result).decode("utf-8")


def _verify_root_password_shadow(password: str) -> bool:
    """Check password against root's shadow hash when already running as root."""
    hashed = _root_shadow_hash()
    if not hashed or hashed[0] in "!*":
        return False
    computed = _libc_crypt(password, hashed)
    return computed == hashed


def _verify_root_password_su(password: str) -> bool:
    """Check password via ``su`` (PAM-backed on Debian)."""
    try:
        result = subprocess.run(
            ["su", "-c", "true", "root"],
            input=f"{password}\n",
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        return False
    except FileNotFoundError:
        return False
    except OSError:
        return False



def sudo_timestamp_valid(timeout: float = 3.0) -> bool:
    """Return True when sudo would not prompt for a password (active timestamp).

    Uses ``sudo -n -v`` — same probe sudo uses before running a cached command.
    """
    try:
        result = subprocess.run(
            ["sudo", "-n", "-v"],
            capture_output=True,
            timeout=timeout,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False



def verify_root_password(password: str) -> bool:
    """Return True if ``password`` is the root password.

    When zBoxTUI runs as root, ``su`` does not validate the password (root may
    switch to root without one). In that case compare against the shadow hash.
    """
    if not password:
        return False
    if os.geteuid() == 0:
        return _verify_root_password_shadow(password)
    return _verify_root_password_su(password)

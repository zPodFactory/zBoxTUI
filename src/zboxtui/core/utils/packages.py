"""Curated package catalog: loader + display formatting.

The catalog is a JSON file (see ``data/packages.schema.json``) listing
packages grouped by category. Each package is one of three ``type``s —
``apt``, ``github_release``, ``script`` — and zBoxTUI's Configure
Packages dialog renders + applies the curated picks.

This module is intentionally split into two halves:

* **Data classes + loading**: pure, no I/O beyond reading the JSON file.
* **Display formatting**: pure functions (no Textual widgets) so the row
  rendering and "last updated" string can be exercised by unit tests
  without spinning up the full app.

The dialog widget that consumes these lives in core/menu_items/packages.py.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, auto
from pathlib import Path
from typing import Literal, Sequence

from rich.text import Text

SUPPORTED_SCHEMA_VERSION = 1
PackageType = Literal["apt", "github_release", "script"]

# System-wide catalog override, mirroring SYSTEM_CONFIG_PATH for app.conf.
SYSTEM_CATALOG_PATH = "/etc/zboxtui/packages.json"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CuratedPackage:
    """A single curated package entry from the catalog.

    Optional fields are populated only for the ``type``s that need them
    (``version``/``github_repo`` for ``github_release``, etc.). The schema
    validator on the catalog repo guarantees the right combinations land
    here, so consumers can rely on the per-type contract documented in
    ``data/packages.schema.json``.
    """

    type: PackageType
    name: str
    description: str
    locked: bool = False

    # Optional, per-type fields
    version: str | None = None
    github_repo: str | None = None
    binary: str | None = None
    version_command: str | None = None
    version_pattern: str | None = None
    install_command: str | None = None
    uninstall_command: str | None = None


@dataclass(frozen=True)
class Group:
    """A named section in the catalog (rendered as ``[ name ]`` in the picker)."""

    name: str
    description: str
    packages: tuple[CuratedPackage, ...]


@dataclass(frozen=True)
class Catalog:
    """The full curated catalog."""

    schema_version: int
    updated_at: datetime | None
    groups: tuple[Group, ...]
    source_path: Path | None = field(default=None, compare=False)

    def iter_packages(self) -> list[CuratedPackage]:
        """Flatten across groups in display order."""
        return [pkg for g in self.groups for pkg in g.packages]


class CatalogError(Exception):
    """Raised when a catalog file is missing, malformed, or unsupported."""


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def load_catalog(path: str | Path) -> Catalog:
    """Read a catalog JSON file and return a :class:`Catalog`.

    Raises :class:`CatalogError` on missing file, invalid JSON, unsupported
    ``schema_version``, or structural problems the dataclass constructors
    can detect (missing required fields, wrong types).
    """
    p = Path(path)
    if not p.is_file():
        raise CatalogError(f"Catalog file not found: {p}")

    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CatalogError(f"Catalog is not valid JSON ({p}): {exc}") from exc

    if not isinstance(raw, dict):
        raise CatalogError(f"Catalog root must be an object ({p})")

    schema_version = raw.get("schema_version")
    if schema_version != SUPPORTED_SCHEMA_VERSION:
        raise CatalogError(
            f"Unsupported schema_version {schema_version!r}; "
            f"this build understands {SUPPORTED_SCHEMA_VERSION}"
        )

    updated_at = _parse_iso8601(raw.get("updated_at"))

    groups_raw = raw.get("groups")
    if not isinstance(groups_raw, list) or not groups_raw:
        raise CatalogError("Catalog must contain a non-empty 'groups' array")

    groups = tuple(_parse_group(g) for g in groups_raw)
    return Catalog(
        schema_version=schema_version,
        updated_at=updated_at,
        groups=groups,
        source_path=p,
    )


def _parse_iso8601(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise CatalogError(f"'updated_at' must be a string, got {type(value).__name__}")
    # Accept both "...Z" and "...+00:00"; fromisoformat handles +00:00 directly,
    # and Z is normalized to +00:00 here.
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise CatalogError(f"'updated_at' is not a valid ISO-8601 timestamp: {value!r}") from exc


def _parse_group(raw: object) -> Group:
    if not isinstance(raw, dict):
        raise CatalogError(f"Group must be an object, got {type(raw).__name__}")
    name = raw.get("name")
    if not isinstance(name, str) or not name:
        raise CatalogError("Group must have a non-empty 'name'")
    description = raw.get("description", "")
    packages_raw = raw.get("packages")
    if not isinstance(packages_raw, list) or not packages_raw:
        raise CatalogError(f"Group {name!r} must contain a non-empty 'packages' array")
    packages = tuple(_parse_package(p, group=name) for p in packages_raw)
    return Group(name=name, description=description, packages=packages)


def _parse_package(raw: object, *, group: str) -> CuratedPackage:
    if not isinstance(raw, dict):
        raise CatalogError(f"Package in group {group!r} must be an object")
    pkg_type = raw.get("type")
    if pkg_type not in ("apt", "github_release", "script"):
        raise CatalogError(f"Package in group {group!r} has unknown type {pkg_type!r}")
    name = raw.get("name")
    if not isinstance(name, str) or not name:
        raise CatalogError(f"Package in group {group!r} must have a non-empty 'name'")
    description = raw.get("description", "")
    return CuratedPackage(
        type=pkg_type,
        name=name,
        description=description,
        locked=bool(raw.get("locked", False)),
        version=raw.get("version"),
        github_repo=raw.get("github_repo"),
        binary=raw.get("binary"),
        version_command=raw.get("version_command"),
        version_pattern=raw.get("version_pattern"),
        install_command=raw.get("install_command"),
        uninstall_command=raw.get("uninstall_command"),
    )


# ---------------------------------------------------------------------------
# Install state
# ---------------------------------------------------------------------------


class InstallState(Enum):
    """What's true on disk *right now* for a curated package."""

    NOT_INSTALLED = auto()
    INSTALLED = auto()
    UPGRADE_AVAILABLE = auto()


@dataclass(frozen=True)
class PackageState:
    """Detected install state for one curated package."""

    state: InstallState
    installed_version: str | None = None
    candidate_version: str | None = None  # set when UPGRADE_AVAILABLE

    @property
    def is_installed(self) -> bool:
        return self.state in (InstallState.INSTALLED, InstallState.UPGRADE_AVAILABLE)


# ---------------------------------------------------------------------------
# Display formatting (pure — no I/O, no Textual)
# ---------------------------------------------------------------------------

# Checkbox symbols used in the picker. Four states are possible:
#   [x] currently installed AND user wants it installed  -> no-op
#   [ ] currently absent    AND user wants it absent     -> no-op
#   [+] currently absent    AND user wants to install    -> pending install
#   [-] currently installed AND user wants to remove     -> pending remove
#   [↑] upgrade available   AND user keeps it installed  -> pending upgrade
CHECKBOX_INSTALLED = "[x]"
CHECKBOX_ABSENT = "[ ]"
CHECKBOX_PENDING_INSTALL = "[+]"
CHECKBOX_PENDING_REMOVE = "[-]"
CHECKBOX_PENDING_UPGRADE = "[↑]"

# Visual separators / indicators used in the picker row formatter.
UPGRADE_ARROW = "→"
UPGRADE_INDICATOR = "↑"


def _truncate_display(text: str, max_len: int) -> str:
    """Trim text for a fixed-width TUI column, adding an ellipsis when needed."""
    if max_len <= 0:
        return ""
    if len(text) <= max_len:
        return text
    if max_len == 1:
        return "…"
    return text[: max_len - 1] + "…"


def checkbox_for(state: PackageState, target_checked: bool) -> str:
    """Pick the right [x]/[ ]/[+]/[-]/[↑] symbol given current + target state."""
    if state.state == InstallState.UPGRADE_AVAILABLE and target_checked:
        return CHECKBOX_PENDING_UPGRADE
    if state.is_installed and target_checked:
        return CHECKBOX_INSTALLED
    if not state.is_installed and not target_checked:
        return CHECKBOX_ABSENT
    if state.is_installed and not target_checked:
        return CHECKBOX_PENDING_REMOVE
    return CHECKBOX_PENDING_INSTALL


@dataclass(frozen=True)
class PackageChangeSet:
    """Install / remove / upgrade diff between targets and detected state."""

    to_install: tuple[str, ...] = ()
    to_remove: tuple[str, ...] = ()
    to_upgrade: tuple[str, ...] = ()

    @property
    def has_changes(self) -> bool:
        return bool(self.to_install or self.to_remove or self.to_upgrade)

    def install_names(self) -> list[str]:
        """Names to pass to apt install (new installs + upgrades)."""
        return [*self.to_install, *self.to_upgrade]


def compute_package_changes(
    packages: Sequence[CuratedPackage],
    states: dict[str, PackageState],
    targets: dict[str, bool],
) -> PackageChangeSet:
    """Compute pending install, remove, and upgrade sets from picker targets."""
    to_install: list[str] = []
    to_remove: list[str] = []
    to_upgrade: list[str] = []
    for pkg in packages:
        state = states.get(pkg.name)
        if state is None:
            continue
        target = targets.get(pkg.name, state.is_installed)
        if state.state == InstallState.UPGRADE_AVAILABLE and target:
            to_upgrade.append(pkg.name)
        elif target and not state.is_installed:
            to_install.append(pkg.name)
        elif not target and state.is_installed:
            to_remove.append(pkg.name)
    return PackageChangeSet(
        tuple(to_install),
        tuple(to_remove),
        tuple(to_upgrade),
    )


def format_pending_changes_summary(changes: PackageChangeSet) -> tuple[str, bool]:
    """Return ``(status_text, highlight)`` for the picker status bar."""
    if not changes.has_changes:
        return "No pending changes.", False
    parts: list[str] = []
    if changes.to_install:
        parts.append(f"+{len(changes.to_install)} install")
    if changes.to_upgrade:
        parts.append(f"↑{len(changes.to_upgrade)} upgrade")
    if changes.to_remove:
        parts.append(f"-{len(changes.to_remove)} remove")
    names = [*changes.to_install, *changes.to_upgrade, *changes.to_remove]
    summary = " · ".join(parts)
    if len(names) <= 4:
        summary = f"{summary} ({', '.join(names)})"
    return f"Pending: {summary} — Enter to apply", True


def format_system_state(state: PackageState) -> str:
    """Human-readable install/version status for detail views."""
    if state.state == InstallState.UPGRADE_AVAILABLE:
        inst = state.installed_version or "unknown"
        cand = state.candidate_version or "unknown"
        return f"Installed ({inst}); upgrade available ({cand})"
    if state.state == InstallState.INSTALLED:
        ver = state.installed_version or "unknown version"
        return f"Installed ({ver})"
    if state.candidate_version:
        return f"Not installed (available: {state.candidate_version})"
    return "Not installed"


def format_selection_status(state: PackageState, target_checked: bool) -> str:
    """Explain what will happen to this package when the user applies."""
    if state.state == InstallState.UPGRADE_AVAILABLE and target_checked:
        return "Will upgrade on apply"
    if state.is_installed and target_checked:
        return "Keep installed (no change)"
    if not state.is_installed and not target_checked:
        return "Leave absent (no change)"
    if state.is_installed and not target_checked:
        return "Marked for removal"
    return "Marked for install"


def format_package_detail_body(
    pkg: CuratedPackage,
    state: PackageState,
    *,
    group_name: str = "",
    group_description: str = "",
    target_checked: bool | None = None,
) -> str:
    """Build scrollable detail text for the package info overlay."""
    target = target_checked if target_checked is not None else state.is_installed
    lines: list[str] = []

    if group_name:
        lines.append(f"Category: {group_name}")
    if group_description:
        lines.append(group_description)
    if lines:
        lines.append("")

    lines.extend(
        [
            "Description",
            pkg.description or "(none)",
            "",
            f"Package type: {pkg.type}",
            f"System state: {format_system_state(state)}",
            f"Selection: {format_selection_status(state, target)}",
        ]
    )

    if pkg.locked:
        lines.extend(["", "Locked in catalog — cannot be removed via the picker."])
    if pkg.type == "github_release" and pkg.github_repo:
        lines.append(f"GitHub repository: {pkg.github_repo}")
    if pkg.version:
        lines.append(f"Catalog version pin: {pkg.version}")

    return "\n".join(lines)


def version_cell(state: PackageState) -> str:
    """Format the version cell as plain text — useful for tests/logging."""
    if state.state == InstallState.UPGRADE_AVAILABLE:
        inst = state.installed_version or ""
        cand = state.candidate_version or ""
        return f"{inst} {UPGRADE_ARROW} {cand}"
    if state.state == InstallState.INSTALLED:
        return state.installed_version or ""
    return state.candidate_version or ""


def _append_version_part(
    text: Text,
    state: PackageState,
    *,
    width: int,
    upgrade_style: str,
) -> None:
    """Append a fixed-width version column (may include styled upgrade target)."""
    if width <= 0:
        return

    if state.state == InstallState.UPGRADE_AVAILABLE:
        inst = state.installed_version or ""
        cand = state.candidate_version or ""
        prefix = f"{inst} {UPGRADE_ARROW} "
        full = prefix + cand
        if len(full) > width:
            text.append(_truncate_display(full, width))
            return
        text.append(prefix)
        text.append(cand, style=upgrade_style)
        text.append(" " * (width - len(full)))
        return

    plain = version_cell(state)
    text.append(plain.ljust(width))


def format_package_picker_line(
    pkg: CuratedPackage,
    state: PackageState,
    target_checked: bool,
    *,
    name_width: int = 20,
    version_width: int = 18,
    desc_width: int = 44,
    upgrade_style: str = "bold green",
) -> Text:
    """Build one picker row: checkbox, name, version, and truncated description.

    Example::

        ``[↑] docker-ce          27.3.1 → 29.5.2   Docker Engine — daemon, CLI…``
    """
    cb = checkbox_for(state, target_checked)
    name = _truncate_display(pkg.name, name_width).ljust(name_width)
    line = Text()
    line.append(f"{cb} {name}  ")
    _append_version_part(
        line,
        state,
        width=version_width,
        upgrade_style=upgrade_style,
    )
    if desc_width > 0:
        line.append(f"  {_truncate_display(pkg.description, desc_width)}")
    return line


def format_package_row(
    pkg: CuratedPackage,
    state: PackageState,
    target_checked: bool,
    *,
    name_width: int = 25,
    version_width: int = 12,
    upgrade_style: str = "bold green",
) -> Text:
    """Backward-compatible alias — name + version only (no description column)."""
    return format_package_picker_line(
        pkg,
        state,
        target_checked,
        name_width=name_width,
        version_width=version_width,
        desc_width=0,
        upgrade_style=upgrade_style,
    )


def format_catalog_freshness(updated_at: datetime | None, now: datetime) -> str:
    """Human-readable "last updated" string for the catalog header.

    Examples:
        "Last update: 2026-05-22 (today)"
        "Last update: 2026-05-19 (3 days ago)"
        "Last update: 2025-11-22 (~6 months ago — Refresh recommended)"
        "Last update: unknown"
    """
    if updated_at is None:
        return "Last update: unknown"

    # Normalize to UTC-aware so subtraction always works regardless of how
    # the catalog wrote it (date-only ISO strings end up naive).
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)

    date_str = updated_at.strftime("%Y-%m-%d")
    delta_days = (now.date() - updated_at.date()).days

    if delta_days < 0:
        # Future timestamp — clock skew or test data. Just show the date.
        return f"Last update: {date_str}"
    if delta_days == 0:
        rel = "today"
    elif delta_days == 1:
        rel = "yesterday"
    elif delta_days < 30:
        rel = f"{delta_days} days ago"
    elif delta_days < 365:
        months = delta_days // 30
        rel = f"~{months} month{'s' if months != 1 else ''} ago"
    else:
        years = delta_days // 365
        rel = f"~{years} year{'s' if years != 1 else ''} ago"

    if delta_days >= 60:
        # Past two months — nudge the user toward a Refresh.
        rel = f"{rel} — Refresh recommended"

    return f"Last update: {date_str} ({rel})"


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


def cached_catalog_path() -> Path:
    """Where Phase 3 will write a refreshed catalog: $XDG_CACHE_HOME/zboxtui/packages.json
    or ~/.cache/zboxtui/packages.json."""
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".cache"
    return base / "zboxtui" / "packages.json"


def shipped_catalog_path() -> Path:
    """The catalog bundled with the package itself."""
    return Path(__file__).resolve().parent.parent.parent / "data" / "packages.json"


def resolve_catalog_path(explicit: str | None = None) -> Path:
    """Pick the catalog file to load, highest priority first.

    1. ``explicit`` argument (e.g. a future ``--packages`` CLI flag).
    2. ``$ZBOXTUI_PACKAGES`` environment variable.
    3. The Phase-3 cache at ``~/.cache/zboxtui/packages.json``.
    4. The system-wide override at ``/etc/zboxtui/packages.json``.
    5. The shipped default that comes with the package.

    Always returns a path; the caller may still get a :class:`CatalogError`
    when loading if the resolved file is corrupt.
    """
    if explicit:
        return Path(explicit)
    env = os.environ.get("ZBOXTUI_PACKAGES")
    if env:
        return Path(env)
    cached = cached_catalog_path()
    if cached.is_file():
        return cached
    system = Path(SYSTEM_CATALOG_PATH)
    if system.is_file():
        return system
    return shipped_catalog_path()


# ---------------------------------------------------------------------------
# Version-string simplification
# ---------------------------------------------------------------------------


def simplify_apt_version(version: str) -> str:
    """Trim Debian-isms out of an apt version string for display.

    Debian package versions look like ``[epoch:]upstream[-debian_revision]``
    with optional distribution suffixes (``~debian.13~trixie``, ``~deb13u1``,
    ``~bpo12+1``, ``+deb12u1``, etc.). Those bits matter for the package
    manager but just add noise in a TUI row, so we strip:

      * the epoch prefix (``5:`` in ``5:29.5.2-1~debian.13~trixie``)
      * anything starting with ``~`` or ``+deb`` (the distribution suffix)

    The Debian revision (``-1``, ``-0.1``) is kept because it can move
    independently of upstream and is short.

    Examples:
        ``5:29.5.2-1~debian.13~trixie`` -> ``29.5.2-1``
        ``1:1.3.2-0.1``                 -> ``1.3.2-0.1``
        ``2.34-3~bpo12+1``              -> ``2.34-3``
        ``1.6.6+ds-1+deb13u1``          -> ``1.6.6+ds-1``
        ``1.98.3``                      -> ``1.98.3``
    """
    if not version:
        return version
    # Strip leading epoch (digits + ":").
    head, sep, tail = version.partition(":")
    if sep and head.isdigit():
        version = tail
    # Strip distribution suffix at the first '~' or '+deb'.
    cut = len(version)
    tilde = version.find("~")
    if tilde >= 0:
        cut = min(cut, tilde)
    plus_deb = version.find("+deb")
    if plus_deb >= 0:
        cut = min(cut, plus_deb)
    return version[:cut]


# ---------------------------------------------------------------------------
# State detection (subprocess wrappers — kept narrow and testable by isolation)
# ---------------------------------------------------------------------------


def query_apt_state(package_names: list[str]) -> dict[str, PackageState]:
    """One ``apt-cache policy`` call covers every apt package in the catalog.

    Parses the per-package blocks for ``Installed:`` and ``Candidate:`` lines.
    A package not installed is reported as :class:`InstallState.NOT_INSTALLED`.
    A package whose installed version differs from its candidate is reported
    as :class:`InstallState.UPGRADE_AVAILABLE`. On systems without
    ``apt-cache`` (or on timeout), every package is reported as
    ``NOT_INSTALLED`` so the caller degrades gracefully.
    """
    result: dict[str, PackageState] = {
        name: PackageState(state=InstallState.NOT_INSTALLED) for name in package_names
    }
    if not package_names:
        return result

    try:
        proc = subprocess.run(
            ["apt-cache", "policy", *package_names],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return result

    current: str | None = None
    installed: str | None = None
    candidate: str | None = None

    def flush() -> None:
        if current and current in result:
            result[current] = _state_from_versions(installed, candidate)

    for line in proc.stdout.splitlines():
        # Package-block header: zero-indented "name:" line.
        if line and not line[0].isspace() and line.rstrip().endswith(":"):
            flush()
            current = line.rstrip()[:-1]
            installed = None
            candidate = None
            continue
        stripped = line.strip()
        if stripped.startswith("Installed:"):
            installed = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("Candidate:"):
            candidate = stripped.split(":", 1)[1].strip()
    flush()
    return result


def _state_from_versions(installed: str | None, candidate: str | None) -> PackageState:
    """Convert apt-cache policy's per-package strings into a PackageState.

    Comparison happens on the *raw* strings (so the package manager's
    full version semantics decide whether it's an upgrade), but the
    versions stored on PackageState are simplified for display.
    `candidate_version` is captured for every state — even NOT_INSTALLED —
    so the dialog can show "this is what would be installed".
    """
    candidate_short = (
        simplify_apt_version(candidate)
        if candidate and candidate != "(none)"
        else None
    )

    if installed in (None, "", "(none)"):
        return PackageState(
            state=InstallState.NOT_INSTALLED,
            candidate_version=candidate_short,
        )
    installed_short = simplify_apt_version(installed) if installed else None
    is_upgrade = bool(candidate and candidate not in ("(none)", installed))
    if is_upgrade:
        return PackageState(
            state=InstallState.UPGRADE_AVAILABLE,
            installed_version=installed_short,
            candidate_version=candidate_short,
        )
    return PackageState(
        state=InstallState.INSTALLED,
        installed_version=installed_short,
        candidate_version=candidate_short,
    )


def query_catalog_state(catalog: Catalog) -> dict[str, PackageState]:
    """Resolve the install state of every package in ``catalog``.

    apt packages are batched into one ``apt-cache policy`` call; non-apt
    packages (``github_release``, ``script``) each run their own
    ``version_command`` to detect installed version, compared against the
    catalog's pinned ``version`` to spot upgrades.

    This function performs blocking subprocess I/O. Textual callers should
    use :func:`query_catalog_state_async` so the event loop stays responsive.
    """
    apt_names = [p.name for p in catalog.iter_packages() if p.type == "apt"]
    states = query_apt_state(apt_names)
    for pkg in catalog.iter_packages():
        if pkg.type == "apt":
            continue
        states[pkg.name] = query_command_state(pkg)
    return states


async def query_catalog_state_async(catalog: Catalog) -> dict[str, PackageState]:
    """Like :func:`query_catalog_state`, but runs in a worker thread."""
    return await asyncio.to_thread(query_catalog_state, catalog)


def query_command_state(pkg: CuratedPackage) -> PackageState:
    """Detect install state for a non-apt curated package.

    The package's catalog entry tells us how to find its installed
    version (``version_command`` + ``version_pattern``), and what
    version is "current" (``version`` field — refreshed by the catalog
    repo's CI). We compare the two and emit the right PackageState.

    Order of detection:
      1. If ``version_command`` runs and matches ``version_pattern``,
         use the captured group as the installed version.
      2. Else, if ``binary`` is set and that path exists, treat as
         installed with no version detail.
      3. Otherwise NOT_INSTALLED.
    """
    candidate = pkg.version
    installed_version = _detect_installed_version(pkg)

    if installed_version is None:
        return PackageState(state=InstallState.NOT_INSTALLED, candidate_version=candidate)

    if candidate and candidate != installed_version:
        return PackageState(
            state=InstallState.UPGRADE_AVAILABLE,
            installed_version=installed_version,
            candidate_version=candidate,
        )
    return PackageState(
        state=InstallState.INSTALLED,
        installed_version=installed_version,
        candidate_version=candidate,
    )


def _detect_installed_version(pkg: CuratedPackage) -> str | None:
    """Run pkg.version_command and extract the version via pkg.version_pattern.

    Returns the captured version string, or None if anything fails (binary
    missing, exit non-zero, regex doesn't match). The caller treats None
    as "not installed".

    If no version_command is set, fall back to checking ``pkg.binary``:
    file exists → return empty string (a falsy-but-not-None sentinel
    that callers can treat as "installed, version unknown" via the empty
    truthy distinction). For simplicity in the trimmed apt-only catalog,
    that fallback simply means "treat as installed" without a version.
    """
    import re
    import subprocess

    if pkg.version_command:
        try:
            proc = subprocess.run(
                pkg.version_command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return None
        if proc.returncode != 0:
            return None
        if pkg.version_pattern:
            match = re.search(pkg.version_pattern, proc.stdout)
            if match:
                try:
                    return match.group(1)
                except IndexError:
                    return None
            return None
        return proc.stdout.strip().splitlines()[0] if proc.stdout.strip() else None

    if pkg.binary and Path(pkg.binary).exists():
        return ""  # installed, version unknown
    return None

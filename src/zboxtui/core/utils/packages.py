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

The dialog widget that consumes these lives in core/menu_items/packages.py
(to be built in Phase 1 of the Configure Packages work).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, auto
from pathlib import Path
from typing import Literal

SUPPORTED_SCHEMA_VERSION = 1
PackageType = Literal["apt", "github_release", "script"]


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
CHECKBOX_INSTALLED = "[x]"
CHECKBOX_ABSENT = "[ ]"
CHECKBOX_PENDING_INSTALL = "[+]"
CHECKBOX_PENDING_REMOVE = "[-]"

# How the version column reads in each state.
UPGRADE_ARROW = "→"
UPGRADE_INDICATOR = "↑"


def checkbox_for(state: PackageState, target_checked: bool) -> str:
    """Pick the right [x]/[ ]/[+]/[-] symbol given current + target state."""
    if state.is_installed and target_checked:
        return CHECKBOX_INSTALLED
    if not state.is_installed and not target_checked:
        return CHECKBOX_ABSENT
    if state.is_installed and not target_checked:
        return CHECKBOX_PENDING_REMOVE
    return CHECKBOX_PENDING_INSTALL


def version_cell(state: PackageState) -> str:
    """Format the version column for one row."""
    if state.state == InstallState.UPGRADE_AVAILABLE:
        return (
            f"{state.installed_version} {UPGRADE_ARROW} "
            f"{state.candidate_version} {UPGRADE_INDICATOR}"
        )
    if state.state == InstallState.INSTALLED:
        return state.installed_version or ""
    return ""


def format_package_row(
    pkg: CuratedPackage,
    state: PackageState,
    target_checked: bool,
    *,
    name_width: int = 22,
    version_width: int = 22,
) -> str:
    """Render one picker row as a fixed-width string.

    Columns, left-aligned and padded to fixed widths:
      ``[x] <name padded> <version padded> <description>``

    The function does **no** truncation if a column overflows — it pads
    short content but lets long content push the next column right. This
    keeps the test assertions easy to read; the dialog clips visually via
    Textual layout.
    """
    cb = checkbox_for(state, target_checked)
    name = pkg.name.ljust(name_width)
    ver = version_cell(state).ljust(version_width)
    return f"{cb} {name} {ver} {pkg.description}"


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

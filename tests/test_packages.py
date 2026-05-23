"""Tests for the curated-package catalog loader and display formatters.

The dialog widget that actually uses these doesn't exist yet (Phase 1
of the Configure Packages work); locking the *display logic* down with
unit tests first means the widget integration is mostly plumbing.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from zboxtui.core.utils.packages import (
    CHECKBOX_ABSENT,
    CHECKBOX_INSTALLED,
    CHECKBOX_PENDING_INSTALL,
    CHECKBOX_PENDING_REMOVE,
    Catalog,
    CatalogError,
    CuratedPackage,
    InstallState,
    PackageState,
    checkbox_for,
    format_catalog_freshness,
    format_package_row,
    load_catalog,
    simplify_apt_version,
    version_cell,
)

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_CATALOG = FIXTURES / "sample_packages.json"


# ---------------------------------------------------------------------------
# Catalog loading
# ---------------------------------------------------------------------------


def test_load_catalog_parses_groups_and_packages() -> None:
    cat = load_catalog(SAMPLE_CATALOG)
    assert isinstance(cat, Catalog)
    assert cat.schema_version == 1
    assert cat.source_path == SAMPLE_CATALOG
    assert [g.name for g in cat.groups] == ["Modern CLI Tools", "Shell Experience"]
    flat = cat.iter_packages()
    assert [p.name for p in flat] == ["bat", "ripgrep", "oh-my-posh", "atuin"]


def test_load_catalog_parses_updated_at_as_aware_datetime() -> None:
    cat = load_catalog(SAMPLE_CATALOG)
    assert cat.updated_at == datetime(2026, 5, 19, 8, 30, tzinfo=timezone.utc)


def test_load_catalog_per_type_optional_fields_land_on_dataclass() -> None:
    cat = load_catalog(SAMPLE_CATALOG)
    by_name = {p.name: p for p in cat.iter_packages()}
    assert by_name["bat"].version is None
    assert by_name["bat"].github_repo is None

    omp = by_name["oh-my-posh"]
    assert omp.type == "github_release"
    assert omp.version == "25.0.0"
    assert omp.github_repo == "JanDeDobbeleer/oh-my-posh"
    assert "{version}" in (omp.install_command or "")

    atuin = by_name["atuin"]
    assert atuin.type == "script"
    assert atuin.version == "18.5.0"
    assert atuin.github_repo is None  # script type has no repo


def test_load_catalog_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(CatalogError, match="not found"):
        load_catalog(tmp_path / "does-not-exist.json")


def test_load_catalog_rejects_bad_json(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(CatalogError, match="not valid JSON"):
        load_catalog(bad)


def test_load_catalog_rejects_unsupported_schema_version(tmp_path: Path) -> None:
    f = tmp_path / "future.json"
    f.write_text(json.dumps({"schema_version": 99, "groups": []}), encoding="utf-8")
    with pytest.raises(CatalogError, match="Unsupported schema_version"):
        load_catalog(f)


def test_load_catalog_rejects_empty_groups(tmp_path: Path) -> None:
    f = tmp_path / "empty.json"
    f.write_text(json.dumps({"schema_version": 1, "groups": []}), encoding="utf-8")
    with pytest.raises(CatalogError, match="non-empty 'groups'"):
        load_catalog(f)


def test_load_catalog_rejects_unknown_package_type(tmp_path: Path) -> None:
    f = tmp_path / "weird.json"
    f.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "groups": [
                    {"name": "X", "packages": [{"type": "deb", "name": "foo"}]},
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(CatalogError, match="unknown type"):
        load_catalog(f)


def test_shipped_default_catalog_loads() -> None:
    """The default catalog shipped with the package itself must always load."""
    shipped = Path(__file__).parent.parent / "src" / "zboxtui" / "data" / "packages.json"
    cat = load_catalog(shipped)
    assert cat.schema_version == 1
    assert cat.groups, "shipped catalog should not be empty"


# ---------------------------------------------------------------------------
# Checkbox state machine
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "current,target,expected",
    [
        (InstallState.INSTALLED, True, CHECKBOX_INSTALLED),
        (InstallState.UPGRADE_AVAILABLE, True, CHECKBOX_INSTALLED),
        (InstallState.NOT_INSTALLED, False, CHECKBOX_ABSENT),
        (InstallState.INSTALLED, False, CHECKBOX_PENDING_REMOVE),
        (InstallState.UPGRADE_AVAILABLE, False, CHECKBOX_PENDING_REMOVE),
        (InstallState.NOT_INSTALLED, True, CHECKBOX_PENDING_INSTALL),
    ],
)
def test_checkbox_for_every_state_combo(
    current: InstallState, target: bool, expected: str
) -> None:
    state = PackageState(state=current, installed_version="1.0", candidate_version="1.1")
    assert checkbox_for(state, target) == expected


# ---------------------------------------------------------------------------
# Version cell
# ---------------------------------------------------------------------------


def test_version_cell_blank_when_not_installed() -> None:
    assert version_cell(PackageState(state=InstallState.NOT_INSTALLED)) == ""


def test_version_cell_just_installed_version_when_no_upgrade() -> None:
    state = PackageState(state=InstallState.INSTALLED, installed_version="3.0.5")
    assert version_cell(state) == "3.0.5"


def test_version_cell_shows_arrow_when_upgrade_available() -> None:
    state = PackageState(
        state=InstallState.UPGRADE_AVAILABLE,
        installed_version="0.19.0",
        candidate_version="0.20.0",
    )
    assert version_cell(state) == "0.19.0 ↑ 0.20.0"


# ---------------------------------------------------------------------------
# Full row formatting
# ---------------------------------------------------------------------------


def _apt(name: str = "htop", desc: str = "Process viewer") -> CuratedPackage:
    return CuratedPackage(type="apt", name=name, description=desc)


def test_format_row_apt_not_installed_no_candidate() -> None:
    pkg = _apt(name="tmux", desc="Terminal multiplexer")
    state = PackageState(state=InstallState.NOT_INSTALLED)
    row = format_package_row(pkg, state, target_checked=False, name_width=10, version_width=10)
    # No candidate → version cell is empty after the separator.
    assert row.plain == "[ ] tmux       │ "


def test_format_row_apt_not_installed_shows_candidate() -> None:
    """When apt knows the candidate version, show it even for not-installed."""
    pkg = _apt(name="tmux", desc="Terminal multiplexer")
    state = PackageState(state=InstallState.NOT_INSTALLED, candidate_version="3.3a")
    row = format_package_row(pkg, state, target_checked=False, name_width=10, version_width=10)
    assert row.plain == "[ ] tmux       │ 3.3a"


def test_format_row_apt_installed_no_upgrade() -> None:
    pkg = _apt(name="htop", desc="Process viewer")
    state = PackageState(state=InstallState.INSTALLED, installed_version="3.0.5")
    row = format_package_row(pkg, state, target_checked=True, name_width=10, version_width=10)
    assert row.plain == "[x] htop       │ 3.0.5"


def test_format_row_upgrade_available_keeps_arrow_inline() -> None:
    pkg = CuratedPackage(type="github_release", name="eza", description="Modern ls")
    state = PackageState(
        state=InstallState.UPGRADE_AVAILABLE,
        installed_version="0.19.0",
        candidate_version="0.20.0",
    )
    row = format_package_row(pkg, state, target_checked=True, name_width=10, version_width=10)
    # Both versions, arrow indicator, all on the first line.
    assert row.plain == "[x] eza        │ 0.19.0     │ ↑ 0.20.0"


def test_format_row_upgrade_styles_only_the_new_version() -> None:
    pkg = _apt(name="eza", desc="Modern ls")
    state = PackageState(
        state=InstallState.UPGRADE_AVAILABLE,
        installed_version="0.19.0",
        candidate_version="0.20.0",
    )
    row = format_package_row(
        pkg, state, target_checked=True,
        name_width=10, version_width=10,
        upgrade_style="bold green",
    )
    # Exactly one styled span, applied to the candidate version "0.20.0".
    styled = [s for s in row.spans if s.style]
    assert len(styled) == 1
    span = styled[0]
    assert row.plain[span.start:span.end] == "0.20.0"


def test_format_row_user_marks_installed_for_removal() -> None:
    pkg = _apt(name="lsd", desc="LSDeluxe")
    state = PackageState(state=InstallState.INSTALLED, installed_version="1.0.0")
    row = format_package_row(pkg, state, target_checked=False, name_width=8, version_width=10)
    assert row.plain == "[-] lsd      │ 1.0.0"


def test_format_row_user_marks_absent_for_install() -> None:
    pkg = _apt(name="ripgrep", desc="Recursive grep")
    state = PackageState(state=InstallState.NOT_INSTALLED)
    row = format_package_row(pkg, state, target_checked=True, name_width=10, version_width=10)
    assert row.plain == "[+] ripgrep    │ "


# ---------------------------------------------------------------------------
# Version-string simplification
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        # docker-ce style: epoch + debian/trixie suffix
        ("5:29.5.2-1~debian.13~trixie", "29.5.2-1"),
        # btop style: epoch + clean debian revision
        ("1:1.3.2-0.1", "1.3.2-0.1"),
        # bare semver
        ("1.98.3", "1.98.3"),
        # backports
        ("2.34-3~bpo12+1", "2.34-3"),
        # +deb style suffix (terraform-like)
        ("1.6.6+ds-1+deb13u1", "1.6.6+ds-1"),
        # epoch but no suffix
        ("2:4.5.6-1", "4.5.6-1"),
        # already clean
        ("0.20.0", "0.20.0"),
        # empty / blank
        ("", ""),
    ],
)
def test_simplify_apt_version(raw: str, expected: str) -> None:
    assert simplify_apt_version(raw) == expected


def test_simplify_does_not_strip_colon_inside_text() -> None:
    """A non-numeric prefix before ':' is not an epoch and must be preserved."""
    # Hypothetical, but defends against being too aggressive.
    assert simplify_apt_version("foo:bar") == "foo:bar"


# ---------------------------------------------------------------------------
# Catalog freshness string
# ---------------------------------------------------------------------------


NOW = datetime(2026, 5, 22, 12, 0, tzinfo=timezone.utc)


def test_freshness_none_means_unknown() -> None:
    assert format_catalog_freshness(None, NOW) == "Last update: unknown"


def test_freshness_today() -> None:
    same_day = datetime(2026, 5, 22, 8, 0, tzinfo=timezone.utc)
    assert format_catalog_freshness(same_day, NOW) == "Last update: 2026-05-22 (today)"


def test_freshness_yesterday() -> None:
    y = datetime(2026, 5, 21, 12, 0, tzinfo=timezone.utc)
    assert format_catalog_freshness(y, NOW) == "Last update: 2026-05-21 (yesterday)"


def test_freshness_few_days_ago() -> None:
    d = datetime(2026, 5, 19, 12, 0, tzinfo=timezone.utc)
    assert format_catalog_freshness(d, NOW) == "Last update: 2026-05-19 (3 days ago)"


def test_freshness_two_months_appends_refresh_warning() -> None:
    d = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
    s = format_catalog_freshness(d, NOW)
    assert s.startswith("Last update: 2026-03-01")
    assert "month" in s
    assert "Refresh recommended" in s


def test_freshness_year_old() -> None:
    d = datetime(2024, 5, 1, 12, 0, tzinfo=timezone.utc)
    s = format_catalog_freshness(d, NOW)
    assert "~2 years ago" in s
    assert "Refresh recommended" in s


def test_freshness_handles_naive_input_as_utc() -> None:
    """ISO date-only strings parse to naive datetimes; the formatter must
    still produce a sensible result rather than blow up on tz subtraction."""
    d = datetime(2026, 5, 19, 12, 0)  # tzinfo=None
    s = format_catalog_freshness(d, NOW)
    assert "3 days ago" in s


def test_freshness_future_timestamp_shows_date_only() -> None:
    future = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    assert format_catalog_freshness(future, NOW) == "Last update: 2026-06-01"

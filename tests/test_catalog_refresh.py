"""Tests for the catalog refresh path (file:// URLs + error handling)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from zboxtui.core.utils import catalog_refresh as cr


@pytest.fixture
def xdg_cache_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the cache target into the test's tmp_path."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    return tmp_path / "zboxtui" / "packages.json"


def _good_catalog() -> dict:
    return {
        "schema_version": 1,
        "updated_at": "2026-05-22T00:00:00Z",
        "groups": [
            {
                "name": "Test Group",
                "packages": [
                    {"type": "apt", "name": "htop", "description": "Process viewer"},
                ],
            }
        ],
    }


def test_refresh_file_url_writes_cache(tmp_path: Path, xdg_cache_tmp: Path) -> None:
    src = tmp_path / "src.json"
    src.write_text(json.dumps(_good_catalog()), encoding="utf-8")

    result = cr.refresh_catalog(src.as_uri())
    assert result.status == "ok"
    assert result.path == xdg_cache_tmp
    assert xdg_cache_tmp.is_file()
    # Roundtrip
    loaded = json.loads(xdg_cache_tmp.read_text())
    assert loaded["schema_version"] == 1


def test_refresh_handles_missing_remote(tmp_path: Path, xdg_cache_tmp: Path) -> None:
    # file:// URL pointing at a path that doesn't exist
    missing = tmp_path / "does-not-exist.json"
    result = cr.refresh_catalog(missing.as_uri())
    assert result.status == "network_error"
    assert "Could not fetch" in result.message
    assert not xdg_cache_tmp.exists()


def test_refresh_rejects_invalid_json(tmp_path: Path, xdg_cache_tmp: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("not json", encoding="utf-8")

    result = cr.refresh_catalog(bad.as_uri())
    assert result.status == "validation_error"
    assert "not valid JSON" in result.message
    assert not xdg_cache_tmp.exists()


def test_refresh_rejects_unsupported_schema_version(
    tmp_path: Path, xdg_cache_tmp: Path
) -> None:
    weird = {"schema_version": 99, "groups": []}
    p = tmp_path / "weird.json"
    p.write_text(json.dumps(weird), encoding="utf-8")

    result = cr.refresh_catalog(p.as_uri())
    assert result.status == "validation_error"
    assert "Unsupported schema_version" in result.message
    assert not xdg_cache_tmp.exists()


def test_refresh_does_not_clobber_cache_on_failure(
    tmp_path: Path, xdg_cache_tmp: Path
) -> None:
    """If the new catalog is bad, the old cache must survive."""
    xdg_cache_tmp.parent.mkdir(parents=True, exist_ok=True)
    xdg_cache_tmp.write_text(json.dumps(_good_catalog()), encoding="utf-8")
    original = xdg_cache_tmp.read_text()

    bad = tmp_path / "bad.json"
    bad.write_text("nope", encoding="utf-8")
    result = cr.refresh_catalog(bad.as_uri())
    assert result.status == "validation_error"
    assert xdg_cache_tmp.read_text() == original


def test_refresh_atomic_replace_on_success(tmp_path: Path, xdg_cache_tmp: Path) -> None:
    """A pre-existing cache should be overwritten cleanly, not have a
    leftover .tmp sibling lying around."""
    xdg_cache_tmp.parent.mkdir(parents=True, exist_ok=True)
    xdg_cache_tmp.write_text("old contents", encoding="utf-8")

    src = tmp_path / "src.json"
    src.write_text(json.dumps(_good_catalog()), encoding="utf-8")

    result = cr.refresh_catalog(src.as_uri())
    assert result.status == "ok"
    assert "schema_version" in xdg_cache_tmp.read_text()
    # No .tmp left over.
    assert not list(xdg_cache_tmp.parent.glob("*.tmp"))

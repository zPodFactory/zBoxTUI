"""Fetch the curated package catalog from its configured URL.

The TUI's "Refresh zBox curated package list" action is the only place that does
network I/O — at startup we always load from the local cache or the
shipped default. This module is the side-effecting half; the rest of
``packages.py`` stays pure.

Supports any URL ``urllib`` understands, including ``file://`` so users
can point ``catalog_url`` at a local JSON file during testing without
having to stand up an HTTP server.
"""

from __future__ import annotations

import contextlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast
from urllib.error import URLError
from urllib.request import Request, urlopen

from .packages import (
    CatalogError,
    cached_catalog_path,
    load_catalog,
)


@dataclass(frozen=True)
class RefreshResult:
    """Outcome of a refresh attempt — successful or otherwise."""

    status: Literal["ok", "network_error", "validation_error", "io_error"]
    message: str
    path: Path | None = None  # where the new catalog landed, on success


def refresh_catalog(catalog_url: str, *, timeout: float = 10.0) -> RefreshResult:
    """Fetch ``catalog_url``, validate, write to cache.

    On any failure the cache is left untouched so the previously-good
    catalog stays loadable. Validation runs :func:`load_catalog` on the
    downloaded content (in a temp file) before promoting it to the
    cache, so a malformed remote can't break the next startup.
    """
    try:
        body = _fetch(catalog_url, timeout=timeout)
    except URLError as exc:
        return RefreshResult(
            status="network_error",
            message=f"Could not fetch {catalog_url}: {exc.reason}",
        )
    except (OSError, ValueError) as exc:
        return RefreshResult(
            status="network_error",
            message=f"Could not fetch {catalog_url}: {exc}",
        )

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        return RefreshResult(
            status="validation_error",
            message=f"Downloaded catalog is not valid JSON: {exc}",
        )

    target = cached_catalog_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(parsed, indent=2), encoding="utf-8")
    except OSError as exc:
        return RefreshResult(
            status="io_error",
            message=f"Could not write cache file {target}: {exc}",
        )

    try:
        load_catalog(tmp)
    except CatalogError as exc:
        # The downloaded JSON parses but doesn't validate as a catalog.
        # Leave the previous cache alone.
        with contextlib.suppress(OSError):
            tmp.unlink(missing_ok=True)
        return RefreshResult(
            status="validation_error",
            message=f"Downloaded catalog failed validation: {exc}",
        )

    # Atomic-ish swap.
    try:
        os.replace(tmp, target)
    except OSError as exc:
        return RefreshResult(
            status="io_error",
            message=f"Could not promote catalog into place: {exc}",
        )

    return RefreshResult(
        status="ok",
        message=f"Refreshed from {catalog_url}",
        path=target,
    )


def _fetch(url: str, *, timeout: float) -> bytes:
    """Pull a URL's contents via urllib. Supports http(s):// and file://."""
    req = Request(url, headers={"User-Agent": "zboxtui/catalog-refresh"})
    with urlopen(req, timeout=timeout) as resp:  # noqa: S310 — URL comes from config, controlled.
        return cast(bytes, resp.read())

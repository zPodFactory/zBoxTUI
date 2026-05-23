"""Tests for the apt operations layer (no subprocess execution).

The streaming wrapper itself is exercised manually against a real apt;
these tests cover the pure logic: argv construction, plan ordering,
progress-line parsing.
"""

from __future__ import annotations

import pytest

from zboxtui.core.utils.apt import (
    AptOperation,
    ProgressEvent,
    parse_progress,
    plan_operations,
)


# ---------------------------------------------------------------------------
# AptOperation.argv
# ---------------------------------------------------------------------------


def test_install_argv_uses_no_install_recommends() -> None:
    op = AptOperation(kind="install", packages=("htop", "btop"))
    assert op.argv() == [
        "apt-get",
        "install",
        "-y",
        "--no-install-recommends",
        "htop",
        "btop",
    ]


def test_remove_argv_uses_remove_not_purge() -> None:
    """Remove keeps config files in place (purge would scrub them)."""
    op = AptOperation(kind="remove", packages=("lsd",))
    assert op.argv() == [
        "apt-get",
        "remove",
        "-y",
        "--no-install-recommends",
        "lsd",
    ]


def test_update_argv_takes_no_packages() -> None:
    op = AptOperation(kind="update", packages=())
    assert op.argv() == ["apt-get", "update"]


# ---------------------------------------------------------------------------
# plan_operations
# ---------------------------------------------------------------------------


def test_plan_orders_removes_before_installs() -> None:
    plan = plan_operations(install=["htop"], remove=["lsd"])
    assert [p.kind for p in plan] == ["remove", "install"]


def test_plan_skips_empty_groups() -> None:
    assert plan_operations(install=["htop"], remove=[]) == [
        AptOperation(kind="install", packages=("htop",)),
    ]
    assert plan_operations(install=[], remove=["lsd"]) == [
        AptOperation(kind="remove", packages=("lsd",)),
    ]


def test_plan_returns_empty_when_no_changes() -> None:
    assert plan_operations(install=[], remove=[]) == []


# ---------------------------------------------------------------------------
# parse_progress
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "line,expected",
    [
        ("Setting up htop (3.0.5-7+b1) ...", ProgressEvent("htop", "setting_up")),
        ("Setting up docker-ce:amd64 (5:29.5.2-1) ...", ProgressEvent("docker-ce", "setting_up")),
        ("Removing lsd (1.0.0-1) ...", ProgressEvent("lsd", "removing")),
        ("Unpacking btop (1.3.2-0.1) over (1.3.0-1) ...", ProgressEvent("btop", "unpacking")),
    ],
)
def test_parse_progress_recognizes_apt_lines(line: str, expected: ProgressEvent) -> None:
    assert parse_progress(line) == expected


@pytest.mark.parametrize(
    "line",
    [
        "Reading package lists... Done",
        "Building dependency tree... Done",
        "The following NEW packages will be installed:",
        "Need to get 1234 B of archives.",
        "",
        "Get:1 http://deb.debian.org/debian trixie/main amd64 htop amd64 3.0.5-7+b1 [123 kB]",
    ],
)
def test_parse_progress_ignores_unrelated_lines(line: str) -> None:
    assert parse_progress(line) is None

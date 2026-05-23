"""Tests for the apt operations layer (no subprocess execution).

The streaming wrapper itself is exercised manually against a real apt;
these tests cover the pure logic: argv construction, plan ordering,
progress-line parsing.
"""

from __future__ import annotations

import asyncio
import sys

import pytest

from zboxtui.core.utils.apt import (
    AptOperation,
    ProgressEvent,
    is_apt_status_line,
    normalize_terminal_line,
    parse_progress,
    plan_operations,
    run_streaming,
    run_streaming_sync,
    _emit_terminal_fragments,
)
from zboxtui.core.utils.privilege import Privilege

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
    plan = plan_operations(install=["htop", "bat"], remove=["lsd"])
    assert [(p.kind, p.packages) for p in plan] == [
        ("remove", ("lsd",)),
        ("install", ("htop",)),
        ("install", ("bat",)),
    ]


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
        (
            "Selecting previously unselected package bat.",
            ProgressEvent("bat", "selecting"),
        ),
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


@pytest.mark.asyncio
async def test_run_streaming_drains_both_streams_with_slow_sink(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: a slow sync sink must not deadlock when both pipes are busy."""
    script = (
        "import sys, time\n"
        "for i in range(200):\n"
        "    sys.stdout.write(f'out-{i}\\n')\n"
        "    sys.stdout.flush()\n"
        "    sys.stderr.write(f'err-{i}\\n')\n"
        "    sys.stderr.flush()\n"
        "    time.sleep(0.001)\n"
    )
    monkeypatch.setattr(
        "zboxtui.core.utils.apt.build_apt_command",
        lambda argv, privilege: [sys.executable, "-c", script],
    )
    op = AptOperation(kind="update", packages=())
    lines: list[tuple[str, str]] = []

    def slow_sink(stream: str, line: str, *, transient: bool = False) -> None:
        lines.append((stream, line))
        # Simulate ApplyDialog RichLog work on the event loop thread.
        import time

        time.sleep(0.001)

    result = await asyncio.wait_for(
        run_streaming(op, Privilege.ROOT, sink=slow_sink),
        timeout=15,
    )
    assert result.returncode == 0
    assert len(lines) == 400


@pytest.mark.asyncio
async def test_run_streaming_sync_runs_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "zboxtui.core.utils.apt.build_apt_command",
        lambda argv, privilege: ["echo", "hello"],
    )
    lines: list[tuple[str, str]] = []
    op = AptOperation(kind="update", packages=())
    result = run_streaming_sync(
        op,
        Privilege.ROOT,
        sink=lambda stream, line, *, transient=False: lines.append((stream, line)),
    )
    assert result.returncode == 0
    assert ("stdout", "hello") in lines


# ---------------------------------------------------------------------------
# Terminal output normalization
# ---------------------------------------------------------------------------


def test_normalize_terminal_line_takes_text_after_last_carriage_return() -> None:
    raw = "Reading database ... \r(Reading database ... 5%\r(Reading database ... 10%"
    assert normalize_terminal_line(raw) == "(Reading database ... 10%"


@pytest.mark.parametrize(
    "line",
    [
        "Reading database ...",
        "(Reading database ... 45%",
        "Reading package lists... Done",
        "Building dependency tree... Done",
    ],
)
def test_is_apt_status_line_matches_progress_output(line: str) -> None:
    assert is_apt_status_line(line)


def test_is_apt_status_line_leaves_fetch_lines_for_the_log() -> None:
    assert not is_apt_status_line(
        "Get:1 http://deb.debian.org/debian trixie InRelease [140 kB]"
    )


def test_emit_terminal_fragments_treats_carriage_return_as_transient() -> None:
    emitted: list[tuple[str, bool]] = []

    def emit(text: str, transient: bool) -> None:
        emitted.append((text, transient))

    leftover = _emit_terminal_fragments(
        "Reading database ...\r(Reading database ... 5%\nGet:1 http://example\n",
        emit,
    )
    assert leftover == ""
    assert emitted == [
        ("Reading database ...", True),
        ("(Reading database ... 5%", True),
        ("Get:1 http://example", False),
    ]

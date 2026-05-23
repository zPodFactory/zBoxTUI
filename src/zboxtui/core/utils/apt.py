"""apt operation primitives + line-stream progress detection.

Most of this module is small + pure so it can be unit-tested. The
actual subprocess-streaming wrapper (`run_streaming`) is a thin shell
around asyncio.subprocess that the ApplyDialog drives.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import re
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass
from typing import Literal

from .privilege import Privilege, build_apt_command

OperationKind = Literal["install", "remove", "update"]


@dataclass(frozen=True)
class AptOperation:
    """Description of an apt batch to execute (one install or one remove)."""

    kind: OperationKind
    packages: tuple[str, ...]

    def argv(self) -> list[str]:
        """Bare apt-get argv (no sudo prefix; build_apt_command wraps it)."""
        if self.kind == "update":
            return ["apt-get", "update"]
        verb = "install" if self.kind == "install" else "remove"
        # --no-install-recommends keeps installs lean.
        # remove (not purge) leaves configs in place for re-install.
        return ["apt-get", verb, "-y", "--no-install-recommends", *self.packages]


def plan_operations(
    install: Sequence[str],
    remove: Sequence[str],
) -> list[AptOperation]:
    """Order the operations safely.

    Removes go first so an install can't be blocked by a package marked
    for removal that depends on it. Empty groups are skipped. apt-get
    update is *not* included here — the dialog runs it as a separate
    explicit action.
    """
    ops: list[AptOperation] = []
    if remove:
        ops.append(AptOperation(kind="remove", packages=tuple(remove)))
    if install:
        ops.append(AptOperation(kind="install", packages=tuple(install)))
    return ops


# ---------------------------------------------------------------------------
# Progress detection from apt's output stream
# ---------------------------------------------------------------------------

# Lines apt writes when actually installing/removing each package. Used by
# the dialog to advance the overall ProgressBar by one tick per package.
_SETTING_UP = re.compile(r"^Setting up ([^\s(:]+)")
_REMOVING = re.compile(r"^Removing ([^\s(:]+)")
_UNPACKING = re.compile(r"^Unpacking ([^\s(:]+)")


@dataclass(frozen=True)
class ProgressEvent:
    """A single user-visible progress signal parsed from the apt stream."""

    package: str
    action: Literal["setting_up", "removing", "unpacking"]


def parse_progress(line: str) -> ProgressEvent | None:
    """Return a ProgressEvent if ``line`` indicates a package transition."""
    if m := _SETTING_UP.match(line):
        return ProgressEvent(package=m.group(1), action="setting_up")
    if m := _REMOVING.match(line):
        return ProgressEvent(package=m.group(1), action="removing")
    if m := _UNPACKING.match(line):
        return ProgressEvent(package=m.group(1), action="unpacking")
    return None


# ---------------------------------------------------------------------------
# Subprocess streaming
# ---------------------------------------------------------------------------


@dataclass
class StreamResult:
    """Outcome of a single :func:`run_streaming` call."""

    returncode: int
    cancelled: bool = False


async def run_streaming(
    op: AptOperation,
    privilege: Privilege,
    *,
    password: str | None = None,
    sink: Callable[[str, str], None] | None = None,
) -> StreamResult:
    """Run an :class:`AptOperation` and feed each output line to ``sink``.

    ``sink`` is any callable taking ``(stream_name, line)`` where
    ``stream_name`` is ``"stdout"`` or ``"stderr"``. The function returns
    only after the subprocess exits.

    When ``privilege == SUDO_PASSWORD``, ``password`` must be provided;
    it is written to the subprocess stdin and never echoed to ``sink``.
    """
    cmd = build_apt_command(op.argv(), privilege)
    env = dict(os.environ)
    env.setdefault("DEBIAN_FRONTEND", "noninteractive")

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE if password is not None else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )

    if password is not None and proc.stdin is not None:
        proc.stdin.write(f"{password}\n".encode())
        with contextlib.suppress(BrokenPipeError, ConnectionResetError):
            await proc.stdin.drain()
        proc.stdin.close()

    async def _pump(stream: asyncio.StreamReader, name: str) -> None:
        assert sink is not None
        while True:
            chunk = await stream.readline()
            if not chunk:
                return
            line = chunk.decode(errors="replace").rstrip("\n")
            sink(name, line)

    if sink is not None:
        assert proc.stdout is not None and proc.stderr is not None
        await asyncio.gather(
            _pump(proc.stdout, "stdout"),
            _pump(proc.stderr, "stderr"),
        )

    returncode = await proc.wait()
    return StreamResult(returncode=returncode)


async def collect_lines(
    op: AptOperation,
    privilege: Privilege,
    *,
    password: str | None = None,
) -> AsyncIterator[tuple[str, str]]:
    """Like :func:`run_streaming` but yields lines instead of taking a sink.

    Convenient for tests; the dialog uses run_streaming directly so it
    can interleave UI updates with line arrival.
    """
    lines: asyncio.Queue[tuple[str, str] | None] = asyncio.Queue()

    def sink(name: str, line: str) -> None:
        lines.put_nowait((name, line))

    async def runner() -> None:
        await run_streaming(op, privilege, password=password, sink=sink)
        lines.put_nowait(None)

    task = asyncio.create_task(runner())
    while True:
        item = await lines.get()
        if item is None:
            break
        yield item
    await task

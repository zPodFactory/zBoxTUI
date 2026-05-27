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
import subprocess
import threading
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass
from queue import Queue
from typing import Literal

from .privilege import Privilege, build_apt_command

OperationKind = Literal["install", "remove", "update"]


@dataclass(frozen=True)
class AptOperation:
    """Description of an apt batch to execute (typically one package)."""

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
    """Order the operations safely, one package per :class:`AptOperation`.

    Removes go first so an install can't be blocked by a package marked
    for removal that depends on it. Each package gets its own ``apt-get``
    invocation so the apply dialog can drive progress bars one at a time.
    ``apt-get update`` is *not* included here — the dialog runs it as a
    separate explicit action.
    """
    ops: list[AptOperation] = []
    for pkg in remove:
        ops.append(AptOperation(kind="remove", packages=(pkg,)))
    for pkg in install:
        ops.append(AptOperation(kind="install", packages=(pkg,)))
    return ops


# ---------------------------------------------------------------------------
# Progress detection from apt's output stream
# ---------------------------------------------------------------------------

# Lines apt writes when actually installing/removing each package. Used by
# the dialog to advance per-package progress bars.
_SETTING_UP = re.compile(r"^Setting up ([^\s(:]+)")
_REMOVING = re.compile(r"^Removing ([^\s(:]+)")
_UNPACKING = re.compile(r"^Unpacking ([^\s(:]+)")
_SELECTING = re.compile(r"^Selecting previously unselected package ([^\s.]+)\.")


@dataclass(frozen=True)
class ProgressEvent:
    """A single user-visible progress signal parsed from the apt stream."""

    package: str
    action: Literal["setting_up", "removing", "unpacking", "selecting"]


def apt_package_base(name: str) -> str:
    """Strip an optional ``:arch`` suffix from an apt/dpkg package name."""
    return name.split(":", 1)[0]


def parse_progress(line: str) -> ProgressEvent | None:
    """Return a ProgressEvent if ``line`` indicates a package transition."""
    if m := _SETTING_UP.match(line):
        return ProgressEvent(package=m.group(1), action="setting_up")
    if m := _REMOVING.match(line):
        return ProgressEvent(package=m.group(1), action="removing")
    if m := _UNPACKING.match(line):
        return ProgressEvent(package=m.group(1), action="unpacking")
    if m := _SELECTING.match(line):
        return ProgressEvent(package=m.group(1), action="selecting")
    return None


# ---------------------------------------------------------------------------
# Terminal-style output normalization (apt/dpkg use \r for live progress)
# ---------------------------------------------------------------------------

_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")

# Spinner / percentage lines — show live in the status bar, not the scroll log.
_APT_STATUS_LINE = re.compile(
    r"^\(?("
    r"Reading database \.\.\."
    r"|Reading package lists\.\.\."
    r"|Reading state information\.\.\."
    r"|Building dependency tree\.\.\."
    r"|Loading additional disk space"
    r")",
    re.IGNORECASE,
)


def normalize_terminal_line(text: str) -> str:
    """Return the visible text from a TTY fragment (handles embedded ``\\r``)."""
    if "\r" in text:
        text = text.rsplit("\r", 1)[-1]
    text = _ANSI_ESCAPE.sub("", text)
    return text.strip()


def is_apt_status_line(line: str) -> bool:
    """True for apt/dpkg live-progress lines that should not flood the log."""
    normalized = normalize_terminal_line(line)
    if not normalized:
        return True
    if _APT_STATUS_LINE.match(normalized):
        return True
    # Percentage-only progress, e.g. "(Reading database ... 45%"
    return bool(re.search(r"\d+%\)?\s*$", normalized) and "Reading" in normalized)


def _emit_terminal_fragments(
    buffer: str,
    emit: Callable[[str, bool], None],
) -> str:
    """Parse buffered subprocess text into emit calls; return leftover buffer."""
    while buffer:
        cr = buffer.find("\r")
        nl = buffer.find("\n")
        if cr == -1 and nl == -1:
            break
        if cr != -1 and (nl == -1 or cr < nl):
            part, buffer = buffer[:cr], buffer[cr + 1 :]
            normalized = normalize_terminal_line(part)
            if normalized:
                emit(normalized, True)
            continue
        part, buffer = buffer[:nl], buffer[nl + 1 :]
        normalized = normalize_terminal_line(part)
        if normalized:
            emit(normalized, is_apt_status_line(normalized))
    return buffer


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

    ``sink`` is any callable taking ``(stream_name, line, *, transient=False)``
    where ``stream_name`` is ``"stdout"`` or ``"stderr"``. When ``transient`` is
    ``True`` the line came from a ``\\r`` in-place TTY update (apt progress).
    The function returns only after the subprocess exits.

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

    if sink is not None:
        assert proc.stdout is not None and proc.stderr is not None
        # Read stdout/stderr into a queue and call ``sink`` from a separate
        # coroutine.  Calling ``sink`` directly inside the pump loops can
        # deadlock: a slow sink (e.g. RichLog writes in ApplyDialog) blocks
        # the event loop so the other pipe is never drained, apt fills the
        # kernel pipe buffer, and the subprocess blocks on write.
        line_queue: asyncio.Queue[tuple[str, str, bool] | None] = asyncio.Queue()

        async def _pump(stream: asyncio.StreamReader, name: str) -> None:
            buffer = ""
            while True:
                chunk = await stream.read(4096)
                if not chunk:
                    if buffer:
                        normalized = normalize_terminal_line(buffer)
                        if normalized:
                            await line_queue.put(
                                (
                                    name,
                                    normalized,
                                    is_apt_status_line(normalized),
                                )
                            )
                    await line_queue.put(None)
                    return
                buffer += chunk.decode(errors="replace")

                def emit(text: str, transient: bool) -> None:
                    line_queue.put_nowait((name, text, transient))

                buffer = _emit_terminal_fragments(buffer, emit)

        async def _drain() -> None:
            closed = 0
            while closed < 2:
                item = await line_queue.get()
                if item is None:
                    closed += 1
                    continue
                stream_name, line, transient = item
                sink(stream_name, line, transient=transient)
                await asyncio.sleep(0)

        await asyncio.gather(
            _pump(proc.stdout, "stdout"),
            _pump(proc.stderr, "stderr"),
            _drain(),
        )

    returncode = await proc.wait()
    return StreamResult(returncode=returncode)


def run_streaming_sync(
    op: AptOperation,
    privilege: Privilege,
    *,
    password: str | None = None,
    sink: Callable[[str, str], None] | None = None,
) -> StreamResult:
    """Run an :class:`AptOperation` synchronously (for Textual thread workers).

    Unlike :func:`run_streaming`, this uses blocking ``subprocess`` I/O only
    and never touches asyncio — safe to call from a ``@work(thread=True)``
    worker while Textual's own event loop is running in the main thread.
    """
    cmd = build_apt_command(op.argv(), privilege)
    env = dict(os.environ)
    env.setdefault("DEBIAN_FRONTEND", "noninteractive")

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE if password is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )

    if password is not None and proc.stdin is not None:
        proc.stdin.write(f"{password}\n".encode())
        with contextlib.suppress(BrokenPipeError, OSError):
            proc.stdin.flush()
        proc.stdin.close()

    if sink is not None and proc.stdout is not None and proc.stderr is not None:
        line_queue: Queue[tuple[str, str, bool] | None] = Queue()

        def _pump(stream, name: str) -> None:
            buffer = ""
            while True:
                chunk = stream.read(4096)
                if not chunk:
                    if buffer:
                        normalized = normalize_terminal_line(buffer)
                        if normalized:
                            line_queue.put(
                                (
                                    name,
                                    normalized,
                                    is_apt_status_line(normalized),
                                )
                            )
                    line_queue.put(None)
                    return
                buffer += chunk.decode(errors="replace")

                def emit(text: str, transient: bool) -> None:
                    line_queue.put((name, text, transient))

                buffer = _emit_terminal_fragments(buffer, emit)

        stdout_thread = threading.Thread(
            target=_pump, args=(proc.stdout, "stdout"), daemon=True
        )
        stderr_thread = threading.Thread(
            target=_pump, args=(proc.stderr, "stderr"), daemon=True
        )
        stdout_thread.start()
        stderr_thread.start()

        closed = 0
        while closed < 2:
            item = line_queue.get()
            if item is None:
                closed += 1
                continue
            stream_name, line, transient = item
            sink(stream_name, line, transient=transient)

        stdout_thread.join(timeout=1)
        stderr_thread.join(timeout=1)

    returncode = proc.wait()
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

    def sink(name: str, line: str, *, transient: bool = False) -> None:
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

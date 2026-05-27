"""ICMP probe helpers shared by the Test Network dialog and the Ping plugin.

* :func:`ping_probe` runs a single ICMP echo and returns ``(ok, latency_ms)``.
* :func:`run_probes` paces N probes one-per-second (or any interval) and
  calls a progress callback after each so the UI can update live.
* :func:`probe_dots` builds the Rich ``Text`` of coloured dots used by
  both dialogs.

Keeping these in one place means the two surfaces share the same
spinner-plus-dots visual treatment and the same per-probe pacing rules.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable

from rich.text import Text

from ..utils.logging import get_logger

log = get_logger("probes")

_DEFAULT_TIMEOUT_S = 2
_DEFAULT_INTERVAL_S = 1.0


async def ping_probe(host: str, *, timeout: int = _DEFAULT_TIMEOUT_S) -> tuple[bool, float | None]:
    """Send a single ICMP echo to ``host``.

    Returns ``(ok, latency_ms_or_None)``. Never raises — every failure
    mode collapses to ``(False, None)`` so the caller doesn't need a
    try/except around each probe.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "ping",
            "-c",
            "1",
            "-W",
            str(timeout),
            host,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout + 1)
    except (TimeoutError, OSError):
        return False, None
    if proc.returncode != 0:
        return False, None
    match = re.search(r"time=([\d.]+)\s*ms", stdout.decode())
    if match:
        return True, float(match.group(1))
    return True, None


async def run_probes(
    host: str,
    *,
    count: int = 3,
    interval: float = _DEFAULT_INTERVAL_S,
    timeout: int = _DEFAULT_TIMEOUT_S,
    on_progress: Callable[[list[bool | None], list[float]], None] | None = None,
) -> tuple[list[bool | None], list[float]]:
    """Run ``count`` ICMP probes paced ``interval`` seconds apart.

    Probe 1 fires immediately so the operator sees feedback right away;
    each subsequent probe waits ``interval`` first. ``on_progress`` (if
    given) is called after every probe with the live ``(results,
    latencies)`` snapshot — perfect for a per-row UI update.
    """
    results: list[bool | None] = [None] * count
    latencies: list[float] = []
    for i in range(count):
        if i > 0:
            await asyncio.sleep(interval)
        ok, lat = await ping_probe(host, timeout=timeout)
        results[i] = ok
        if ok and lat is not None:
            latencies.append(lat)
        if on_progress is not None:
            on_progress(results, latencies)
    return results, latencies


def probe_dots(
    results: list[bool | None],
    *,
    success: str = "green",
    error: str = "red",
    faint: str = "grey50",
    trailing: str = "",
) -> Text:
    """Compose the coloured-dot status line for ``results``.

    ``None`` ⇒ probe still in flight (faint dot).
    ``True`` ⇒ success (green dot).
    ``False`` ⇒ failure (red dot).
    """
    line = Text()
    for outcome in results:
        if outcome is None:
            line.append("●", style=faint)
        elif outcome:
            line.append("●", style=success)
        else:
            line.append("●", style=error)
        line.append(" ")
    if trailing:
        line.append(trailing)
    return line


def summarise(results: list[bool | None], latencies: list[float]) -> tuple[bool, str]:
    """Reduce a probe run to (overall_ok, summary_string).

    All-success ⇒ ``(True,  "OK (avg ms)")``.
    All-fail    ⇒ ``(False, "FAIL (n/n lost)")``.
    Mixed       ⇒ ``(False, "PARTIAL (k/n lost, avg ms)")``.
    """
    count = len(results)
    successes = sum(1 for r in results if r)
    if successes == count:
        avg = sum(latencies) / len(latencies) if latencies else 0.0
        return True, f"OK ({avg:.1f} ms)"
    if successes == 0:
        return False, f"FAIL ({count}/{count} lost)"
    lost = count - successes
    avg = sum(latencies) / len(latencies) if latencies else 0.0
    return False, f"PARTIAL ({lost}/{count} lost, avg {avg:.1f} ms)"

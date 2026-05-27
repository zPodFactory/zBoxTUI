"""Network: DNS Lookup — resolve a hostname against a chosen resolver.

Asks for a hostname (prefilled from ``network.dns_test_default_target``)
and a resolver. ``Ctrl+T`` cycles the resolver field through common
presets (``system``, ``1.1.1.1``, ``8.8.8.8``, ``9.9.9.9``,
``208.67.222.222``); the field is also a plain text input, so an
operator can type the IP of any internal resolver they want to test.

* ``system`` (case-insensitive) ⇒ ``libc getaddrinfo`` — what every
  other program on this box would see.
* Anything else ⇒ ``dig @<value> +short host`` — useful for spotting
  cases where the local resolver hands back different data than a
  public one, or for sanity-checking a freshly-deployed corporate
  resolver.
"""

from __future__ import annotations

import asyncio
import shutil
import socket
from typing import TYPE_CHECKING

from rich.spinner import Spinner
from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Static

from zboxtui.core.utils.config import get_config
from zboxtui.core.utils.logging import get_logger
from zboxtui.core.widgets import DCUI_DIALOG_CSS

if TYPE_CHECKING:
    from zboxtui.app import ZBoxTUI


_SPINNER_REFRESH = 1 / 15

# Ctrl+T cycle. "system" first so the default behaviour matches what
# the rest of the box sees; the public resolvers are in popularity order.
_RESOLVER_PRESETS: tuple[str, ...] = (
    "system",
    "1.1.1.1",          # Cloudflare
    "8.8.8.8",          # Google
    "9.9.9.9",          # Quad9
    "208.67.222.222",   # OpenDNS / Cisco Umbrella
)

log = get_logger("menu.network_dns_lookup")


def _format_records(addrs: list[str]) -> str:
    """One record per line so long answer sets (mixed v4/v6 or many
    CDN nodes) wrap cleanly in the status pane instead of overflowing
    a single line."""
    return "\n".join(addrs) if addrs else "(no records)"


async def resolve_system(host: str) -> tuple[bool, str]:
    """Use libc getaddrinfo (off the event loop) to resolve ``host``.

    Splits v4 vs v6 just for readability — v4 first, v6 next — so the
    common-case answer (one A record) stays on top and the longer v6
    addresses don't push the v4 line out of view.
    """
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        return False, f"resolve failed: {exc}"
    v4 = sorted({info[4][0] for info in infos if info[0] == socket.AF_INET})
    v6 = sorted({info[4][0] for info in infos if info[0] == socket.AF_INET6})
    return True, _format_records(v4 + v6)


async def resolve_dig(host: str, server: str) -> tuple[bool, str]:
    """Use ``dig @<server> +short host`` to resolve via a chosen DNS server.

    Queries both A and AAAA so v6-only / dual-stack records are
    surfaced. Output is one record per line.
    """
    if shutil.which("dig") is None:
        return False, "dig not installed"

    async def _one(rrtype: str) -> list[str]:
        try:
            proc = await asyncio.create_subprocess_exec(
                "dig",
                f"@{server}",
                "+short",
                "+timeout=3",
                "+tries=1",
                host,
                rrtype,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=6)
        except (TimeoutError, OSError):
            return []
        if proc.returncode != 0:
            return []
        return [line for line in stdout.decode().strip().splitlines() if line]

    v4_lines, v6_lines = await asyncio.gather(_one("A"), _one("AAAA"))
    records = v4_lines + v6_lines
    if not records:
        return False, "no answer"
    return True, _format_records(records)


class DnsLookupDialog(ModalScreen[None]):
    """Hostname + resolver inputs with a coloured answer line."""

    BINDINGS = [
        Binding("escape", "close", "Close", show=False),
        Binding("q", "close", "Close", show=False),
        Binding("ctrl+t", "cycle_resolver", "Next Resolver", show=False),
    ]

    DEFAULT_CSS = DCUI_DIALOG_CSS.format(dialog_class="DnsLookupDialog", width=60) + """
    DnsLookupDialog .form-row {
        height: 1;
        width: 100%;
    }

    DnsLookupDialog .form-label {
        width: 13;
        color: $z-fg;
    }

    DnsLookupDialog .form-input {
        width: 1fr;
        background: $z-mantle;
        color: $z-panel-fg;
        border: none;
        height: 1;
    }

    DnsLookupDialog .form-input:focus {
        background: $z-panel-focus;
    }

    DnsLookupDialog #status-row {
        height: auto;
        margin-top: 1;
    }

    DnsLookupDialog .status-label {
        width: 13;
        color: $z-fg;
    }

    DnsLookupDialog .status-value {
        width: 1fr;
        height: auto;
        color: $z-fg;
    }

    DnsLookupDialog .status-value.--success {
        color: $z-success;
    }

    DnsLookupDialog .status-value.--failure {
        color: $z-error;
    }

    DnsLookupDialog .status-value.--pending {
        color: $z-fg-faint;
    }
    """

    def __init__(self, default_host: str) -> None:
        super().__init__()
        self._default_host = default_host

    def compose(self) -> ComposeResult:
        with Container(id="dialog-outer"):
            with Vertical(id="dialog-header"):
                yield Static("")
                yield Static("DNS Lookup", id="dialog-title")
                yield Static("")
                yield Static(
                    "Resolve a hostname. Resolver accepts 'system' (libc) "
                    "or any DNS server IP. Ctrl+T cycles presets.",
                    id="dialog-subtitle",
                )
                yield Static("")
            with Vertical(id="dialog-body"):
                with Horizontal(classes="form-row"):
                    yield Static("Hostname:", classes="form-label")
                    yield Input(
                        value=self._default_host,
                        placeholder="example.com",
                        classes="form-input",
                        id="host-input",
                    )
                with Horizontal(classes="form-row"):
                    yield Static("Resolver:", classes="form-label")
                    yield Input(
                        value=_RESOLVER_PRESETS[0],
                        placeholder="system | 1.1.1.1 | 8.8.8.8 | …",
                        classes="form-input",
                        id="resolver-input",
                    )
                with Horizontal(id="status-row"):
                    yield Static("Answer:", classes="status-label")
                    yield Static(
                        "(press Enter to resolve)",
                        classes="status-value --pending",
                        id="dns-status",
                    )
                yield Static("")
                yield Static(
                    "<Enter> Resolve    <Ctrl+T> Cycle Presets    "
                    "<Tab> Next Field    <Esc> Close",
                    id="dialog-footer",
                )

    def on_mount(self) -> None:
        self.query_one("#host-input", Input).focus()

    @on(Input.Submitted)
    def _on_submitted(self, event: Input.Submitted) -> None:
        # Submitting the host field from anywhere triggers a lookup.
        # If the user is editing the resolver field, Enter also fires
        # the lookup — that matches "type the resolver, hit Enter".
        if event.input.id in {"host-input", "resolver-input"}:
            self._run_lookup()

    def action_cycle_resolver(self) -> None:
        """Cycle the Resolver input through the preset values.

        We look up the *current* value in the preset list — that way
        if the operator has typed a custom IP, ``Ctrl+T`` snaps back
        to ``system`` rather than appending; if they're already on a
        preset, it advances to the next.
        """
        resolver_input = self.query_one("#resolver-input", Input)
        current = resolver_input.value.strip().lower()
        try:
            idx = _RESOLVER_PRESETS.index(current)
            next_idx = (idx + 1) % len(_RESOLVER_PRESETS)
        except ValueError:
            next_idx = 0  # Custom value — snap to first preset.
        resolver_input.value = _RESOLVER_PRESETS[next_idx]

    def _run_lookup(self) -> None:
        host = self.query_one("#host-input", Input).value.strip()
        resolver = self.query_one("#resolver-input", Input).value.strip() or "system"
        status = self.query_one("#dns-status", Static)
        if not host:
            status.remove_class("--success", "--pending")
            status.add_class("--failure")
            status.update("Hostname is empty")
            return
        status.remove_class("--success", "--failure")
        status.add_class("--pending")
        status.update(Spinner("dots", text=f" resolving {host} via {resolver}…"))
        status.auto_refresh = _SPINNER_REFRESH
        self._do_lookup(host, resolver)

    @work(exclusive=True)
    async def _do_lookup(self, host: str, resolver: str) -> None:
        if resolver.lower() == "system":
            success, message = await resolve_system(host)
        else:
            success, message = await resolve_dig(host, server=resolver)
        status = self.query_one("#dns-status", Static)
        status.auto_refresh = None
        status.remove_class("--pending")
        status.add_class("--success" if success else "--failure")
        status.update(message)

    def action_close(self) -> None:
        status = self.query_one("#dns-status", Static)
        status.auto_refresh = None
        self.dismiss(None)


def show_network_dns_lookup_dialog(app: ZBoxTUI) -> None:
    cfg = get_config()
    log.info("Opening Network: DNS Lookup")
    app.push_screen(DnsLookupDialog(cfg.dns_test_default_target or "example.com"))

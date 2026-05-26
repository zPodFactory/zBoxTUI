"""Configure Hostname / Domain menu item.

Lets the operator set the system's short hostname and DNS domain, with
a live preview of the resulting FQDN. RFC 1123 hostname validation is
applied as the user types. On submit, the change is applied with
``hostnamectl set-hostname`` (which updates ``/etc/hostname`` and the
kernel name in one call) and ``/etc/hosts`` is patched so ``hostname
-f`` resolves to the new FQDN.

Requires root. When running unprivileged, the apply step surfaces the
underlying error in the dialog without losing the operator's input.
"""

from __future__ import annotations

import re
import shutil
import socket
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Static

from ..utils.logging import get_logger
from ..widgets.dcui_dialog import DCUI_DIALOG_CSS, MessageDialog

if TYPE_CHECKING:
    from ...app import ZBoxTUI

log = get_logger("menu.hostname")

_LABEL_RE = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$")
_MAX_FQDN = 253


def validate_hostname(label: str) -> str | None:
    """Return None if ``label`` is a valid single hostname label,
    otherwise a short user-facing error string.

    Enforces RFC 1123: 1-63 chars, ASCII alphanumerics plus hyphen,
    no leading/trailing hyphen. (RFC 952 forbade leading digits;
    RFC 1123 relaxed that — we follow 1123.)
    """
    if not label:
        return "Hostname is required"
    if len(label) > 63:
        return "Hostname must be 1-63 characters"
    if not _LABEL_RE.match(label):
        return "Hostname: letters/digits/hyphen, no leading/trailing -"
    return None


def validate_domain(domain: str) -> str | None:
    """Return None if ``domain`` is a valid DNS domain (or empty),
    otherwise a short user-facing error string.

    Empty is allowed — that means "no domain, just the short
    hostname". Each dot-separated label follows the same rules as
    :func:`validate_hostname`.
    """
    if not domain:
        return None
    if domain.endswith("."):
        domain = domain[:-1]
    if not domain:
        return "Domain is empty"
    for label in domain.split("."):
        if validate_hostname(label) is not None:
            return f"Invalid domain label: {label!r}"
    return None


def build_fqdn(hostname: str, domain: str) -> str:
    """Concatenate hostname + domain (if any) into an FQDN."""
    hostname = hostname.strip()
    domain = domain.strip().strip(".")
    if not domain:
        return hostname
    return f"{hostname}.{domain}"


def validate_fqdn(hostname: str, domain: str) -> str | None:
    err = validate_hostname(hostname)
    if err:
        return err
    err = validate_domain(domain)
    if err:
        return err
    if len(build_fqdn(hostname, domain)) > _MAX_FQDN:
        return f"FQDN exceeds {_MAX_FQDN} characters"
    return None


def current_hostname_and_domain() -> tuple[str, str]:
    """Best-effort guess at the running system's short name + domain.

    Uses ``socket.gethostname()`` for the short name (always works)
    and ``socket.getfqdn()`` to recover the domain by stripping the
    short name from the front of the FQDN. Returns ``("", "")`` if
    the system has no useful hostname configured.
    """
    short = socket.gethostname().split(".", 1)[0]
    try:
        fqdn = socket.getfqdn()
    except OSError:
        fqdn = short
    domain = fqdn[len(short) + 1 :] if "." in fqdn and fqdn.startswith(short + ".") else ""
    return short, domain


def apply_hostname(hostname: str, domain: str) -> tuple[bool, str]:
    """Apply the new hostname + domain to the system.

    Runs ``hostnamectl set-hostname <fqdn>`` (kernel + ``/etc/hostname``)
    and rewrites the ``127.0.1.1`` line in ``/etc/hosts`` so
    ``hostname -f`` resolves to the new FQDN.

    Returns ``(ok, message)``. ``ok=False`` means at least one step
    failed; ``message`` is suitable for direct display in the dialog.
    """
    fqdn = build_fqdn(hostname, domain)
    short = hostname.strip()

    if shutil.which("hostnamectl") is None:
        return False, "hostnamectl not found — install systemd or run as root"

    try:
        result = subprocess.run(
            ["hostnamectl", "set-hostname", fqdn],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        return False, "hostnamectl timed out"
    except OSError as exc:
        return False, f"hostnamectl failed: {exc}"

    if result.returncode != 0:
        return False, (result.stderr.strip() or "hostnamectl failed").splitlines()[0]

    # Patch /etc/hosts so `hostname -f` returns the FQDN.
    ok_hosts, hosts_msg = _patch_etc_hosts(fqdn, short)
    if not ok_hosts:
        return False, hosts_msg

    return True, f"Hostname set to {fqdn}"


def _patch_etc_hosts(fqdn: str, short: str) -> tuple[bool, str]:
    """Update the 127.0.1.1 line in ``/etc/hosts`` to point to FQDN.

    Debian's convention: a line ``127.0.1.1 <fqdn> <short>`` provides
    the FQDN lookup that ``hostname -f`` uses. We replace any existing
    127.0.1.1 line; if none exists we append one.
    """
    path = Path("/etc/hosts")
    try:
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    except (OSError, PermissionError) as exc:
        return False, f"/etc/hosts read failed: {exc}"

    new_line = f"127.0.1.1\t{fqdn} {short}\n"
    rewritten: list[str] = []
    found = False
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("127.0.1.1"):
            rewritten.append(new_line)
            found = True
        else:
            rewritten.append(line)
    if not found:
        # Insert after the loopback (127.0.0.1) line if we find one,
        # otherwise append to the end.
        for idx, line in enumerate(rewritten):
            if line.lstrip().startswith("127.0.0.1"):
                rewritten.insert(idx + 1, new_line)
                found = True
                break
        if not found:
            rewritten.append(new_line)

    try:
        path.write_text("".join(rewritten), encoding="utf-8")
    except (OSError, PermissionError) as exc:
        return False, f"/etc/hosts write failed: {exc}"

    return True, ""


class HostnameDialog(ModalScreen[bool]):
    """Edit the system's hostname + DNS domain with live FQDN preview."""

    app: ZBoxTUI

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("q", "cancel", "Cancel", show=False),
        Binding("tab", "focus_next_field", "Next Field", show=False, priority=True),
        Binding("shift+tab", "focus_previous_field", "Prev Field", show=False, priority=True),
    ]

    DEFAULT_CSS = DCUI_DIALOG_CSS.format(dialog_class="HostnameDialog", width=55) + """
    HostnameDialog .form-row {
        height: 1;
        width: 100%;
    }

    HostnameDialog .form-label {
        width: 14;
        color: $z-fg;
        height: 1;
        content-align: left middle;
    }

    HostnameDialog .form-input {
        width: 1fr;
        background: $z-mantle;
        color: $z-panel-fg;
        border: none;
        height: 1;
    }

    HostnameDialog .form-input:focus {
        background: $z-panel-focus;
    }

    HostnameDialog #fqdn-row {
        height: 1;
        margin-top: 1;
    }

    HostnameDialog #fqdn-value {
        width: 1fr;
        color: $z-success;
        text-style: bold;
    }

    HostnameDialog #error-message {
        color: $z-error;
        height: 1;
        text-align: center;
    }
    """

    _INPUTS = ("hostname-input", "domain-input")

    def compose(self) -> ComposeResult:
        short, domain = current_hostname_and_domain()
        with Container(id="dialog-outer"):
            with Vertical(id="dialog-header"):
                yield Static("")
                yield Static("Configure Hostname", id="dialog-title")
                yield Static("")
                yield Static(
                    "Set the system hostname and DNS domain. Both are "
                    "applied immediately.",
                    id="dialog-subtitle",
                )
                yield Static("")
            with Vertical(id="dialog-body"):
                with Horizontal(classes="form-row"):
                    yield Static("Hostname:", classes="form-label")
                    yield Input(
                        value=short,
                        placeholder="myhost",
                        classes="form-input",
                        id="hostname-input",
                    )
                with Horizontal(classes="form-row"):
                    yield Static("Domain:", classes="form-label")
                    yield Input(
                        value=domain,
                        placeholder="example.com",
                        classes="form-input",
                        id="domain-input",
                    )
                with Horizontal(id="fqdn-row"):
                    yield Static("FQDN:", classes="form-label")
                    yield Static(build_fqdn(short, domain), id="fqdn-value")
                yield Static("", id="error-message")
                yield Static("")
                yield Static("<Enter> Apply    <Tab> Next    <Esc> Cancel", id="dialog-footer")

    def on_mount(self) -> None:
        self.query_one("#hostname-input", Input).focus()
        self.app.save_debug_screenshot("hostname_dialog")
        self._refresh_preview()

    @on(Input.Changed)
    def _on_input_changed(self, event: Input.Changed) -> None:  # noqa: ARG002 - event unused
        self._refresh_preview()

    @on(Input.Submitted)
    def _on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "hostname-input":
            self.query_one("#domain-input", Input).focus()
            return
        self._submit()

    def _refresh_preview(self) -> None:
        hostname = self.query_one("#hostname-input", Input).value
        domain = self.query_one("#domain-input", Input).value
        fqdn = build_fqdn(hostname, domain)
        err = validate_fqdn(hostname, domain) if hostname else None
        preview = self.query_one("#fqdn-value", Static)
        error_msg = self.query_one("#error-message", Static)
        if err:
            preview.update(fqdn or "(invalid)")
            preview.remove_class("--ok")
            error_msg.update(err)
        else:
            preview.update(fqdn)
            error_msg.update("")

    def _submit(self) -> None:
        hostname = self.query_one("#hostname-input", Input).value.strip()
        domain = self.query_one("#domain-input", Input).value.strip()
        error_msg = self.query_one("#error-message", Static)

        err = validate_fqdn(hostname, domain)
        if err:
            error_msg.update(err)
            return

        log.info("Applying hostname=%s domain=%s", hostname, domain)
        ok, message = apply_hostname(hostname, domain)
        if not ok:
            log.error("Hostname apply failed: %s", message)
            error_msg.update(message)
            return

        self.app.push_screen(
            MessageDialog("Hostname Updated", message),
            callback=lambda _: self.dismiss(True),
        )

    def action_focus_next_field(self) -> None:
        current = self.focused.id if self.focused else ""
        if current in self._INPUTS:
            idx = self._INPUTS.index(current)
            target = self._INPUTS[(idx + 1) % len(self._INPUTS)]
            self.query_one(f"#{target}", Input).focus()

    def action_focus_previous_field(self) -> None:
        current = self.focused.id if self.focused else ""
        if current in self._INPUTS:
            idx = self._INPUTS.index(current)
            target = self._INPUTS[(idx - 1) % len(self._INPUTS)]
            self.query_one(f"#{target}", Input).focus()

    def action_cancel(self) -> None:
        self.dismiss(False)


def show_hostname_dialog(app: ZBoxTUI) -> None:
    """Push the hostname/domain editor."""
    log.info("Opening Configure Hostname dialog")
    app.push_screen(HostnameDialog())

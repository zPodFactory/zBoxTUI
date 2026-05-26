# zBoxTUI

An ESXi DCUI-style TUI for Debian. Drops onto a virtual console as the
operator interface for a `zbox` deployment: configure the hostname,
manage the root password, edit network settings, install curated
package sets, inspect live system stats, and run quick connectivity
tests — all from the terminal, no shell required.

Built on [Textual](https://textual.textualize.io/) (Python 3.11+),
ships with six colour themes (Catppuccin Mocha by default, VMware ESXi
yellow/grey for the classic look), and exposes a small plugin API so
new menu entries can be added by dropping a single `.py` file into
`src/zboxtui/plugins/`.

## Screenshots

### Dashboard (Catppuccin Mocha)

![Dashboard — Catppuccin Mocha](docs/screenshots/01_dashboard_catppuccin.svg)

The top panel shows OS + hostname + CPU/memory facts on the left and
live CPU/MEM usage bars on the right. The bottom panel splits into
network interfaces (with default gateway annotation) and storage usage
per filesystem. Refresh runs every 2 seconds by default; turn it off
or change the interval in `Configure Settings`.

### Dashboard (VMware ESXi)

![Dashboard — VMware ESXi theme](docs/screenshots/01_dashboard_esxi.svg)

### Login (F2) and Main Menu

![Login dialog](docs/screenshots/02_login_catppuccin.svg)

Press **F2** on the dashboard, enter the root password (verified via
PAM through `su -c true root`), and the customization menu opens:

![System customization menu](docs/screenshots/03_menu_catppuccin.svg)

### Configure Hostname

![Configure Hostname dialog](docs/screenshots/04_hostname_catppuccin.svg)

Sets the kernel hostname (`hostnamectl set-hostname …`) and patches
the `127.0.1.1` line in `/etc/hosts` so `hostname -f` returns the
FQDN. Validation is RFC 1123: 1-63 chars, letters/digits/hyphen, no
leading or trailing hyphen, per label.

### Configure Settings

![Configure Settings dialog](docs/screenshots/06_settings_catppuccin.svg)

Edits and persists the `[dashboard]`, `[network]`, and `[general]`
sections of `app.conf`. The currently-loaded config file is shown in
the subtitle; writes go to the user-scoped `~/.config/zboxtui/app.conf`
unless the system file at `/etc/zboxtui/app.conf` is writable.

### Plugins: Ping + DNS Lookup

| Ping                                              | DNS Lookup                                    |
|---------------------------------------------------|-----------------------------------------------|
| ![Ping plugin](docs/screenshots/07_ping_catppuccin.svg) | ![DNS Lookup plugin](docs/screenshots/08_dns_catppuccin.svg) |

Live progress bars and animated screens (apt installs, system metrics
sparklines, the auto-dim transition) are not capturable as static SVG.
Use [`asciinema`](https://asciinema.org/) to record them — `asciinema
rec demo.cast` while running `zboxtui` produces a recording you can
embed in any markdown viewer that renders the [asciinema-player]
component.

[asciinema-player]: https://github.com/asciinema/asciinema-player

## Quickstart

```bash
# Install dependencies (uses uv — https://docs.astral.sh/uv/)
uv sync

# Run the TUI
uv run zboxtui

# Force a specific theme for this run
uv run zboxtui --theme vmware-esxi

# Print a sample config to stdout
uv run zboxtui --generate-config

# Use a non-default config file
uv run zboxtui --config /path/to/app.conf

# Save SVG snapshots of every screen visited
uv run zboxtui --debug-svg
```

## Configuration

The config file is searched, first hit wins:

1. `--config <path>` on the CLI.
2. `$ZBOXTUI_CONFIG`.
3. `~/.config/zboxtui/app.conf` (`$XDG_CONFIG_HOME` honoured).
4. `/etc/zboxtui/app.conf`.

`uv run zboxtui --generate-config` prints a fully commented sample.
Highlights:

```ini
[general]
log_file = /var/log/zboxtui.log
log_level = INFO
confirm_shutdown = true

[dashboard]
# Hide the right-hand column (CPU/MEM bars + Storage panel)
display_live_information = true
refresh_interval_seconds = 2.0

[network]
test_default_target = 1.1.1.1
dns_test_default_target = example.com

[theme]
# catppuccin-mocha (default), vmware-esxi, nord, gruvbox,
# tokyo-night, atom-one-dark
name = catppuccin-mocha
```

## Architecture

```
src/zboxtui/
├── __main__.py                  # CLI entry (argparse + init_config + init_logging)
├── app.py                       # ZBoxTUI(App) — themes, screens, menu dispatch
├── plugin_loader.py             # discover_plugins() — globs plugins/*.py
│
├── core/                        # Permanent, built-in surface
│   ├── themes.py                # 6 Textual Theme objects
│   ├── screens/
│   │   ├── dashboard.py         # Home screen (F2 → login, F12 → shutdown)
│   │   └── menu.py              # Builds menu from CORE_MENU_ITEMS + plugins
│   ├── widgets/                 # DCUIMenu / DCUIHeader / DCUIFooter / dialog kit
│   ├── utils/                   # config.py, logging.py, system.py
│   └── menu_items/              # Built-in (non-plugin) entries
│       ├── hostname.py          # Configure Hostname
│       ├── network.py           # Configure / Restart Network
│       ├── network_test.py      # Test Network
│       ├── packages.py          # Configure Packages
│       ├── password.py          # Configure Password
│       ├── settings.py          # Configure Settings
│       └── theme.py             # Configure Theme
│
└── plugins/                     # Auto-discovered, ASCII filename order
    ├── 01_view_system_logs.py
    ├── 02_view_zbox_logs.py
    ├── 03_configure_packages.py
    ├── 60_themes.py
    ├── 80_system_metrics.py
    ├── 90_ping.py
    ├── 91_dns_lookup.py
    └── 99_test_dialog.py
```

### Application flow

1. `__main__.py` parses CLI args, calls `init_config()` and `init_logging()`,
   then imports and runs `ZBoxTUI`.
2. `ZBoxTUI.__init__` registers every Theme (must happen before any
   CSS is parsed) and applies the configured one.
3. `on_mount` pushes `DashboardScreen`.
4. F2 → `LoginDialog`; PAM auth runs in a background thread.
5. On success, `MenuScreen` rebuilds its menu dynamically:
   - **General** group from `CORE_MENU_ITEMS`.
   - **Plugins** group from `discover_plugins()`.
   - The `action_id → Callable` map is handed to the app via
     `set_menu_handlers`.
6. `app.handle_menu_action(action_id)` dispatches via the registry —
   no hard-coded `if/elif` ladder.

## Plugin authoring

A plugin is a `.py` file in `src/zboxtui/plugins/` whose name does not
start with `_`. Files load in ASCII filename order — so `01_` runs
before `90_` before `99_`. Each file must export:

```python
MENU_LABEL: str             # Shown in the menu list
MENU_DESCRIPTION: str       # Shown in the right-hand detail pane
def show_dialog(app) -> None: ...   # Called when Enter is pressed
```

Optional knob:

```python
MENU_ENABLED = False        # Skip this file without deleting it
```

Plugins import the styled widget toolkit from `zboxtui.core.widgets`:

```python
from zboxtui.core.widgets import (
    DCUI_DIALOG_CSS,    # Shared dialog stylesheet template
    MessageDialog,      # Simple OK/Cancel modal
    ping_host,          # async ping_host(target, count=3) -> (ok, msg)
)
from zboxtui.core.utils.logging import get_logger
```

### Full example: the `Ping` plugin

The Ping plugin in `src/zboxtui/plugins/90_ping.py` is a complete
reference implementation. It:

- Reads its default target from `network.test_default_target` in the
  config so operators can override it per deployment.
- Uses `DCUI_DIALOG_CSS.format(...)` to inherit the shared dialog
  chrome (centered modal, panel/body sections, themed colours).
- Spawns the actual ping in a `@work(exclusive=True)` worker so the
  UI stays responsive while ICMP probes run.
- Surfaces success/failure by toggling a `--success` / `--failure` /
  `--pending` class on the status line, which the stylesheet binds to
  the theme's `$z-success`, `$z-error`, `$z-fg-faint` variables.

Skeleton:

```python
from rich.spinner import Spinner
from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Static

from zboxtui.core.utils.config import get_config
from zboxtui.core.widgets import DCUI_DIALOG_CSS, ping_host

MENU_LABEL = "Ping"
MENU_DESCRIPTION = "Ping any host or IP. Defaults to the configured ping target."


class PingDialog(ModalScreen[None]):
    BINDINGS = [
        Binding("escape", "close", "Close", show=False),
        Binding("r", "retest", "Retest", show=False),
    ]
    DEFAULT_CSS = DCUI_DIALOG_CSS.format(dialog_class="PingDialog", width=55) + """
    PingDialog .status-value.--success { color: $z-success; }
    PingDialog .status-value.--failure { color: $z-error; }
    PingDialog .status-value.--pending { color: $z-fg-faint; }
    """

    def __init__(self, target: str) -> None:
        super().__init__()
        self._target = target

    def compose(self):
        with Container(id="dialog-outer"):
            with Vertical(id="dialog-header"):
                yield Static("Ping", id="dialog-title")
            with Vertical(id="dialog-body"):
                yield Input(value=self._target, id="target-input")
                yield Static(
                    "(press Enter to start)",
                    classes="status-value --pending",
                    id="ping-status",
                )

    @on(Input.Submitted)
    def _on_submit(self, event):
        self._run(event.value)

    def action_retest(self):
        self._run(self.query_one("#target-input", Input).value)

    def action_close(self):
        self.dismiss(None)

    def _run(self, target: str) -> None:
        status = self.query_one("#ping-status", Static)
        status.remove_class("--success", "--failure")
        status.add_class("--pending")
        status.update(Spinner("dots", text=f" pinging {target}…"))
        self._do_ping(target)

    @work(exclusive=True)
    async def _do_ping(self, target: str) -> None:
        ok, msg = await ping_host(target)
        status = self.query_one("#ping-status", Static)
        status.remove_class("--pending")
        status.add_class("--success" if ok else "--failure")
        status.update(f"{target}: {msg}")


def show_dialog(app) -> None:
    target = get_config().network_test_default_target or "1.1.1.1"
    app.push_screen(PingDialog(target))
```

`91_dns_lookup.py` is a second worked example: same shape, but
resolves a hostname via `socket.getaddrinfo` (system resolver) or
`dig @1.1.1.1` (public resolver) depending on a `Ctrl+T` toggle.

### Theming hooks

Plugins should refer to the shared theme variables (`$z-bg`, `$z-fg`,
`$z-panel`, `$z-accent`, `$z-success`, `$z-error`, `$z-fg-faint`, …)
rather than hardcoding colours. That way a single theme switch flips
every plugin together. See `src/zboxtui/core/themes.py` for the full
list.

## Production deployment (tty6 login shell on packer-zbox)

The intended deployment for `zbox` boxes is to bind `zboxtui` to a
dedicated virtual console. Install the system package, then drop in a
systemd override that auto-logs root onto tty6 with `zboxtui` as the
login program. Anyone who switches to that console (Ctrl+Alt+F6 at
the host) lands directly in the DCUI without seeing a shell prompt.

### Install

```bash
# 1. Build a wheel and install system-wide
uv build
sudo pip install --break-system-packages dist/zboxtui-*.whl
# (or use pipx, or your distro's packaging — the goal is to land
#  /usr/local/bin/zboxtui owned by root)

# 2. Ship the config + log directory
sudo install -d -m 0755 /etc/zboxtui /var/log
sudo install -m 0644 packaging/app.conf.sample /etc/zboxtui/app.conf

# 3. Install the getty drop-in
sudo install -d /etc/systemd/system/getty@tty6.service.d
sudo install -m 0644 packaging/zboxtui-tty6.conf \
    /etc/systemd/system/getty@tty6.service.d/override.conf
sudo systemctl daemon-reload
sudo systemctl restart getty@tty6
```

### What the systemd drop-in does

`packaging/zboxtui-tty6.conf`:

```ini
[Service]
# Drop the default agetty command and replace it with one that
# autologins root and uses /usr/local/bin/zboxtui as the user's
# "login shell". --noclear keeps the previous DCUI screen visible
# during a service restart; --keep-baud is the standard agetty knob.
ExecStart=
ExecStart=-/sbin/agetty --autologin root \
    --login-program /usr/local/bin/zboxtui \
    --noclear --keep-baud %I 38400 linux

# tty6 is dedicated to the DCUI; restart it eagerly when it exits.
Restart=always
RestartSec=1
```

### Security audit notes

Running a TUI as root on a permanent console is a security-relevant
choice. The following constraints are baked into the design and
deserve to be re-checked before production rollout:

- **No shell escape**: zBoxTUI never spawns a user-controlled shell.
  Every external command is invoked via `subprocess` with an explicit
  argv list — no `shell=True` anywhere. The Plugin contract does not
  expose any free-text "run command" entry; plugins ship with their
  own `subprocess.run([...])` calls audited at code-review time.
- **PAM verification gates root-only actions**: the F2 login dialog
  calls `su -c true root` so that simply being autologin-ed onto tty6
  is not enough to change passwords / edit network config / restart
  services. The dialog only flips `_authenticated = True` once PAM
  succeeds. (Tradeoff: if root has no password, PAM will succeed
  silently — set a strong root password or rebuild PAM with
  `pam_succeed_if user != root` rules in front of the DCUI.)
- **Sudo password caching**: when a plugin needs `sudo`, the cached
  password lives only in the process — it's not written to disk and
  is dropped when zBoxTUI exits. Restarting the systemd unit forces a
  fresh prompt.
- **Log file ownership**: the default log path is `zboxtui.log` in
  the working directory, which on a tty deployment is `/`. Override
  to `/var/log/zboxtui.log` (the systemd unit runs as root) and
  rotate via standard `logrotate` rules.
- **Console access ≠ network access**: the DCUI is only reachable
  from a physical or KVM console — anyone at the keyboard already
  owns the box. The threat model that matters is "operator
  fat-fingers a config" rather than "remote attacker exploits the
  TUI"; the F2 PAM gate is there to prevent the former, not the
  latter.

### Production checklist

- [ ] Root password set and matches what operators expect.
- [ ] `/etc/zboxtui/app.conf` deployed with `log_file =
  /var/log/zboxtui.log` and the right `catalog_url` for the
  package-curation source.
- [ ] `logrotate` configured for `/var/log/zboxtui.log`.
- [ ] `getty@tty6` running zboxtui and restarting on exit.
- [ ] tty1-tty5 still expose a regular login (don't kidnap every
  console — leave a recovery path).
- [ ] `journalctl -u getty@tty6` looks clean after a few restarts.

## Development

```bash
uv sync                          # install with dev deps
uv run ruff check src/ tests/
uv run mypy src/
uv run pytest                    # 175+ tests; ~50s wall-clock

# Single test
uv run pytest tests/test_settings_and_hostname.py -v

# Capture fresh README screenshots
uv run python scripts/capture_readme_screenshots.py
```

## License

See the parent `zPodFactory` project for licensing.

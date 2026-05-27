# Installing zBoxTUI on a zBox appliance

Production installs use **`/sbin/zbox-zboxtui-setup.sh`** from
[packer-zbox](../packer-zbox/files/zbox-zboxtui-setup.sh). This document covers
console layout, security, manual wheel installs, and verification.

## Overview

| VT | Console | Purpose |
|----|---------|---------|
| **tty1** | **kmscon** → zBoxTUI | Operator DCUI (default boot VT; F2 login, F12 reboot) |
| **tty2** | **kmscon** → login | Truecolor shell |
| **tty3–tty6** | `agetty` (stock) | Normal login — recovery, break-glass |

zBoxTUI needs **truecolor** (`COLORTERM=truecolor`). On zBox that is provided by
kmscon via the setup script’s systemd drop-in and console wrappers. Stock **agetty**
on a Linux VT does not advertise truecolor; themes will look wrong there.

## Requirements

- Debian-based zBox with **systemd**
- **`/sbin/zbox-zboxtui-setup.sh`** (provisioned from packer-zbox, or
  [`scripts/zbox-zboxtui-setup.sh`](scripts/zbox-zboxtui-setup.sh) from a dev checkout)
- **Python ≥ 3.11** (3.13 recommended) — installed into `/opt/zboxtui/venv` by `--enable`
- **root password** set — F2 login uses PAM; tty1 autostart alone does not authorize changes
- Network tools used by menu actions: `ip`, `ping`, `hostnamectl`, `apt-get` (must be on `PATH`; tty1 autostart sets `/usr/sbin` and `/sbin` — see `zbox-zboxtui-setup.sh` console wrappers)

## Console setup (`zbox-zboxtui-setup.sh`)

On zBox Packer images this runs automatically during build. On any Debian host:

```bash
sudo /sbin/zbox-zboxtui-setup.sh --enable
```

From a zBoxTUI checkout (same script):

```bash
sudo ./scripts/zbox-zboxtui-setup.sh --enable
```

`--enable` (unattended):

- Installs **kmscon** and Nerd Font + Catppuccin palette
- Clones [zBoxTUI](https://github.com/zPodFactory/zBoxTUI) @ `main`, runs `uv build`, installs the wheel into `/opt/zboxtui/venv`
- Copies **`packaging/app.conf.sample`** → `/etc/zboxtui/app.conf` (if missing)
- Copies **`packaging/zboxtui.logrotate`** → `/etc/logrotate.d/zboxtui`
- Writes kmscon/console scripts and systemd drop-ins **inline** (not from `packaging/`)
- Enables **tty1** (zBoxTUI) and **tty2** (login); removes `/tmp/zboxtui-build` when done

Optional: `--font`, `--palette`, `--font-size`.

Revert everything:

```bash
sudo /sbin/zbox-zboxtui-setup.sh --disable
```

See [packer-zbox/docs/ZCONSOLE-INTEGRATION.md](../packer-zbox/docs/ZCONSOLE-INTEGRATION.md).

## Manual wheel install (without the setup script)

Use this on lab VMs or when you only need the Python package, not kmscon wiring.

```bash
sudo apt install -y python3 python3-venv python3-pip
sudo install -d -m 0755 /opt/zboxtui
sudo python3 -m venv /opt/zboxtui/venv

cd /path/to/zBoxTUI
uv build
sudo /opt/zboxtui/venv/bin/pip install dist/zboxtui-*.whl
sudo ln -sf /opt/zboxtui/venv/bin/zboxtui /usr/local/bin/zboxtui

sudo install -d -m 0755 /etc/zboxtui /var/log
sudo install -m 0644 packaging/app.conf.sample /etc/zboxtui/app.conf
sudo install -m 0644 packaging/zboxtui.logrotate /etc/logrotate.d/zboxtui
sudo touch /var/log/zboxtui.log
sudo chmod 0644 /var/log/zboxtui.log

# Optional curated catalog
sudo install -m 0644 zbox-packages.json /etc/zboxtui/packages.json
# Set catalog_url = file:///etc/zboxtui/packages.json in app.conf
```

Do **not** `pip install` into Debian system site-packages on golden images
(`EXTERNALLY-MANAGED` and apt conflicts).

## Security model

### tty1 autologin is not full access

- tty1 starts zBoxTUI as **root** without a password; **F2 → Login** (PAM) is required for configuration.
- **Menu back** (`Esc` / `q`) returns to the dashboard; F2 login stays valid for **15 minutes** (same default as sudo’s timestamp). If sudo still has a cached timestamp after that, the session can extend without re-entering the root password.
- **F8** exits the application from the configuration menu only (after login).
- No arbitrary-shell menu entry; subprocesses use fixed `argv` lists.

### Dashboard quit keys disabled

Before login, **Q**, **Ctrl+Q**, and **Ctrl+C** do not quit. The console wrapper
restarts zBoxTUI on exit; tty1 stays locked if the binary is missing until you
re-run `--enable` from tty3–tty6 or SSH.

### Development

```bash
ZBOXTUI_ALLOW_QUIT=1 uv run zboxtui
```

Never set `ZBOXTUI_ALLOW_QUIT` in the tty1 kmscon environment.

### Recovery access

Use **tty3–tty6** or **tty2** (kmscon login) for a normal root shell.

## Manual test (SSH / local terminal)

```bash
export COLORTERM=truecolor TERM=xterm-256color
zboxtui
# or: ZBOXTUI_ALLOW_QUIT=1 zboxtui
```

## Packer / zBox template checklist

- [ ] `/sbin/zbox-zboxtui-setup.sh --enable` in provisioning
- [ ] `/opt/zboxtui/venv` + `/usr/local/bin/zboxtui`
- [ ] `/etc/zboxtui/app.conf` and `/etc/logrotate.d/zboxtui`
- [ ] Root password set
- [ ] **Ctrl+Alt+F1** → zBoxTUI; F2 login works; Esc from menu returns to dashboard
- [ ] `journalctl -u kmsconvt@tty1` clean after restart

## Troubleshooting

| Symptom | Likely cause |
|---------|----------------|
| Washed-out / wrong colors | Re-run `zbox-zboxtui-setup.sh --enable` |
| tty1 shows agetty/`/etc/issue` | Missing kmsconvt drop-in — re-run `--enable` |
| Immediate shell on tty1 | `--enable` not run or stale getty override |
| zBoxTUI exits to shell | Old build / missing console-loop |
| F2 login always succeeds | Empty root password |

## `packaging/` directory

Only two files — consumed by **`zbox-zboxtui-setup.sh --enable`** from the git clone:

| File | Installed to |
|------|----------------|
| `packaging/app.conf.sample` | `/etc/zboxtui/app.conf` |
| `packaging/zboxtui.logrotate` | `/etc/logrotate.d/zboxtui` |

Kmscon snippets, console wrappers, profile.d, and the systemd drop-in are
**generated inline** in
[packer-zbox/files/zbox-zboxtui-setup.sh](../packer-zbox/files/zbox-zboxtui-setup.sh)
(mirrored in [`scripts/zbox-zboxtui-setup.sh`](scripts/zbox-zboxtui-setup.sh)).

## Dashboard network display

On the home screen, each non-virtual interface shows `→ name: ip/cidr [STATIC]`,
`[DHCP]`, or `[UNMANAGED]` (VPN/tunnel interfaces such as **tailscale0** or **wt0**
that are not in `/etc/network/interfaces`). Routes and DNS appear in bulleted
sections below the interface list. See [README.md](README.md) screenshots
`15`–`17` for examples.

## Related docs

- [README.md](README.md) — development, architecture, plugins, screenshots
- [TRADEMARKS.md](TRADEMARKS.md)
- [packer-zbox/docs/ZCONSOLE-INTEGRATION.md](../packer-zbox/docs/ZCONSOLE-INTEGRATION.md) — console layout on OVA images

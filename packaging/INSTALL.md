# zBoxTUI — Production install (tty6 DCUI)

This document covers the exact steps to land zBoxTUI on a Debian box
as the operator interface on tty6 (Ctrl+Alt+F6).

## Files in this directory

| File                      | Install target                                            |
|---------------------------|-----------------------------------------------------------|
| `app.conf.sample`         | `/etc/zboxtui/app.conf`                                   |
| `zboxtui-tty6.conf`       | `/etc/systemd/system/getty@tty6.service.d/override.conf`  |
| `zboxtui.logrotate`       | `/etc/logrotate.d/zboxtui`                                |

## One-shot install

```bash
# 0. From a checkout of the repo, build the wheel
uv build

# 1. Install the binary system-wide
sudo pip install --break-system-packages dist/zboxtui-*.whl
# (pipx works too: `sudo pipx install --system-site-packages dist/zboxtui-*.whl`)
which zboxtui      # expect /usr/local/bin/zboxtui

# 2. Drop config, log dir, logrotate rule
sudo install -d -m 0755 /etc/zboxtui
sudo install -m 0644 packaging/app.conf.sample /etc/zboxtui/app.conf
sudo install -d -m 0750 -o root -g adm /var/log
sudo install -m 0644 packaging/zboxtui.logrotate /etc/logrotate.d/zboxtui

# 3. Wire tty6 to launch the DCUI
sudo install -d /etc/systemd/system/getty@tty6.service.d
sudo install -m 0644 packaging/zboxtui-tty6.conf \
    /etc/systemd/system/getty@tty6.service.d/override.conf
sudo systemctl daemon-reload
sudo systemctl restart getty@tty6.service
```

Switch to tty6 (Ctrl+Alt+F6 on the physical/VM console) — the DCUI
should be waiting.

## Verifying

```bash
# tty6 unit must report the DCUI command
systemctl status getty@tty6.service | grep ExecStart

# Logs from the DCUI itself (after one session)
tail -n 50 /var/log/zboxtui.log

# Quick sanity test of the binary outside the tty
sudo -u root zboxtui --generate-config | head -20
```

## Recovery

- **tty1-tty5 still run a regular login.** Even if the DCUI is
  broken, you can switch to tty1 and recover from a shell.
- **Disable the DCUI temporarily** without removing files:
  ```bash
  sudo systemctl revert getty@tty6.service
  sudo systemctl restart getty@tty6.service
  ```
- **Permanently uninstall**:
  ```bash
  sudo rm /etc/systemd/system/getty@tty6.service.d/override.conf
  sudo rm /etc/logrotate.d/zboxtui
  sudo rm -rf /etc/zboxtui
  sudo systemctl daemon-reload
  sudo systemctl restart getty@tty6.service
  sudo pip uninstall --break-system-packages zboxtui   # or pipx uninstall
  ```

## Security recap

See `README.md` (Security audit notes) for the full threat model.
Quick summary:

- DCUI runs as **root** because the operations it performs require
  it. Compensate with PAM auth at F2 — make sure root has a strong
  password.
- No shell escape: every external command uses argv lists, no
  `shell=True`. Plugin contract has no "run arbitrary command" hook.
- Console access ≠ network access: the DCUI is reachable only from
  the physical/KVM console. Anyone there already owns the box.
- Sudo passwords are cached in-process only and dropped on exit.

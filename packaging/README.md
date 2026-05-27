# `packaging/`

Files installed by [`zbox-zboxtui-setup.sh`](../scripts/zbox-zboxtui-setup.sh) when the
repo is cloned during `zbox-zboxtui-setup.sh --enable` (same paths on
[packer-zbox](https://github.com/zPodFactory/packer-zbox) images).

| File | Installed to |
|------|----------------|
| `app.conf.sample` | `/etc/zboxtui/app.conf` (only if missing) |
| `zboxtui.logrotate` | `/etc/logrotate.d/zboxtui` |

Kmscon configuration, console wrappers, profile.d, and the `kmsconvt@tty1` systemd
drop-in are generated **inline** in the setup script — not from this directory.

See [INSTALL.md](../INSTALL.md).

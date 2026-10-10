# Changelog

Notable changes to zBoxTUI, newest first. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html): `0.2.6` is the version in
`pyproject.toml` and the git tag `v0.2.6`.

Entries describe what changed for the person using the console: screens, menu entries, what a
value shows, configuration keys, the plugin API. The commit history has the reasoning.

**Cutting a release.** Changes land under `[Unreleased]` as they are made. Then
`python3 tools/release.py X.Y.Z --push` does the rest: `[Unreleased]` becomes `[X.Y.Z] — date`,
the version moves in `pyproject.toml` and `uv.lock`, the tests run, the commit is tagged `vX.Y.Z`
and pushed, and the tag publishes this file's section as the GitHub release note, with the source
link and install pointers above it (`.github/workflows/release.yml`, `tools/release_notes.py`).
The script refuses a dirty tree, an empty `[Unreleased]` (`--from-commits` fills it from the
commits), a version not above the last tag, a failing suite, and any string from the local
`.release-denylist`; `--check` runs the same rules, and CI runs it on every push. Preview a note
with `python3 tools/release_notes.py X.Y.Z`.

## [Unreleased]

### Added

- **The dashboard follows the system.** Besides the CPU and memory bars, it now re-reads the
  hostname, interfaces and addresses, routes, DNS and mounted filesystems on a timer (every
  10 seconds by default, `rescan_interval_seconds` under `[dashboard]`, also in Configure
  Settings). Only what changed is repainted: a new address or route updates the network block
  in place, storage bars move in place, and a mount appearing or vanishing rebuilds the panel.
  Before, Network and Storage were read once at start and again only when returning from the
  F2 menu, so a VLAN interface or a volume added after boot stayed invisible.

### Fixed

- **Interfaces configured under `/etc/network/interfaces.d/` are no longer tagged
  `[UNMANAGED]`.** The mode, DHCP and DNS readers opened only `/etc/network/interfaces` and
  ignored its `source` line, so a static VLAN interface whose stanza zbox-init drops into
  `interfaces.d` showed as unmanaged. The readers now follow `source` and `source-directory`
  the way ifupdown does, relative paths included.

## [0.2.7] — 2026-10-08

### Changed

- **Network interfaces are listed in natural order.** VLAN IDs and interface indexes compare as
  numbers, so `eth1.64` comes before `eth1.128` and `eth2` before `eth10`, instead of the
  character-by-character order that put `eth1.128` right after `eth1.10`. The gateway interface
  still comes first.
- **Releases follow the shared zPodFactory standard.** `tools/release.py` (cut, `--check`,
  `--draft`, `--from-commits`) and `tools/release_notes.py` are the same files as in every other
  repository, with a configuration block at the top: here the version lives in `pyproject.toml`
  and `uv.lock` (`__version__` now reads it from the installed package), and the test suite
  gates the cut.
  `tools/README.md` explains the release in a page. The tag is created by the cut, on the
  workstation, never by a workflow.

### Fixed

- **Filesystem usage no longer counts ext4's reserved blocks as used.** The dashboard's per-mount
  list derived "used" from the blocks available to unprivileged users, so the 5% root reservation
  showed up as consumption: `/` read 11% where `df` and `duf` read 5–6%, and an empty 1 TB volume
  read 5%. Usage now matches `duf` and `shutil.disk_usage`.

## [0.2.6] — 2026-05-27

Initial public release, work in progress.

### Added

- DCUI-style console for Debian built on Textual: dashboard with live CPU, memory, storage and
  network I/O, hostname, root password, network (static/DHCP, DNS), curated package sets from
  `zbox-packages.json`, system and zBox logs, system metrics, ping, DNS lookup and connectivity
  tests.
- Six colour themes, Catppuccin Mocha by default, selectable from the console or `--theme`.
- Configuration file search (`--config`, `$ZBOXTUI_CONFIG`, `~/.config/zboxtui/app.conf`,
  `/etc/zboxtui/app.conf`) and `--generate-config` to print the commented sample.
- Plugin API: a menu entry is one `.py` file dropped into `src/zboxtui/plugins/`.
- `packaging/` files for the appliance install (`app.conf.sample`, logrotate) and
  [INSTALL.md](INSTALL.md) for the manual wheel install; `packer-zbox` installs the console on
  tty1 through `/sbin/zbox-zboxtui-setup.sh`.

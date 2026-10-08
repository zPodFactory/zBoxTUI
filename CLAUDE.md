# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

zBoxTUI is a DCUI-style console for Debian built on Textual (Python 3.11+), installed on zBox
appliances by `packer-zbox`. README.md covers the screens, configuration and plugin API;
INSTALL.md covers the appliance install.

## Development

```bash
uv sync
uv run ruff check src/ tests/
uv run mypy src/
uv run pytest
```

## Releases

- Versions are SemVer: `pyproject.toml` `0.2.6` is tag `v0.2.6` is release `v0.2.6`. `uv.lock`
  carries the same version and `__version__` reads it from the installed package; the cut keeps
  them in step, never edit them apart.
- Every change gets a line under `[Unreleased]` in `CHANGELOG.md`: what changed for the person
  using the console, and why in a clause.
- A release is one command: `python3 tools/release.py X.Y.Z --push` (`--dry-run` first). The cut
  moves the heading, bumps the version, runs the tests, commits, tags `vX.Y.Z`, pushes; the tag
  then publishes the section as the GitHub release through `.github/workflows/release.yml`.
- `python3 tools/release.py --check` is what CI runs on every push: shipped version equals the
  newest section, every tag has a section, nothing local is tracked. Keep the forbidden-string
  list in `.release-denylist` (git-ignored) for the names that must never enter the history.
- Never tag by hand, never edit a release on GitHub: fix the changelog and re-run the workflow
  (`workflow_dispatch`, blank version republishes every tag).

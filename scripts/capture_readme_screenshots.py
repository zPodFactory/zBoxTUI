#!/usr/bin/env python3
"""Regenerate the SVG screenshots embedded in the README.

Run with ``uv run python scripts/capture_readme_screenshots.py`` from
the repo root. Output lands in ``docs/screenshots/``.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "screenshots"


def _stub_pam() -> None:
    """Make `verify_root_password` accept any input so we can reach the menu."""
    import zboxtui.core.widgets.dcui_dialog as dcui

    dcui.verify_root_password = lambda _pw: True


async def capture() -> None:
    from zboxtui.core.utils.config import init_config

    init_config(None)
    _stub_pam()
    from zboxtui.app import ZBoxTUI
    from zboxtui.core.menu_items.hostname import HostnameDialog
    from zboxtui.core.menu_items.settings import SettingsDialog

    OUT.mkdir(parents=True, exist_ok=True)

    for theme_name, suffix in (("catppuccin-mocha", "catppuccin"), ("vmware-esxi", "esxi")):
        app = ZBoxTUI()
        async with app.run_test(size=(120, 35)) as pilot:
            await pilot.pause()
            app.theme = theme_name
            await pilot.pause(0.1)
            app.save_screenshot(str(OUT / f"01_dashboard_{suffix}.svg"))

            # Login dialog
            await pilot.press("f2")
            await pilot.pause(0.2)
            app.save_screenshot(str(OUT / f"02_login_{suffix}.svg"))

            # Past login → menu
            await pilot.press("tab")
            for char in "root":
                await pilot.press(char)
            await pilot.press("enter")
            await pilot.pause(0.4)
            app.save_screenshot(str(OUT / f"03_menu_{suffix}.svg"))

            # Configure Hostname (top of menu now)
            app.push_screen(HostnameDialog())
            await pilot.pause(0.3)
            app.save_screenshot(str(OUT / f"04_hostname_{suffix}.svg"))
            app.pop_screen()
            await pilot.pause(0.1)

            # Configure Settings
            app.push_screen(SettingsDialog())
            await pilot.pause(0.2)
            app.save_screenshot(str(OUT / f"06_settings_{suffix}.svg"))

    # Plugin: Ping + DNS — load directly from disk since they're not importable as modules.
    import importlib.util

    def _load(name: str, path: Path) -> object:
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod

    ping = _load("ping_plugin", ROOT / "src/zboxtui/plugins/90_ping.py")
    dns = _load("dns_plugin", ROOT / "src/zboxtui/plugins/91_dns_lookup.py")

    for theme_name, suffix in (("catppuccin-mocha", "catppuccin"),):
        app = ZBoxTUI()
        async with app.run_test(size=(120, 35)) as pilot:
            await pilot.pause()
            app.theme = theme_name
            await pilot.pause(0.1)
            ping.show_dialog(app)  # type: ignore[attr-defined]
            await pilot.pause(0.2)
            app.save_screenshot(str(OUT / f"07_ping_{suffix}.svg"))
            app.pop_screen()
            await pilot.pause()
            dns.show_dialog(app)  # type: ignore[attr-defined]
            await pilot.pause(0.2)
            app.save_screenshot(str(OUT / f"08_dns_{suffix}.svg"))


if __name__ == "__main__":
    asyncio.run(capture())
    print("Screenshots saved to", OUT)

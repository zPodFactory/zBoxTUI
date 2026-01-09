#!/usr/bin/env python3
"""Test script to capture network test dialog screenshot."""

import asyncio

from src.zboxtui.app import ZBoxTUI
from src.zboxtui.widgets.dcui_dialog import NetworkTestDialog


async def main():
    """Run the app and capture network test dialog screenshot."""
    app = ZBoxTUI(debug_svg=True)

    async with app.run_test() as pilot:
        # Wait for dashboard to render
        await pilot.pause(0.5)

        # Push network test dialog directly
        app.push_screen(NetworkTestDialog())
        await pilot.pause(3)  # Wait for network tests to complete

        await pilot.pause(0.5)


if __name__ == "__main__":
    asyncio.run(main())

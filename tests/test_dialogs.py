#!/usr/bin/env python3
"""Test script to capture dialog screenshots."""

import asyncio
from textual.pilot import Pilot

from src.zboxtui.app import ZBoxTUI


async def main():
    """Run the app and capture screenshots of all dialogs."""
    app = ZBoxTUI(debug_svg=True)

    async with app.run_test() as pilot:
        # Wait for dashboard to render
        await pilot.pause(0.5)

        # Trigger login dialog (F2)
        await pilot.press("f2")
        await pilot.pause(0.5)

        # Close login dialog
        await pilot.press("escape")
        await pilot.pause(0.5)

        # Trigger shutdown dialog (F12)
        await pilot.press("f12")
        await pilot.pause(0.5)

        # Close shutdown dialog
        await pilot.press("escape")
        await pilot.pause(0.5)

        # Go to menu - login with credentials
        await pilot.press("f2")
        await pilot.pause(0.3)
        # Type password (username already has "root")
        await pilot.press("tab")  # Move to password field
        await pilot.pause(0.2)
        # Type any password
        for char in "password":
            await pilot.press(char)
            await pilot.pause(0.05)
        await pilot.pause(0.2)
        await pilot.press("enter")  # Submit login
        await pilot.pause(0.5)

        # Now in menu - navigate to test network (4th item)
        await pilot.press("down", "down", "down", "down")
        await pilot.pause(0.3)
        await pilot.press("enter")
        await pilot.pause(2)  # Wait for network tests to complete

        await pilot.pause(0.5)


if __name__ == "__main__":
    asyncio.run(main())

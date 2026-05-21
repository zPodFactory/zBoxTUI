"""Entry point for zBoxTUI."""

import argparse

from .app import ZBoxTUI


def main() -> None:
    """Run the zBoxTUI application."""
    parser = argparse.ArgumentParser(description="zBoxTUI - ESXi DCUI-style TUI")
    parser.add_argument(
        "--debug-svg",
        action="store_true",
        help="Enable debug mode: auto-capture SVG screenshots of screens/dialogs",
    )
    parser.add_argument(
        "--palette",
        choices=["auto", "catppuccin", "console"],
        default="auto",
        help="Color palette: 'auto' detects terminal capabilities (default), "
        "'catppuccin' forces the 24-bit Mocha palette, "
        "'console' forces the 16-color ANSI palette",
    )
    args = parser.parse_args()

    app = ZBoxTUI(debug_svg=args.debug_svg, palette=args.palette)
    app.run()


if __name__ == "__main__":
    main()

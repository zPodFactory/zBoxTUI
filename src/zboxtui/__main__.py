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
    args = parser.parse_args()

    app = ZBoxTUI(debug_svg=args.debug_svg)
    app.run()


if __name__ == "__main__":
    main()

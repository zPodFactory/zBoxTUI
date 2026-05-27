"""Entry point for zBoxTUI."""

from __future__ import annotations

import argparse


def main() -> None:
    """Run the zBoxTUI application."""
    parser = argparse.ArgumentParser(
        description="zBoxTUI — DCUI-style TUI for Debian (see TRADEMARKS.md)"
    )
    parser.add_argument(
        "--debug-svg",
        action="store_true",
        help="Enable debug mode: auto-capture SVG screenshots of screens/dialogs",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        metavar="PATH",
        help="Config file path (overrides search order; see config.py for "
        "$ZBOXTUI_CONFIG, ~/.config/zboxtui/app.conf, /etc/zboxtui/app.conf)",
    )
    parser.add_argument(
        "--generate-config",
        action="store_true",
        help="Print a sample configuration file to stdout and exit",
    )
    parser.add_argument(
        "--theme",
        type=str,
        default=None,
        metavar="NAME",
        help="Override the configured theme for this run. Built-in themes: "
        "catppuccin-mocha (default; https://catppuccin.com/palette/), "
        "vmware-esxi, nord, gruvbox, tokyo-night, atom-one-dark.",
    )
    args = parser.parse_args()

    # --generate-config: print and exit, before touching anything.
    if args.generate_config:
        from .core.utils.config import generate_sample_config

        print(generate_sample_config())
        return

    # Load config before logging and app startup so get_config() honors CLI/env.
    from .core.utils.config import init_config

    init_config(args.config)

    # Initialize logging once the config is known (truncates the log file).
    from .core.utils.logging import init_logging

    init_logging()

    from .app import ZBoxTUI

    app = ZBoxTUI(debug_svg=args.debug_svg, theme_override=args.theme)
    app.run()


if __name__ == "__main__":
    main()

"""zBoxTUI — DCUI-style TUI for Debian (ESXi / XCP-ng-inspired; see TRADEMARKS.md)."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("zboxtui")
except PackageNotFoundError:  # pragma: no cover - running from a bare checkout
    __version__ = "0.0.0"

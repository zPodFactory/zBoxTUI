"""Discovery and loading of menu plugins from src/zboxtui/plugins/."""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from .core.utils.logging import get_logger

if TYPE_CHECKING:
    from .app import ZBoxTUI

log = get_logger("plugin_loader")


@dataclass
class PluginMenuItem:
    """A menu entry contributed by a plugin module."""

    label: str
    description: str
    handler: Callable[[ZBoxTUI], None]
    module_name: str
    section: str  # e.g. "Network", "System", "Logs"; "" = no section header


def discover_plugins(plugins_dir: Path | None = None) -> list[PluginMenuItem]:
    """Load every plugin in ``plugins_dir``, sorted by filename (ASCII order).

    A plugin is a .py file exporting ``MENU_LABEL``, ``MENU_DESCRIPTION``,
    ``MENU_SECTION="Plugins"``, and ``show_dialog(app)``. Files starting with
    ``_`` are skipped. An optional ``MENU_ENABLED = False`` opts a plugin out.
    Built-in menu actions live in ``menu_items`` instead of the plugins folder.
    """
    if plugins_dir is None:
        plugins_dir = Path(__file__).parent / "plugins"

    if not plugins_dir.exists():
        log.warning("Plugins directory not found: %s", plugins_dir)
        return []

    plugin_files = sorted(
        f
        for f in plugins_dir.glob("*.py")
        if f.name != "__init__.py" and not f.name.startswith("_")
    )

    plugins: list[PluginMenuItem] = []
    for plugin_file in plugin_files:
        try:
            plugin = load_plugin(plugin_file)
        except Exception as exc:
            log.error("Failed to load plugin %s: %s", plugin_file.name, exc)
            continue
        if plugin is not None:
            plugins.append(plugin)
            log.info("Loaded plugin: %s -> %s", plugin_file.name, plugin.label)

    return plugins


def load_plugin(plugin_path: Path) -> PluginMenuItem | None:
    """Import a single plugin file and return its PluginMenuItem.

    Returns None if the file is disabled (``MENU_ENABLED = False``) or
    missing one of the required attributes.
    """
    module_name = f"zboxtui.plugins.{plugin_path.stem}"

    spec = importlib.util.spec_from_file_location(module_name, plugin_path)
    if spec is None or spec.loader is None:
        log.warning("Could not load spec for %s", plugin_path)
        return None

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    if getattr(module, "MENU_ENABLED", True) is False:
        log.debug("Plugin %s is disabled (MENU_ENABLED=False)", plugin_path.name)
        return None

    label = getattr(module, "MENU_LABEL", None)
    description = getattr(module, "MENU_DESCRIPTION", None)
    section = getattr(module, "MENU_SECTION", None)
    show_dialog = getattr(module, "show_dialog", None)

    if not isinstance(label, str):
        log.warning("Plugin %s missing or invalid MENU_LABEL", plugin_path.name)
        return None
    if not isinstance(description, str):
        log.warning("Plugin %s missing or invalid MENU_DESCRIPTION", plugin_path.name)
        return None
    if not callable(show_dialog):
        log.warning("Plugin %s missing callable show_dialog", plugin_path.name)
        return None
    if not isinstance(section, str) or section != "Plugins":
        log.debug(
            "Skipping %s (MENU_SECTION must be 'Plugins', got %r)",
            plugin_path.name,
            section,
        )
        return None

    return PluginMenuItem(
        label=label,
        description=description,
        handler=show_dialog,
        module_name=module_name,
        section=section,
    )

"""Plugin loader: scan plugins_ext/*/manifest.json and load enabled plugins."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.observability import get_logger
from app.plugins.architecture import PluginInfo, PluginManifest
from app.plugins.registry import plugin_registry

logger = get_logger("plugin_loader")


def _import_module_from_path(mod_name: str, file_path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(mod_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load spec for {file_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


def _collect_tools(module: Any) -> list[Any]:
    """Collect langchain tools exported via __all__ (auto-discovery)."""
    tools: list[Any] = []
    names = getattr(module, "__all__", None)
    if names is None:
        names = [n for n in dir(module) if not n.startswith("_")]
    for name in names:
        obj = getattr(module, name, None)
        # langchain tools expose a `.name` and are invocable
        if obj is not None and hasattr(obj, "name") and hasattr(obj, "invoke"):
            tools.append(obj)
    return tools


def discover_and_load(plugins_dir: Path | None = None, enabled: list[str] | None = None) -> list[PluginInfo]:
    """Scan the plugins directory; register every plugin, load only enabled ones.

    Safe default (QwenPaw-aligned): a plugin present on disk but NOT listed in
    `enabled` is registered as disabled and its tools are NOT loaded/registered.
    """
    base = plugins_dir or settings.plugins_dir
    enabled_names = enabled if enabled is not None else settings.enabled_plugins_list
    plugin_registry.clear()

    if not base.exists():
        return []

    results: list[PluginInfo] = []
    for manifest_file in sorted(base.glob("*/manifest.json")):
        plugin_dir = manifest_file.parent
        try:
            manifest = PluginManifest.from_dict(json.loads(manifest_file.read_text(encoding="utf-8")))
        except Exception as exc:  # noqa: BLE001
            logger.warning("plugin_manifest_error", path=str(manifest_file), error=str(exc))
            continue

        is_enabled = manifest.name in enabled_names
        info = PluginInfo(manifest=manifest, path=str(plugin_dir), enabled=is_enabled)

        if not is_enabled:
            plugin_registry.add(info)
            results.append(info)
            logger.info("plugin_skipped_disabled", name=manifest.name)
            continue

        entry_path = plugin_dir / manifest.entry
        try:
            module = _import_module_from_path(f"boetclaw_plugin_{manifest.name}", entry_path)
            tools = _collect_tools(module)
            info.loaded = True
            plugin_registry.add(info, tools)
            logger.info("plugin_loaded", name=manifest.name, tools=len(tools))
        except Exception as exc:  # noqa: BLE001
            info.error = str(exc)
            plugin_registry.add(info)
            logger.warning("plugin_load_failed", name=manifest.name, error=str(exc))
        results.append(info)

    return results


def reload_plugins() -> list[PluginInfo]:
    return discover_and_load()

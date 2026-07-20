"""Plugin registry: holds discovered plugins and their enabled tools."""

from __future__ import annotations

from typing import Any

from app.core.observability import get_logger
from app.plugins.architecture import PluginInfo

logger = get_logger("plugin_registry")


class PluginRegistry:
    def __init__(self) -> None:
        self._plugins: dict[str, PluginInfo] = {}
        self._tools: dict[str, Any] = {}  # tool_name -> tool object (enabled only)

    def clear(self) -> None:
        self._plugins.clear()
        self._tools.clear()

    def add(self, info: PluginInfo, tools: list[Any] | None = None) -> None:
        self._plugins[info.manifest.name] = info
        if info.enabled and info.loaded and tools:
            for t in tools:
                name = getattr(t, "name", None)
                if name:
                    self._tools[name] = t
            info.tools = [getattr(t, "name", "") for t in tools]

    def list_plugins(self) -> list[PluginInfo]:
        return list(self._plugins.values())

    def get(self, name: str) -> PluginInfo | None:
        return self._plugins.get(name)

    def enabled_tools(self) -> list[Any]:
        """Tools contributed by enabled+loaded plugins (safe default: empty)."""
        return list(self._tools.values())


plugin_registry = PluginRegistry()

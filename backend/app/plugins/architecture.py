"""Plugin architecture: types and manifest schema."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PluginType(str, Enum):
    TOOL = "tool"
    PROVIDER = "provider"
    HOOK = "hook"
    COMMAND = "command"
    FRONTEND = "frontend"
    GENERAL = "general"


@dataclass
class PluginManifest:
    name: str
    version: str = "0.1.0"
    plugin_type: PluginType = PluginType.GENERAL
    description: str = ""
    entry: str = "plugin.py"
    author: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PluginManifest":
        raw_type = data.get("plugin_type", data.get("type", "general"))
        try:
            ptype = PluginType(raw_type)
        except ValueError:
            ptype = PluginType.GENERAL
        return cls(
            name=data["name"],
            version=data.get("version", "0.1.0"),
            plugin_type=ptype,
            description=data.get("description", ""),
            entry=data.get("entry", "plugin.py"),
            author=data.get("author", ""),
            metadata=data.get("metadata", {}),
        )


@dataclass
class PluginInfo:
    manifest: PluginManifest
    path: str
    enabled: bool
    loaded: bool = False
    tools: list[str] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.manifest.name,
            "version": self.manifest.version,
            "type": self.manifest.plugin_type.value,
            "description": self.manifest.description,
            "path": self.path,
            "enabled": self.enabled,
            "loaded": self.loaded,
            "tools": self.tools,
            "error": self.error,
        }

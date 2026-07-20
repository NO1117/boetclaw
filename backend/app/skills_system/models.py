"""Skill system data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class SkillConflictError(Exception):
    """Raised when a skill name conflicts during install."""


@dataclass
class SkillInfo:
    name: str
    description: str
    path: str
    source: str = "pool"  # pool | workspace | builtin
    enabled: bool = True
    languages: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "path": self.path,
            "source": self.source,
            "enabled": self.enabled,
            "languages": self.languages,
            "metadata": self.metadata,
        }

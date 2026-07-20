"""Workspace: an isolated container for a single agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class Workspace:
    agent_id: str
    root: Path
    config: dict[str, Any] = field(default_factory=dict)
    agent: Any = None
    checkpointer: Any = field(default=None, repr=False)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_access: float = 0.0

    def skills_dir(self) -> Path:
        return self.root / "skills"

    def files_dir(self) -> Path:
        return self.root / "files"

    def to_dict(self) -> dict[str, Any]:
        skills_count = 0
        sd = self.skills_dir()
        if sd.exists():
            skills_count = len([d for d in sd.iterdir() if d.is_dir()])
        return {
            "agent_id": self.agent_id,
            "root": str(self.root),
            "created_at": self.created_at,
            "loaded": self.agent is not None,
            "skills_count": skills_count,
            "config": self.config,
        }

"""Skill resolution: compute effective skills for a workspace + channel."""

from __future__ import annotations

from pathlib import Path

from app.core.config import settings
from app.core.observability import EventType, emit_event
from app.skills_system.store import get_workspace_skills_dir


def resolve_effective_skills(workspace_dir: str | Path | None = None, channel: str = "console") -> list[str]:
    """Return skill directory paths to feed create_deep_agent(skills=...).

    Priority:
    1. If a workspace skills dir exists and has skills -> use it.
    2. Otherwise fall back to the global pool (backend/skills).
    """
    dirs: list[str] = []

    ws_skills: Path | None = None
    if workspace_dir is not None:
        ws_skills = Path(workspace_dir) / "skills"

    if ws_skills and ws_skills.exists() and any(ws_skills.iterdir()):
        dirs.append(str(ws_skills))
    elif settings.skills_dir.exists():
        dirs.append(str(settings.skills_dir))

    emit_event(EventType.SKILL_LOADED, {"action": "resolve", "channel": channel, "dirs": dirs})
    return dirs


def ensure_workspace_skills(agent_id: str) -> Path:
    d = get_workspace_skills_dir(agent_id)
    d.mkdir(parents=True, exist_ok=True)
    return d

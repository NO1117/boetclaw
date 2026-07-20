"""Workspace skill service: per-agent skill copies and enable/disable state."""

from __future__ import annotations

import json
import shutil

from app.core.observability import EventType, emit_event, get_logger
from app.skills_system.models import SkillInfo
from app.skills_system.store import (
    get_skill_pool_dir,
    get_workspace_skills_dir,
    list_skill_dirs,
    read_skill_manifest,
    safe_skill_dir,
)

logger = get_logger("skill_workspace")


class SkillService:
    """Manages the workspace-level (per-agent) skill copies."""

    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id
        self.dir = get_workspace_skills_dir(agent_id)
        self._state_file = self.dir.parent / "skills_state.json"

    def _load_state(self) -> dict[str, bool]:
        if self._state_file.exists():
            try:
                return json.loads(self._state_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return {}
        return {}

    def _save_state(self, state: dict[str, bool]) -> None:
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        self._state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_skills(self) -> list[SkillInfo]:
        state = self._load_state()
        skills: list[SkillInfo] = []
        for d in list_skill_dirs(self.dir):
            info = read_skill_manifest(d, source="workspace")
            if info:
                info.enabled = state.get(info.name, True)
                skills.append(info)
        return skills

    def add_from_pool(self, name: str) -> SkillInfo:
        pool_dir = safe_skill_dir(get_skill_pool_dir(), name)
        if not pool_dir.exists():
            raise ValueError(f"技能池中不存在: {name}")
        self.dir.mkdir(parents=True, exist_ok=True)
        target = safe_skill_dir(self.dir, name)
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(pool_dir, target)
        info = read_skill_manifest(target, source="workspace")
        assert info is not None
        emit_event(EventType.SKILL_LOADED, {"action": "add_workspace", "agent": self.agent_id, "name": name})
        return info

    def set_enabled(self, name: str, enabled: bool) -> None:
        state = self._load_state()
        state[name] = enabled
        self._save_state(state)

    def effective_dirs(self) -> list[str]:
        """Directories of enabled workspace skills (for create_deep_agent skills=)."""
        return [s.path for s in self.list_skills() if s.enabled]


def get_skill_service(agent_id: str) -> SkillService:
    return SkillService(agent_id)

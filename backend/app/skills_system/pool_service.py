"""Skill pool service: manage the shared global skill repository."""

from __future__ import annotations

import shutil
from pathlib import Path

from app.core.observability import EventType, emit_event, get_logger
from app.skills_system.models import SkillConflictError, SkillInfo
from app.skills_system.scanner import skill_scanner
from app.skills_system.store import (
    get_skill_pool_dir,
    list_skill_dirs,
    read_skill_manifest,
    safe_skill_dir,
)

logger = get_logger("skill_pool")


class SkillPoolService:
    """CRUD over the global skill pool (backend/skills)."""

    def list_skills(self) -> list[SkillInfo]:
        pool = get_skill_pool_dir()
        skills: list[SkillInfo] = []
        for d in list_skill_dirs(pool):
            info = read_skill_manifest(d, source="pool")
            if info:
                skills.append(info)
        return skills

    def get(self, name: str) -> SkillInfo | None:
        for s in self.list_skills():
            if s.name == name:
                return s
        return None

    def install(self, name: str, source_dir: str, *, scan: bool = True, overwrite: bool = False) -> SkillInfo:
        pool = get_skill_pool_dir()
        pool.mkdir(parents=True, exist_ok=True)
        target = safe_skill_dir(pool, name)

        if target.exists() and not overwrite:
            raise SkillConflictError(f"技能已存在: {name}")

        src = Path(source_dir)
        if not (src / "SKILL.md").exists():
            raise ValueError("源目录缺少 SKILL.md")

        if scan:
            findings = skill_scanner.scan(src)
            if findings:
                raise ValueError(f"技能安全扫描未通过，发现 {len(findings)} 处风险: {findings[0].category}")

        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(src, target)
        emit_event(EventType.SKILL_LOADED, {"action": "install", "name": name})
        info = read_skill_manifest(target, source="pool")
        assert info is not None
        return info

    def remove(self, name: str) -> bool:
        pool = get_skill_pool_dir()
        target = safe_skill_dir(pool, name)
        if target.exists():
            shutil.rmtree(target)
            emit_event(EventType.SKILL_LOADED, {"action": "remove", "name": name})
            return True
        return False


skill_pool_service = SkillPoolService()

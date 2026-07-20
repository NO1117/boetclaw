"""Skill storage: directory resolution and SKILL.md manifest parsing."""

from __future__ import annotations

import re
from pathlib import Path

from app.core.config import settings
from app.skills_system.models import SkillInfo

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def get_skill_pool_dir() -> Path:
    """Global shared skill pool (backend/skills)."""
    return settings.skills_dir


def get_workspace_skills_dir(agent_id: str) -> Path:
    """Per-agent workspace skills directory."""
    return settings.agents_root / agent_id / "skills"


def safe_skill_dir(base: Path, name: str) -> Path:
    """Resolve a skill dir under base, preventing path traversal."""
    candidate = (base / name).resolve()
    base_resolved = base.resolve()
    if base_resolved not in candidate.parents and candidate != base_resolved:
        raise ValueError(f"unsafe skill path: {name}")
    return candidate


def parse_frontmatter(text: str) -> dict[str, str]:
    """Parse a minimal YAML-ish frontmatter block (key: value lines)."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}
    result: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip()
    return result


def read_skill_manifest(skill_dir: Path, source: str = "pool") -> SkillInfo | None:
    """Read a skill's SKILL.md and build SkillInfo."""
    manifest = skill_dir / "SKILL.md"
    if not manifest.exists():
        return None
    text = manifest.read_text(encoding="utf-8")
    fm = parse_frontmatter(text)
    name = fm.get("name", skill_dir.name)
    description = fm.get("description", "")
    languages = [x.strip() for x in fm.get("languages", "").split(",") if x.strip()]
    return SkillInfo(
        name=name,
        description=description,
        path=str(skill_dir),
        source=source,
        languages=languages,
        metadata={k: v for k, v in fm.items() if k not in ("name", "description", "languages")},
    )


def list_skill_dirs(base: Path) -> list[Path]:
    if not base.exists():
        return []
    return [d for d in base.iterdir() if d.is_dir() and (d / "SKILL.md").exists()]

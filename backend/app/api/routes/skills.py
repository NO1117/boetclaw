"""Skill management routes."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.skills_system.pool_service import skill_pool_service
from app.skills_system.scanner import SCAN_EXTS, skill_scanner
from app.skills_system.store import get_skill_pool_dir, get_workspace_skills_dir, read_skill_manifest, safe_skill_dir
from app.skills_system.workspace_service import get_skill_service

router = APIRouter(prefix="/skills", tags=["Skills"])


class InstallRequest(BaseModel):
    name: str
    source_dir: str
    overwrite: bool = False


class EnableRequest(BaseModel):
    enabled: bool = True


class ScanRequest(BaseModel):
    path: str


class ReloadSkillsRequest(BaseModel):
    agent_id: str | None = None


class SkillFileUpdate(BaseModel):
    path: str
    content: str


TEXT_EXTS = SCAN_EXTS | {""}


def _skill_dir(scope: str, name: str, agent_id: str = "default") -> Path:
    if scope == "pool":
        base = get_skill_pool_dir()
    elif scope == "workspace":
        base = get_workspace_skills_dir(agent_id)
    else:
        raise HTTPException(status_code=400, detail="scope must be pool or workspace")
    path = safe_skill_dir(base, name)
    if not path.exists():
        raise HTTPException(status_code=404, detail="skill not found")
    return path


def _safe_file(skill_dir: Path, rel_path: str) -> Path:
    target = (skill_dir / rel_path).resolve()
    root = skill_dir.resolve()
    if root not in target.parents and target != root:
        raise HTTPException(status_code=400, detail="unsafe file path")
    if target.suffix.lower() not in TEXT_EXTS:
        raise HTTPException(status_code=400, detail="unsupported file type")
    return target


def _list_files(skill_dir: Path) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for path in skill_dir.rglob("*"):
        if path.is_file() and path.suffix.lower() in TEXT_EXTS:
            files.append(
                {
                    "path": str(path.relative_to(skill_dir)).replace("\\", "/"),
                    "size": path.stat().st_size,
                    "is_manifest": path.name == "SKILL.md",
                }
            )
    return sorted(files, key=lambda f: (not f["is_manifest"], f["path"]))


@router.get("")
async def list_skills(agent_id: str = "default"):
    return {
        "pool": [s.to_dict() for s in skill_pool_service.list_skills()],
        "workspace": [s.to_dict() for s in get_skill_service(agent_id).list_skills()],
    }


@router.post("/install")
async def install_skill(body: InstallRequest):
    try:
        info = skill_pool_service.install(body.name, body.source_dir, overwrite=body.overwrite)
        return info.to_dict()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{scope}/{name}")
async def get_skill_detail(scope: str, name: str, agent_id: str = "default"):
    skill_dir = _skill_dir(scope, name, agent_id)
    info = read_skill_manifest(skill_dir, source=scope)
    if info is None:
        raise HTTPException(status_code=404, detail="skill manifest not found")
    if scope == "workspace":
        state = {s.name: s.enabled for s in get_skill_service(agent_id).list_skills()}
        info.enabled = state.get(info.name, True)
    findings = skill_scanner.scan(skill_dir)
    return {
        "info": info.to_dict(),
        "files": _list_files(skill_dir),
        "scan": {"safe": len(findings) == 0, "findings": [f.to_dict() for f in findings]},
    }


@router.get("/{scope}/{name}/file")
async def read_skill_file(scope: str, name: str, path: str = "SKILL.md", agent_id: str = "default"):
    skill_dir = _skill_dir(scope, name, agent_id)
    target = _safe_file(skill_dir, path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    return {"path": path, "content": target.read_text(encoding="utf-8", errors="ignore")}


@router.put("/{scope}/{name}/file")
async def update_skill_file(scope: str, name: str, body: SkillFileUpdate, agent_id: str = "default"):
    skill_dir = _skill_dir(scope, name, agent_id)
    target = _safe_file(skill_dir, body.path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body.content, encoding="utf-8")
    info = read_skill_manifest(skill_dir, source=scope)
    if info is None:
        raise HTTPException(status_code=400, detail="skill manifest missing after update")
    return {"path": body.path, "info": info.to_dict()}


@router.delete("/{scope}/{name}")
async def delete_skill(scope: str, name: str, agent_id: str = "default"):
    if scope == "pool":
        ok = skill_pool_service.remove(name)
    elif scope == "workspace":
        target = _skill_dir(scope, name, agent_id)
        shutil.rmtree(target)
        ok = True
    else:
        raise HTTPException(status_code=400, detail="scope must be pool or workspace")
    if not ok:
        raise HTTPException(status_code=404, detail="skill not found")
    return {"deleted": name, "scope": scope}


@router.get("/{scope}/{name}/scan-report")
async def get_scan_report(scope: str, name: str, agent_id: str = "default"):
    skill_dir = _skill_dir(scope, name, agent_id)
    findings = skill_scanner.scan(skill_dir)
    return {"safe": len(findings) == 0, "findings": [f.to_dict() for f in findings]}


@router.post("/{name}/enable")
async def enable_skill(name: str, body: EnableRequest, agent_id: str = "default"):
    get_skill_service(agent_id).set_enabled(name, body.enabled)
    return {"name": name, "enabled": body.enabled}


@router.post("/{name}/add-to-workspace")
async def add_to_workspace(name: str, agent_id: str = "default"):
    try:
        return get_skill_service(agent_id).add_from_pool(name).to_dict()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/scan")
async def scan_skill(body: ScanRequest):
    findings = skill_scanner.scan(body.path)
    return {"safe": len(findings) == 0, "findings": [f.to_dict() for f in findings]}


@router.post("/reload")
async def reload_skills(body: ReloadSkillsRequest | None = None):
    from app.agents.multi_agent_manager import multi_agent_manager

    if body and body.agent_id:
        result = await multi_agent_manager.reload_agent(body.agent_id)
        return {"reloaded": 1 if result["reloaded"] else 0, "agents": [result]}
    results = await multi_agent_manager.reload_loaded_agents()
    return {"reloaded": sum(1 for item in results if item["reloaded"]), "agents": results}

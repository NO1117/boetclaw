"""Plugin & command management routes."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.commands.registry import command_registry
from app.core.config import settings
from app.core.env_file import update_env_file
from app.plugins.loader import reload_plugins
from app.plugins.architecture import PluginManifest
from app.plugins.registry import plugin_registry
from app.skills_system.scanner import skill_scanner

router = APIRouter(prefix="/plugins", tags=["Plugins"])
PLUGIN_ENV_PATH = Path(__file__).resolve().parents[3] / ".env"


class PluginInstallRequest(BaseModel):
    name: str
    source_dir: str
    overwrite: bool = False


class PluginEnableRequest(BaseModel):
    enabled: bool


class PluginScanRequest(BaseModel):
    path: str


def _safe_plugin_dir(name: str) -> Path:
    if not name or name in {".", ".."} or "/" in name or "\\" in name:
        raise HTTPException(status_code=400, detail="unsafe plugin path")
    base = settings.plugins_dir.resolve()
    candidate = (base / name).resolve()
    # Must be a strict child of plugins_dir (blocks ".", "..", and traversal).
    if base not in candidate.parents:
        raise HTTPException(status_code=400, detail="unsafe plugin path")
    return candidate


def _scan_payload(path: Path | str) -> dict:
    findings = skill_scanner.scan(path)
    return {"safe": len(findings) == 0, "findings": [f.to_dict() for f in findings]}


def _reject_if_unsafe(path: Path, *, label: str = "plugin") -> None:
    report = _scan_payload(path)
    if not report["safe"]:
        raise HTTPException(
            status_code=400,
            detail={
                "message": f"{label} security scan failed",
                "safe": False,
                "findings": report["findings"],
            },
        )


def _set_enabled_plugin(name: str, enabled: bool) -> list[str]:
    names = settings.enabled_plugins_list
    if enabled and name not in names:
        names.append(name)
    if not enabled:
        names = [p for p in names if p != name]
    settings.enabled_plugins = ",".join(names)
    update_env_file({"ENABLED_PLUGINS": settings.enabled_plugins}, PLUGIN_ENV_PATH)
    return names


@router.get("")
async def list_plugins():
    return {"plugins": [p.to_dict() for p in plugin_registry.list_plugins()]}


@router.post("/reload")
async def reload():
    infos = reload_plugins()
    return {"reloaded": len(infos), "plugins": [p.to_dict() for p in infos]}


@router.post("/scan")
async def scan_plugin(body: PluginScanRequest):
    return _scan_payload(body.path)


@router.post("/install")
async def install_plugin(body: PluginInstallRequest):
    src = Path(body.source_dir)
    manifest_file = src / "manifest.json"
    if not manifest_file.exists():
        raise HTTPException(status_code=400, detail="source_dir must contain manifest.json")
    try:
        manifest = PluginManifest.from_dict(json.loads(manifest_file.read_text(encoding="utf-8")))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"invalid manifest: {exc}") from exc
    if manifest.name != body.name:
        raise HTTPException(status_code=400, detail="manifest name does not match request name")

    # Scan source before copy; refuse unsafe plugins (do not auto-enable).
    _reject_if_unsafe(src, label="plugin")

    settings.plugins_dir.mkdir(parents=True, exist_ok=True)
    target = _safe_plugin_dir(body.name)
    if target.exists() and not body.overwrite:
        raise HTTPException(status_code=409, detail="plugin already exists")
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(src, target)

    # Belt-and-suspenders: scan installed copy before any enable path.
    try:
        _reject_if_unsafe(target, label="plugin")
    except HTTPException:
        shutil.rmtree(target, ignore_errors=True)
        raise

    infos = reload_plugins()
    info = plugin_registry.get(body.name) or next((p for p in infos if p.manifest.name == body.name), None)
    # Install never adds to ENABLED_PLUGINS; remains disabled until explicit enable.
    return info.to_dict() if info else {"installed": body.name, "enabled": False}


@router.get("/{name}/scan-report")
async def get_plugin_scan_report(name: str):
    target = _safe_plugin_dir(name)
    if not target.exists():
        raise HTTPException(status_code=404, detail="plugin not found")
    return _scan_payload(target)


@router.get("/{name}")
async def get_plugin(name: str):
    info = plugin_registry.get(name)
    if info is None:
        raise HTTPException(status_code=404, detail="plugin not found")
    manifest_path = Path(info.path) / "manifest.json"
    manifest = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    report = _scan_payload(info.path)
    return {**info.to_dict(), "manifest": manifest, "scan": report}


@router.put("/{name}/enabled")
async def set_plugin_enabled(name: str, body: PluginEnableRequest):
    target = _safe_plugin_dir(name)
    if not target.exists():
        raise HTTPException(status_code=404, detail="plugin not found")
    _set_enabled_plugin(name, body.enabled)
    reload_plugins()
    info = plugin_registry.get(name)
    if info is None:
        raise HTTPException(status_code=404, detail="plugin not found")
    return info.to_dict()


@router.delete("/{name}")
async def delete_plugin(name: str):
    target = _safe_plugin_dir(name)
    if not target.exists():
        raise HTTPException(status_code=404, detail="plugin not found")
    shutil.rmtree(target)
    _set_enabled_plugin(name, False)
    reload_plugins()
    return {"deleted": name}


commands_router = APIRouter(prefix="/commands", tags=["Commands"])


@commands_router.get("")
async def list_commands():
    return {"commands": command_registry.list_commands()}

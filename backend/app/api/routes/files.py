"""File serving for generated charts and code."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.core.config import settings

router = APIRouter(prefix="/files", tags=["Files"])


def _safe_file(base: Path, filename: str) -> Path:
    target = (base / filename).resolve()
    root = base.resolve()
    if root not in target.parents and target != root:
        raise HTTPException(status_code=400, detail="unsafe file path")
    return target


def _read_meta(kind: str, filename: str) -> dict[str, Any]:
    meta_path = settings.workspace_dir / "artifacts" / f"{kind}_{filename}.json"
    if not meta_path.exists():
        return {}
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _artifact_path(kind: str, filename: str) -> Path:
    if kind == "chart":
        return _safe_file(settings.workspace_dir / "charts", filename)
    if kind == "code":
        return _safe_file(settings.workspace_dir / "code", filename)
    raise HTTPException(status_code=400, detail="kind must be chart or code")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_row(kind: str, path: Path) -> dict[str, Any]:
    meta = _read_meta(kind, path.name)
    stat = path.stat()
    row = {
        "id": f"{kind}:{path.name}",
        "kind": kind,
        "filename": path.name,
        "size": stat.st_size,
        "created_at": meta.get("created_at", ""),
        "task_id": meta.get("task_id", ""),
        "trace_id": meta.get("trace_id", ""),
        "agent_id": meta.get("agent_id", ""),
        "well_id": meta.get("well_id", ""),
        "sha256": _sha256_file(path),
        "preview": "",
        "url": f"/api/v1/files/{path.name}" if kind == "chart" else f"/api/v1/files/code/{path.name}",
        "download_url": f"/api/v1/files/artifacts/{kind}/{path.name}/download",
    }
    if kind == "code":
        row["preview"] = path.read_text(encoding="utf-8", errors="ignore")[:2000]
    return row


@router.get("/artifacts")
async def list_artifacts(kind: str = "", well_id: str = "", agent_id: str = ""):
    rows: list[dict[str, Any]] = []
    charts_dir = settings.workspace_dir / "charts"
    code_dir = settings.workspace_dir / "code"
    if kind in ("", "chart") and charts_dir.exists():
        rows.extend(_artifact_row("chart", path) for path in charts_dir.glob("*.png") if path.is_file())
    if kind in ("", "code") and code_dir.exists():
        rows.extend(_artifact_row("code", path) for path in code_dir.iterdir() if path.is_file())
    if well_id:
        rows = [row for row in rows if row.get("well_id") == well_id]
    if agent_id:
        rows = [row for row in rows if row.get("agent_id") == agent_id]
    rows.sort(key=lambda row: row.get("created_at") or row.get("filename", ""), reverse=True)
    return {"artifacts": rows}


@router.get("/artifacts/{kind}/{filename}/download")
async def download_artifact(kind: str, filename: str):
    path = _artifact_path(kind, filename)
    media_type = "image/png" if kind == "chart" else "text/plain"
    if not path.exists():
        raise HTTPException(status_code=404, detail="artifact not found")
    return FileResponse(path, media_type=media_type, filename=filename)


@router.delete("/artifacts/{kind}/{filename}")
async def delete_artifact(kind: str, filename: str):
    path = _artifact_path(kind, filename)
    if not path.exists():
        raise HTTPException(status_code=404, detail="artifact not found")
    path.unlink()
    meta_path = settings.workspace_dir / "artifacts" / f"{kind}_{filename}.json"
    meta_path.unlink(missing_ok=True)
    return {"deleted": filename, "kind": kind}


@router.get("/{filename}")
async def get_chart(filename: str):
    filepath = _safe_file(settings.workspace_dir / "charts", filename)
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(filepath, media_type="image/png")


@router.get("/code/{filename}")
async def get_code(filename: str):
    filepath = _safe_file(settings.workspace_dir / "code", filename)
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(filepath, media_type="text/plain")

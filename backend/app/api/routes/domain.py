"""Drilling domain object routes."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.core.config import settings
from app.domain.models import DailyReport, DrillingParam, LasFile, Well, WellboreSection
from app.domain.las_importer import import_las_file
from app.domain.store import domain_store

router = APIRouter(prefix="/domain", tags=["Domain"])


class WellIn(BaseModel):
    name: str
    field: str = ""
    operator: str = ""
    location: str = ""
    status: str = "planned"
    metadata: dict[str, Any] = Field(default_factory=dict)


class SectionIn(BaseModel):
    well_id: str
    name: str
    top_depth: float = 0
    bottom_depth: float = 0
    hole_size: str = ""
    start_date: str = ""
    end_date: str = ""


class DailyReportIn(BaseModel):
    well_id: str
    report_date: str
    depth_start: float = 0
    depth_end: float = 0
    summary: str = ""
    issues: str = ""


class DrillingParamIn(BaseModel):
    well_id: str
    measured_depth: float
    timestamp: str = ""
    wob: float | None = None
    rpm: float | None = None
    rop: float | None = None
    torque: float | None = None
    pump_pressure: float | None = None
    flow_rate: float | None = None
    source: str = "manual"


class LasFileIn(BaseModel):
    well_id: str
    filename: str
    path: str = ""
    status: str = "registered"
    curves: list[str] = Field(default_factory=list)
    depth_min: float | None = None
    depth_max: float | None = None
    imported_at: str = ""
    curve_data_path: str = ""
    quality: dict[str, Any] = Field(default_factory=dict)


class LasImportIn(BaseModel):
    well_id: str
    path: str
    filename: str = ""


def _require_well(well_id: str) -> None:
    if domain_store.get("wells", well_id) is None:
        raise HTTPException(status_code=404, detail={"code": "well_not_found", "message": "well not found"})


def _get_or_404(collection: str, item_id: str) -> dict[str, Any]:
    item = domain_store.get(collection, item_id)
    if item is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "domain_item_not_found", "message": f"{collection} item not found"},
        )
    return item


def _safe_upload_name(filename: str) -> str:
    name = Path(filename or "upload.las").name
    return name or "upload.las"


def _validate_las_upload(name: str, content: bytes) -> None:
    if Path(name).suffix.lower() != ".las":
        raise HTTPException(status_code=400, detail={"code": "invalid_las_extension", "message": "LAS upload must use .las extension"})
    if len(content) > settings.las_upload_max_bytes:
        raise HTTPException(status_code=413, detail={"code": "las_upload_too_large", "message": "LAS upload exceeds size limit"})
    text = content.decode("utf-8", errors="ignore").upper()
    if "~A" not in text or ("~C" not in text and "~CURVE" not in text):
        raise HTTPException(status_code=400, detail={"code": "invalid_las_content", "message": "LAS upload must include curve and data sections"})


def _create_related(collection: str, payload: dict[str, Any]) -> dict[str, Any]:
    item = domain_store.create_related(collection, payload)
    if item is None:
        _require_well(str(payload.get("well_id", "")))
    return item


def _update_related(collection: str, item_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    status, item = domain_store.update_related(collection, item_id, payload)
    if status == "missing_item":
        return _get_or_404(collection, item_id)
    if status == "missing_well":
        _require_well(str(payload.get("well_id", "")))
    assert item is not None
    return item


def _artifact_count(well_id: str) -> int:
    meta_dir = settings.workspace_dir / "artifacts"
    count = 0
    if not meta_dir.exists():
        return count
    for path in meta_dir.glob("*.json"):
        try:
            if json.loads(path.read_text(encoding="utf-8")).get("well_id") == well_id:
                count += 1
        except (OSError, ValueError):
            continue
    return count


def _managed_las_paths(item: dict[str, Any]) -> list[Path]:
    managed: list[Path] = []
    curve_path = Path(str(item.get("curve_data_path") or ""))
    expected_curve = settings.workspace_dir / "domain" / "las_curves" / f"{item['id']}.json"
    if curve_path and curve_path.resolve() == expected_curve.resolve():
        managed.append(curve_path)

    source_path = Path(str(item.get("path") or ""))
    upload_root = (settings.workspace_dir / "domain" / "las_uploads").resolve()
    if source_path:
        resolved = source_path.resolve()
        if upload_root in resolved.parents:
            references = [
                row for row in domain_store.list("las_files")
                if row.get("id") != item["id"] and Path(str(row.get("path") or "")).resolve() == resolved
            ]
            if not references:
                managed.append(source_path)
    return managed


@router.get("/wells", response_model=list[Well])
async def list_wells():
    return domain_store.list("wells")


@router.post("/wells", response_model=Well)
async def create_well(body: WellIn):
    return domain_store.create("wells", body.model_dump())


@router.get("/wells/{well_id}", response_model=Well)
async def get_well(well_id: str):
    return _get_or_404("wells", well_id)


@router.put("/wells/{well_id}", response_model=Well)
async def update_well(well_id: str, body: WellIn):
    item = domain_store.update("wells", well_id, body.model_dump())
    if item is None:
        raise HTTPException(status_code=404, detail="well not found")
    return item


@router.delete("/wells/{well_id}")
async def delete_well(well_id: str):
    _get_or_404("wells", well_id)
    dependencies = domain_store.related_counts(well_id)
    dependencies["artifacts"] = _artifact_count(well_id)
    blocking = {name: count for name, count in dependencies.items() if count}
    if blocking:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "well_has_dependencies",
                "message": "well has related records and cannot be deleted",
                "dependencies": blocking,
            },
        )
    if not domain_store.delete("wells", well_id):
        _get_or_404("wells", well_id)
    return {"deleted": well_id}


@router.get("/sections", response_model=list[WellboreSection])
async def list_sections(well_id: str = ""):
    return domain_store.list("sections", well_id)


@router.post("/sections", response_model=WellboreSection)
async def create_section(body: SectionIn):
    return _create_related("sections", body.model_dump())


@router.get("/sections/{section_id}", response_model=WellboreSection)
async def get_section(section_id: str):
    return _get_or_404("sections", section_id)


@router.put("/sections/{section_id}", response_model=WellboreSection)
async def update_section(section_id: str, body: SectionIn):
    return _update_related("sections", section_id, body.model_dump())


@router.delete("/sections/{section_id}")
async def delete_section(section_id: str):
    if not domain_store.delete("sections", section_id):
        raise HTTPException(status_code=404, detail="section not found")
    return {"deleted": section_id}


@router.get("/reports", response_model=list[DailyReport])
async def list_reports(well_id: str = ""):
    return domain_store.list("reports", well_id)


@router.post("/reports", response_model=DailyReport)
async def create_report(body: DailyReportIn):
    return _create_related("reports", body.model_dump())


@router.get("/reports/{report_id}", response_model=DailyReport)
async def get_report(report_id: str):
    return _get_or_404("reports", report_id)


@router.put("/reports/{report_id}", response_model=DailyReport)
async def update_report(report_id: str, body: DailyReportIn):
    return _update_related("reports", report_id, body.model_dump())


@router.delete("/reports/{report_id}")
async def delete_report(report_id: str):
    if not domain_store.delete("reports", report_id):
        _get_or_404("reports", report_id)
    return {"deleted": report_id}


@router.get("/params", response_model=list[DrillingParam])
async def list_params(well_id: str = ""):
    return domain_store.list("params", well_id)


@router.post("/params", response_model=DrillingParam)
async def create_param(body: DrillingParamIn):
    return _create_related("params", body.model_dump())


@router.get("/params/{param_id}", response_model=DrillingParam)
async def get_param(param_id: str):
    return _get_or_404("params", param_id)


@router.put("/params/{param_id}", response_model=DrillingParam)
async def update_param(param_id: str, body: DrillingParamIn):
    return _update_related("params", param_id, body.model_dump())


@router.delete("/params/{param_id}")
async def delete_param(param_id: str):
    if not domain_store.delete("params", param_id):
        _get_or_404("params", param_id)
    return {"deleted": param_id}


@router.get("/las-files", response_model=list[LasFile])
async def list_las_files(well_id: str = ""):
    return domain_store.list("las_files", well_id)


@router.post("/las-files", response_model=LasFile)
async def create_las_file(body: LasFileIn):
    return _create_related("las_files", body.model_dump())


@router.get("/las-files/{las_id}", response_model=LasFile)
async def get_las_file(las_id: str):
    return _get_or_404("las_files", las_id)


@router.put("/las-files/{las_id}", response_model=LasFile)
async def update_las_file(las_id: str, body: LasFileIn):
    return _update_related("las_files", las_id, body.model_dump())


@router.delete("/las-files/{las_id}")
async def delete_las_file(las_id: str):
    item = _get_or_404("las_files", las_id)
    managed_paths = _managed_las_paths(item)
    if not domain_store.delete("las_files", las_id):
        _get_or_404("las_files", las_id)
    deleted_files: list[str] = []
    cleanup_errors: list[str] = []
    for path in managed_paths:
        try:
            path.unlink(missing_ok=True)
            deleted_files.append(str(path))
        except OSError as exc:
            cleanup_errors.append(f"{path}: {exc}")
    return {"deleted": las_id, "deleted_files": deleted_files, "cleanup_errors": cleanup_errors}


@router.post("/las/import", response_model=LasFile)
async def import_las(body: LasImportIn):
    _require_well(body.well_id)
    try:
        return import_las_file(body.well_id, body.path, body.filename)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="las file not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail={"code": "well_not_found", "message": str(exc)}) from exc


@router.post("/las/upload", response_model=LasFile)
async def upload_las(
    well_id: str = Form(...),
    file: UploadFile = File(...),
    filename: str = Form(""),
):
    _require_well(well_id)
    safe_name = _safe_upload_name(filename or file.filename or "upload.las")
    upload_dir = settings.workspace_dir / "domain" / "las_uploads"
    content = await file.read()
    _validate_las_upload(safe_name, content)
    upload_dir.mkdir(parents=True, exist_ok=True)
    upload_path = upload_dir / safe_name
    if upload_path.exists():
        upload_path = upload_dir / f"{upload_path.stem}-{uuid.uuid4().hex[:8]}{upload_path.suffix}"
    upload_path.write_bytes(content)
    try:
        return import_las_file(well_id, str(upload_path), safe_name)
    except Exception:
        upload_path.unlink(missing_ok=True)
        raise

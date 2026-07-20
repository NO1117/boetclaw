"""Minimal LAS text parser and importer."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.domain.store import domain_store

NULL_VALUE = -999.25


def parse_las_text(text: str) -> dict[str, Any]:
    curves: list[str] = []
    rows: list[dict[str, float | None]] = []
    section = ""

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("~"):
            section = line[:2].upper()
            continue
        if section == "~C":
            name = line.split(".", 1)[0].strip()
            if name:
                curves.append(name)
        elif section == "~A":
            if not curves:
                continue
            parts = line.split()
            if len(parts) < len(curves):
                continue
            row: dict[str, float | None] = {}
            for name, value in zip(curves, parts):
                try:
                    parsed = float(value)
                except ValueError:
                    parsed = NULL_VALUE
                row[name] = None if parsed == NULL_VALUE else parsed
            rows.append(row)

    depth_key = curves[0] if curves else "DEPT"
    depths: list[float] = [
        value for row in rows if (value := row.get(depth_key)) is not None
    ]
    null_count = sum(1 for row in rows for value in row.values() if value is None)
    warnings = []
    if not curves:
        warnings.append("未识别到 ~Curve 曲线定义")
    if not rows:
        warnings.append("未识别到 ~A 数据段")

    return {
        "curves": curves,
        "rows": rows,
        "quality": {
            "point_count": len(rows),
            "curve_count": len(curves),
            "null_count": null_count,
            "depth_min": min(depths) if depths else None,
            "depth_max": max(depths) if depths else None,
            "warnings": warnings,
        },
    }


def import_las_file(well_id: str, file_path: str, filename: str = "") -> dict[str, Any]:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(file_path)
    parsed = parse_las_text(path.read_text(encoding="utf-8", errors="ignore"))
    las = domain_store.create_related(
        "las_files",
        {
            "well_id": well_id,
            "filename": filename or path.name,
            "path": str(path),
            "status": "imported" if parsed["rows"] else "failed",
            "curves": parsed["curves"],
            "depth_min": parsed["quality"]["depth_min"],
            "depth_max": parsed["quality"]["depth_max"],
            "quality": parsed["quality"],
        },
    )
    if las is None:
        raise ValueError("well not found")
    curve_dir = settings.workspace_dir / "domain" / "las_curves"
    curve_dir.mkdir(parents=True, exist_ok=True)
    curve_path = curve_dir / f"{las['id']}.json"
    temp_path = curve_dir / f".{las['id']}.{uuid.uuid4().hex}.tmp"
    try:
        with temp_path.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(parsed["rows"], handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, curve_path)
    finally:
        temp_path.unlink(missing_ok=True)
    updated = domain_store.update("las_files", las["id"], {"curve_data_path": str(curve_path), "quality": parsed["quality"]})
    return updated or las

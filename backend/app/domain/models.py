"""Drilling domain models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DomainBase(BaseModel):
    id: str
    created_at: str
    updated_at: str


class Well(DomainBase):
    name: str
    field: str = ""
    operator: str = ""
    location: str = ""
    status: str = "planned"
    metadata: dict[str, Any] = Field(default_factory=dict)


class WellboreSection(DomainBase):
    well_id: str
    name: str
    top_depth: float = 0
    bottom_depth: float = 0
    hole_size: str = ""
    start_date: str = ""
    end_date: str = ""


class DailyReport(DomainBase):
    well_id: str
    report_date: str
    depth_start: float = 0
    depth_end: float = 0
    summary: str = ""
    issues: str = ""


class DrillingParam(DomainBase):
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


class LasFile(DomainBase):
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

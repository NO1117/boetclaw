"""Voice stage metrics (no raw audio or full text)."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.core.observability import EventType, emit_event, new_trace_id


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class VoiceMetricsSummary:
    trace_id: str
    operation: str
    provider: str | None = None
    model: str | None = None
    status: str = "running"
    started_at: str = field(default_factory=_now_iso)
    completed_at: str | None = None
    upload_ms: float | None = None
    first_byte_ms: float | None = None
    total_ms: float | None = None
    audio_bytes: int | None = None
    audio_duration_seconds: float | None = None
    input_chars: int | None = None
    output_bytes: int | None = None
    format: str | None = None
    failure_category: str | None = None
    estimated_cost: float | None = None
    cost_currency: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "operation": self.operation,
            "provider": self.provider,
            "model": self.model,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "upload_ms": self.upload_ms,
            "first_byte_ms": self.first_byte_ms,
            "total_ms": self.total_ms,
            "audio_bytes": self.audio_bytes,
            "audio_duration_seconds": self.audio_duration_seconds,
            "input_chars": self.input_chars,
            "output_bytes": self.output_bytes,
            "format": self.format,
            "failure_category": self.failure_category,
            "estimated_cost": self.estimated_cost,
            "cost_currency": self.cost_currency,
        }


class VoiceMetricsTracker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._runs: dict[str, VoiceMetricsSummary] = {}
        self._started_mono: dict[str, float] = {}

    def start(self, *, operation: str, trace_id: str | None = None) -> VoiceMetricsSummary:
        tid = trace_id or new_trace_id()
        summary = VoiceMetricsSummary(trace_id=tid, operation=operation)
        with self._lock:
            self._runs[tid] = summary
            self._started_mono[tid] = time.monotonic()
        emit_event(
            EventType.VOICE_STAGE,
            {
                "operation": operation,
                "status": "start",
            },
            trace_id=tid,
        )
        return summary

    def complete(
        self,
        trace_id: str,
        *,
        status: str = "completed",
        provider: str | None = None,
        model: str | None = None,
        upload_ms: float | None = None,
        first_byte_ms: float | None = None,
        audio_bytes: int | None = None,
        audio_duration_seconds: float | None = None,
        input_chars: int | None = None,
        output_bytes: int | None = None,
        fmt: str | None = None,
        failure_category: str | None = None,
        estimated_cost: float | None = None,
    ) -> VoiceMetricsSummary | None:
        with self._lock:
            summary = self._runs.get(trace_id)
            mono = self._started_mono.get(trace_id)
            if summary is None:
                return None
            summary.status = status
            summary.completed_at = _now_iso()
            if mono is not None:
                summary.total_ms = round((time.monotonic() - mono) * 1000, 1)
            summary.provider = provider
            summary.model = model
            summary.upload_ms = upload_ms
            summary.first_byte_ms = first_byte_ms
            summary.audio_bytes = audio_bytes
            summary.audio_duration_seconds = audio_duration_seconds
            summary.input_chars = input_chars
            summary.output_bytes = output_bytes
            summary.format = fmt
            summary.failure_category = failure_category
            summary.estimated_cost = estimated_cost
            if estimated_cost is not None:
                summary.cost_currency = "USD"
            emit_event(
                EventType.VOICE_STAGE,
                {
                    "operation": summary.operation,
                    "status": status,
                    "provider": provider,
                    "model": model,
                    "upload_ms": upload_ms,
                    "first_byte_ms": first_byte_ms,
                    "total_ms": summary.total_ms,
                    "audio_bytes": audio_bytes,
                    "audio_duration_seconds": audio_duration_seconds,
                    "input_chars": input_chars,
                    "output_bytes": output_bytes,
                    "format": fmt,
                    "failure_category": failure_category,
                    "estimated_cost": estimated_cost,
                },
                trace_id=trace_id,
            )
            return summary

    def get(self, trace_id: str) -> VoiceMetricsSummary | None:
        with self._lock:
            return self._runs.get(trace_id)


voice_metrics_tracker = VoiceMetricsTracker()

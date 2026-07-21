"""Memory observability counters (no content logged)."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field


@dataclass
class MemoryMetrics:
    created: int = 0
    approved: int = 0
    rejected: int = 0
    retrieved: int = 0
    hits: int = 0
    skipped: int = 0
    deduped: int = 0
    deleted: int = 0
    storage_errors: int = 0
    retrieval_ms_total: float = 0.0
    candidates: int = 0
    injected_items: int = 0
    injected_chars: int = 0


class MemoryMetricsTracker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._metrics = MemoryMetrics()

    def inc(self, name: str, amount: int = 1) -> None:
        with self._lock:
            current = getattr(self._metrics, name, None)
            if isinstance(current, int):
                setattr(self._metrics, name, current + amount)

    def add_retrieval_ms(self, ms: float) -> None:
        with self._lock:
            self._metrics.retrieval_ms_total += ms

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "created": self._metrics.created,
                "approved": self._metrics.approved,
                "rejected": self._metrics.rejected,
                "retrieved": self._metrics.retrieved,
                "hits": self._metrics.hits,
                "skipped": self._metrics.skipped,
                "deduped": self._metrics.deduped,
                "deleted": self._metrics.deleted,
                "storage_errors": self._metrics.storage_errors,
                "retrieval_ms_total": round(self._metrics.retrieval_ms_total, 2),
                "candidates": self._metrics.candidates,
                "injected_items": self._metrics.injected_items,
                "injected_chars": self._metrics.injected_chars,
            }


memory_metrics = MemoryMetricsTracker()

"""Profile validation metrics."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


@dataclass
class ProfileMetrics:
    save_success: int = 0
    save_failed: int = 0
    validate_total: int = 0
    validate_ms_total: float = 0.0
    rebuild_ms_total: float = 0.0
    rebuild_count: int = 0
    rollback_count: int = 0
    revision_conflicts: int = 0

    def to_dict(self) -> dict[str, int | float]:
        avg_validate = self.validate_ms_total / self.validate_total if self.validate_total else 0.0
        avg_rebuild = self.rebuild_ms_total / self.rebuild_count if self.rebuild_count else 0.0
        return {
            "save_success": self.save_success,
            "save_failed": self.save_failed,
            "validate_total": self.validate_total,
            "validate_avg_ms": round(avg_validate, 2),
            "rebuild_avg_ms": round(avg_rebuild, 2),
            "rollback_count": self.rollback_count,
            "revision_conflicts": self.revision_conflicts,
        }


class ProfileMetricsCollector:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._metrics = ProfileMetrics()

    def record_save(self, *, success: bool) -> None:
        with self._lock:
            if success:
                self._metrics.save_success += 1
            else:
                self._metrics.save_failed += 1

    def record_validate(self, elapsed_ms: float) -> None:
        with self._lock:
            self._metrics.validate_total += 1
            self._metrics.validate_ms_total += elapsed_ms

    def record_rebuild(self, elapsed_ms: float) -> None:
        with self._lock:
            self._metrics.rebuild_count += 1
            self._metrics.rebuild_ms_total += elapsed_ms

    def record_rollback(self) -> None:
        with self._lock:
            self._metrics.rollback_count += 1

    def record_conflict(self) -> None:
        with self._lock:
            self._metrics.revision_conflicts += 1

    def snapshot(self) -> dict[str, int | float]:
        with self._lock:
            return self._metrics.to_dict()


profile_metrics = ProfileMetricsCollector()


class validate_timer:
    def __enter__(self) -> validate_timer:
        self._started = time.perf_counter()
        return self

    def __exit__(self, *args: object) -> None:
        elapsed_ms = (time.perf_counter() - self._started) * 1000
        profile_metrics.record_validate(elapsed_ms)

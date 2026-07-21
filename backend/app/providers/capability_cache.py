"""Capability cache: persist learned model capabilities to disk."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from app.core.config import settings


class CapabilityCache:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or (settings.workspace_dir / ".cache" / "capabilities.json")
        self._lock = threading.Lock()
        self._data: dict[str, dict[str, Any]] = self._load()

    def _load(self) -> dict[str, dict[str, Any]]:
        if self._path.exists():
            try:
                return json.loads(self._path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return {}
        return {}

    def _persist(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")

    def get(self, model_key: str, cap: str, default: Any = None) -> Any:
        entry = self._data.get(model_key, {})
        caps = entry.get("capabilities", entry)
        return caps.get(cap, default)

    def learn(self, model_key: str, cap: str, value: Any) -> None:
        with self._lock:
            entry = self._data.setdefault(model_key, {"capabilities": {}, "sources": {}, "updated_at": {}})
            entry.setdefault("capabilities", {})[cap] = value
            self._persist()

    def learn_entry(
        self,
        model_key: str,
        capabilities: dict[str, Any],
        sources: dict[str, str],
        updated_at: dict[str, str],
    ) -> None:
        with self._lock:
            self._data[model_key] = {
                "capabilities": dict(capabilities),
                "sources": dict(sources),
                "updated_at": dict(updated_at),
            }
            self._persist()

    def all(self) -> dict[str, dict[str, Any]]:
        return dict(self._data)


_cache: CapabilityCache | None = None


def get_capability_cache() -> CapabilityCache:
    global _cache
    if _cache is None:
        _cache = CapabilityCache()
    return _cache

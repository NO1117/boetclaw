"""JSON-backed repository for drilling domain objects."""

from __future__ import annotations

import json
import os
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import settings


COLLECTIONS = ("wells", "sections", "reports", "params", "las_files")
SCHEMA_VERSION = 1


class DomainStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or settings.workspace_dir / "domain" / "domain_data.json"
        self._lock = threading.RLock()

    def _empty(self) -> dict[str, Any]:
        return {"schema_version": SCHEMA_VERSION, **{name: [] for name in COLLECTIONS}}

    def _load_unlocked(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._empty()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        version = data.get("schema_version", SCHEMA_VERSION)
        if version != SCHEMA_VERSION:
            raise ValueError(f"unsupported domain schema_version: {version}")
        return {"schema_version": SCHEMA_VERSION, **{name: list(data.get(name, [])) for name in COLLECTIONS}}

    def load(self) -> dict[str, Any]:
        with self._lock:
            return self._load_unlocked()

    def _save_unlocked(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema_version": SCHEMA_VERSION, **{name: list(data.get(name, [])) for name in COLLECTIONS}}
        temp_path = self.path.with_name(f".{self.path.name}.{uuid.uuid4().hex}.tmp")
        backup_path = self.path.with_suffix(f"{self.path.suffix}.bak")
        try:
            if self.path.exists():
                shutil.copy2(self.path, backup_path)
            with temp_path.open("w", encoding="utf-8", newline="\n") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.path)
        finally:
            temp_path.unlink(missing_ok=True)

    def save(self, data: dict[str, Any]) -> None:
        with self._lock:
            self._save_unlocked(data)

    def list(self, collection: str, well_id: str = "") -> list[dict[str, Any]]:
        with self._lock:
            rows = self._load_unlocked()[collection]
            if well_id:
                rows = [row for row in rows if row.get("well_id") == well_id or row.get("id") == well_id]
            return rows

    def get(self, collection: str, item_id: str) -> dict[str, Any] | None:
        with self._lock:
            return next((row for row in self._load_unlocked()[collection] if row.get("id") == item_id), None)

    def create(self, collection: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            data = self._load_unlocked()
            now = datetime.now(timezone.utc).isoformat()
            item = {**payload, "id": payload.get("id") or uuid.uuid4().hex[:12], "created_at": now, "updated_at": now}
            data[collection].append(item)
            self._save_unlocked(data)
            return item

    def create_related(self, collection: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        with self._lock:
            data = self._load_unlocked()
            if not any(row.get("id") == payload.get("well_id") for row in data["wells"]):
                return None
            now = datetime.now(timezone.utc).isoformat()
            item = {**payload, "id": payload.get("id") or uuid.uuid4().hex[:12], "created_at": now, "updated_at": now}
            data[collection].append(item)
            self._save_unlocked(data)
            return item

    def update(self, collection: str, item_id: str, changes: dict[str, Any]) -> dict[str, Any] | None:
        with self._lock:
            data = self._load_unlocked()
            return self._update_unlocked(data, collection, item_id, changes)

    def update_related(self, collection: str, item_id: str, changes: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
        with self._lock:
            data = self._load_unlocked()
            if not any(row.get("id") == item_id for row in data[collection]):
                return "missing_item", None
            if not any(row.get("id") == changes.get("well_id") for row in data["wells"]):
                return "missing_well", None
            return "updated", self._update_unlocked(data, collection, item_id, changes)

    def _update_unlocked(
        self,
        data: dict[str, Any],
        collection: str,
        item_id: str,
        changes: dict[str, Any],
    ) -> dict[str, Any] | None:
        for idx, row in enumerate(data[collection]):
            if row.get("id") == item_id:
                updated = {**row, **{k: v for k, v in changes.items() if v is not None}}
                updated["id"] = item_id
                updated["created_at"] = row.get("created_at", updated.get("created_at", ""))
                updated["updated_at"] = datetime.now(timezone.utc).isoformat()
                data[collection][idx] = updated
                self._save_unlocked(data)
                return updated
        return None

    def delete(self, collection: str, item_id: str) -> bool:
        with self._lock:
            data = self._load_unlocked()
            before = len(data[collection])
            data[collection] = [row for row in data[collection] if row.get("id") != item_id]
            if len(data[collection]) == before:
                return False
            self._save_unlocked(data)
            return True

    def related_counts(self, well_id: str) -> dict[str, int]:
        with self._lock:
            data = self._load_unlocked()
            return {
                name: sum(1 for row in data[name] if row.get("well_id") == well_id)
                for name in COLLECTIONS
                if name != "wells"
            }


domain_store = DomainStore()

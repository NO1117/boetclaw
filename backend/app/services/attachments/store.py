"""JSON-backed attachment metadata store with agent isolation."""

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
from app.services.attachments.models import AttachmentRecord, AttachmentTombstone, TextChunk


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AttachmentStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or (settings.workspace_dir / "attachments")
        self._lock = threading.RLock()

    def agent_root(self, agent_id: str) -> Path:
        safe = "".join(ch for ch in agent_id if ch.isalnum() or ch in ("-", "_"))[:64]
        return self.root / safe

    def attachment_dir(self, agent_id: str, attachment_id: str) -> Path:
        safe_id = "".join(ch for ch in attachment_id if ch.isalnum() or ch in ("-", "_"))[:64]
        return self.agent_root(agent_id) / safe_id

    def meta_path(self, agent_id: str, attachment_id: str) -> Path:
        return self.attachment_dir(agent_id, attachment_id) / "meta.json"

    def original_path(self, agent_id: str, attachment_id: str) -> Path:
        return self.attachment_dir(agent_id, attachment_id) / "original.bin"

    def chunks_path(self, agent_id: str, attachment_id: str) -> Path:
        return self.attachment_dir(agent_id, attachment_id) / "chunks.json"

    def index_path(self, agent_id: str, attachment_id: str) -> Path:
        return self.attachment_dir(agent_id, attachment_id) / "keyword_index.json"

    def tombstones_path(self, agent_id: str) -> Path:
        return self.agent_root(agent_id) / "tombstones.json"

    def _read_json(self, path: Path) -> Any:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_json_atomic(self, path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            with temp.open("w", encoding="utf-8", newline="\n") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
        finally:
            temp.unlink(missing_ok=True)

    def load_record(self, agent_id: str, attachment_id: str) -> AttachmentRecord | None:
        with self._lock:
            raw = self._read_json(self.meta_path(agent_id, attachment_id))
            if raw is None:
                return None
            return AttachmentRecord.model_validate(raw)

    def save_record(self, record: AttachmentRecord) -> AttachmentRecord:
        with self._lock:
            record.updated_at = _utc_now()
            self._write_json_atomic(
                self.meta_path(record.agent_id, record.attachment_id),
                record.model_dump(),
            )
            return record

    def write_original(self, agent_id: str, attachment_id: str, data: bytes) -> Path:
        with self._lock:
            path = self.original_path(agent_id, attachment_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_name(f".original.{uuid.uuid4().hex}.tmp")
            try:
                temp.write_bytes(data)
                os.replace(temp, path)
            finally:
                temp.unlink(missing_ok=True)
            return path

    def read_original(self, agent_id: str, attachment_id: str) -> bytes | None:
        path = self.original_path(agent_id, attachment_id)
        if not path.exists():
            return None
        return path.read_bytes()

    def save_chunks(self, agent_id: str, attachment_id: str, chunks: list[TextChunk]) -> None:
        with self._lock:
            payload = [c.model_dump() for c in chunks]
            self._write_json_atomic(self.chunks_path(agent_id, attachment_id), payload)

    def load_chunks(self, agent_id: str, attachment_id: str) -> list[TextChunk]:
        with self._lock:
            raw = self._read_json(self.chunks_path(agent_id, attachment_id))
            if not raw:
                return []
            return [TextChunk.model_validate(item) for item in raw]

    def save_keyword_index(self, agent_id: str, attachment_id: str, index: dict[str, list[str]]) -> None:
        with self._lock:
            self._write_json_atomic(self.index_path(agent_id, attachment_id), index)

    def load_keyword_index(self, agent_id: str, attachment_id: str) -> dict[str, list[str]]:
        with self._lock:
            raw = self._read_json(self.index_path(agent_id, attachment_id))
            return raw if isinstance(raw, dict) else {}

    def list_records(self, agent_id: str, *, include_deleted: bool = False) -> list[AttachmentRecord]:
        with self._lock:
            base = self.agent_root(agent_id)
            if not base.exists():
                return []
            rows: list[AttachmentRecord] = []
            for child in base.iterdir():
                if not child.is_dir():
                    continue
                meta = child / "meta.json"
                if not meta.exists():
                    continue
                record = AttachmentRecord.model_validate(json.loads(meta.read_text(encoding="utf-8")))
                if record.status == "deleted" and not include_deleted:
                    continue
                rows.append(record)
            rows.sort(key=lambda r: r.created_at, reverse=True)
            return rows

    def append_tombstone(self, agent_id: str, tombstone: AttachmentTombstone) -> None:
        with self._lock:
            path = self.tombstones_path(agent_id)
            rows: list[dict[str, Any]] = []
            if path.exists():
                rows = json.loads(path.read_text(encoding="utf-8"))
            rows.append(tombstone.model_dump())
            self._write_json_atomic(path, rows[-500:])

    def delete_attachment_files(self, agent_id: str, attachment_id: str) -> None:
        with self._lock:
            directory = self.attachment_dir(agent_id, attachment_id)
            if directory.exists():
                shutil.rmtree(directory, ignore_errors=True)

    def find_by_id_any_agent(self, attachment_id: str) -> AttachmentRecord | None:
        """Internal lookup across agents — returns None if not found; never expose cross-agent."""
        with self._lock:
            if not self.root.exists():
                return None
            for agent_dir in self.root.iterdir():
                if not agent_dir.is_dir():
                    continue
                meta = agent_dir / attachment_id / "meta.json"
                if meta.exists():
                    return AttachmentRecord.model_validate(json.loads(meta.read_text(encoding="utf-8")))
            return None


attachment_store = AttachmentStore()

"""JSON-backed knowledge base store with atomic writes and schema migration."""

from __future__ import annotations

import json
import os
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.core.config import settings
from app.core.observability import get_logger
from app.services.attachments.models import TextChunk
from app.services.knowledge_base.models import (
    CURRENT_SCHEMA_VERSION,
    AgentKBBinding,
    AgentKBBindingsFile,
    KBDocumentRecord,
    KnowledgeBaseRecord,
)

logger = get_logger("knowledge_base_store")


class KnowledgeBaseStoreError(ValueError):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class KnowledgeBaseConflictError(KnowledgeBaseStoreError):
    def __init__(self, expected: int, actual: int) -> None:
        super().__init__(f"知识库 revision 冲突：期望 {expected}，当前 {actual}", 409)
        self.expected_revision = expected
        self.actual_revision = actual


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sanitize_id(value: str, *, max_len: int = 64) -> str:
    return "".join(ch for ch in value if ch.isalnum() or ch in ("-", "_"))[:max_len]


class KnowledgeBaseStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or (settings.workspace_dir / "knowledge_bases")
        self._locks: dict[str, threading.Lock] = {}
        self._global_lock = threading.Lock()
        self._corrupt_dir = self.root / "_corrupt"

    def _lock(self, key: str) -> threading.Lock:
        with self._global_lock:
            if key not in self._locks:
                self._locks[key] = threading.Lock()
            return self._locks[key]

    def agent_root(self, agent_id: str) -> Path:
        return self.root / _sanitize_id(agent_id)

    def kb_dir(self, agent_id: str, kb_id: str) -> Path:
        return self.agent_root(agent_id) / _sanitize_id(kb_id)

    def kb_meta_path(self, agent_id: str, kb_id: str) -> Path:
        return self.kb_dir(agent_id, kb_id) / "meta.json"

    def doc_dir(self, agent_id: str, kb_id: str, doc_id: str) -> Path:
        return self.kb_dir(agent_id, kb_id) / "documents" / _sanitize_id(doc_id)

    def doc_meta_path(self, agent_id: str, kb_id: str, doc_id: str) -> Path:
        return self.doc_dir(agent_id, kb_id, doc_id) / "meta.json"

    def blob_dir(self, agent_id: str, sha256: str) -> Path:
        return self.agent_root(agent_id) / "blobs" / _sanitize_id(sha256, max_len=128)

    def bindings_path(self, agent_id: str) -> Path:
        return self.agent_root(agent_id) / "bindings.json"

    def _read_json(self, path: Path) -> Any:
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            self._isolate_corrupt(path, exc)
            return None

    def _isolate_corrupt(self, path: Path, exc: Exception) -> None:
        self._corrupt_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        target = self._corrupt_dir / f"{path.name}.{stamp}.corrupt"
        try:
            shutil.copy2(path, target)
        except OSError:
            pass
        logger.warning("kb_corrupt_file_isolated", path=str(path), error=str(exc))

    def _write_json_atomic(self, path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        backup = path.with_suffix(path.suffix + ".bak")
        if path.exists():
            try:
                shutil.copy2(path, backup)
            except OSError:
                pass
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

    def _migrate_kb(self, raw: dict[str, Any]) -> dict[str, Any]:
        version = int(raw.get("schema_version", 0) or 0)
        if version == 0:
            raw["schema_version"] = CURRENT_SCHEMA_VERSION
            raw.setdefault("revision", 1)
            return raw
        if version > CURRENT_SCHEMA_VERSION:
            raise KnowledgeBaseStoreError(f"不支持的 schema 版本: {version}")
        return raw

    def load_kb(self, agent_id: str, kb_id: str) -> KnowledgeBaseRecord | None:
        with self._lock(f"kb:{agent_id}:{kb_id}"):
            raw = self._read_json(self.kb_meta_path(agent_id, kb_id))
            if raw is None:
                return None
            try:
                migrated = self._migrate_kb(raw)
                return KnowledgeBaseRecord.model_validate(migrated)
            except ValidationError as exc:
                self._isolate_corrupt(self.kb_meta_path(agent_id, kb_id), exc)
                return None

    def save_kb(self, record: KnowledgeBaseRecord, *, expected_revision: int | None = None) -> KnowledgeBaseRecord:
        key = f"kb:{record.agent_id}:{record.knowledge_base_id}"
        with self._lock(key):
            if expected_revision is not None:
                current = self.load_kb(record.agent_id, record.knowledge_base_id)
                if current is not None and current.revision != expected_revision:
                    raise KnowledgeBaseConflictError(expected_revision, current.revision)
            record.updated_at = _utc_now()
            self._write_json_atomic(
                self.kb_meta_path(record.agent_id, record.knowledge_base_id),
                record.model_dump(),
            )
            return record

    def list_kbs(self, agent_id: str, *, status: str | None = None) -> list[KnowledgeBaseRecord]:
        with self._lock(f"agent:{agent_id}"):
            base = self.agent_root(agent_id)
            if not base.exists():
                return []
            rows: list[KnowledgeBaseRecord] = []
            for child in base.iterdir():
                if not child.is_dir() or child.name in ("blobs", "_corrupt"):
                    continue
                meta = child / "meta.json"
                if not meta.exists():
                    continue
                kb = self.load_kb(agent_id, child.name)
                if kb is None:
                    continue
                if status and kb.status != status:
                    continue
                if kb.status == "deleted" and status != "deleted":
                    continue
                rows.append(kb)
            rows.sort(key=lambda r: r.updated_at, reverse=True)
            return rows

    def load_document(self, agent_id: str, kb_id: str, doc_id: str) -> KBDocumentRecord | None:
        with self._lock(f"doc:{agent_id}:{kb_id}:{doc_id}"):
            raw = self._read_json(self.doc_meta_path(agent_id, kb_id, doc_id))
            if raw is None:
                return None
            try:
                return KBDocumentRecord.model_validate(raw)
            except ValidationError as exc:
                self._isolate_corrupt(self.doc_meta_path(agent_id, kb_id, doc_id), exc)
                return None

    def save_document(self, record: KBDocumentRecord) -> KBDocumentRecord:
        key = f"doc:{record.agent_id}:{record.knowledge_base_id}:{record.document_id}"
        with self._lock(key):
            record.updated_at = _utc_now()
            self._write_json_atomic(
                self.doc_meta_path(record.agent_id, record.knowledge_base_id, record.document_id),
                record.model_dump(),
            )
            return record

    def list_documents(self, agent_id: str, kb_id: str, *, include_removed: bool = False) -> list[KBDocumentRecord]:
        with self._lock(f"kb:{agent_id}:{kb_id}"):
            docs_root = self.kb_dir(agent_id, kb_id) / "documents"
            if not docs_root.exists():
                return []
            rows: list[KBDocumentRecord] = []
            for child in docs_root.iterdir():
                if not child.is_dir():
                    continue
                doc = self.load_document(agent_id, kb_id, child.name)
                if doc is None:
                    continue
                if doc.status == "removed" and not include_removed:
                    continue
                rows.append(doc)
            rows.sort(key=lambda r: r.created_at, reverse=True)
            return rows

    def write_blob(self, agent_id: str, sha256: str, data: bytes) -> Path:
        with self._lock(f"blob:{agent_id}:{sha256}"):
            path = self.blob_dir(agent_id, sha256) / "original.bin"
            if path.exists():
                return path
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_name(f".original.{uuid.uuid4().hex}.tmp")
            try:
                temp.write_bytes(data)
                os.replace(temp, path)
            finally:
                temp.unlink(missing_ok=True)
            return path

    def read_blob(self, agent_id: str, sha256: str) -> bytes | None:
        path = self.blob_dir(agent_id, sha256) / "original.bin"
        if not path.exists():
            return None
        return path.read_bytes()

    def blob_has_artifacts(self, agent_id: str, sha256: str) -> bool:
        base = self.blob_dir(agent_id, sha256)
        return (base / "chunks.json").exists() and (base / "keyword_index.json").exists()

    def save_blob_chunks(self, agent_id: str, sha256: str, chunks: list[TextChunk]) -> None:
        with self._lock(f"blob:{agent_id}:{sha256}"):
            payload = [c.model_dump() for c in chunks]
            self._write_json_atomic(self.blob_dir(agent_id, sha256) / "chunks.json", payload)

    def load_blob_chunks(self, agent_id: str, sha256: str) -> list[TextChunk]:
        with self._lock(f"blob:{agent_id}:{sha256}"):
            raw = self._read_json(self.blob_dir(agent_id, sha256) / "chunks.json")
            if not raw:
                return []
            return [TextChunk.model_validate(item) for item in raw]

    def save_blob_index(self, agent_id: str, sha256: str, index: dict[str, list[str]]) -> None:
        with self._lock(f"blob:{agent_id}:{sha256}"):
            self._write_json_atomic(self.blob_dir(agent_id, sha256) / "keyword_index.json", index)

    def load_blob_index(self, agent_id: str, sha256: str) -> dict[str, list[str]]:
        with self._lock(f"blob:{agent_id}:{sha256}"):
            raw = self._read_json(self.blob_dir(agent_id, sha256) / "keyword_index.json")
            return raw if isinstance(raw, dict) else {}

    def increment_blob_ref(self, agent_id: str, sha256: str, ref: dict[str, str]) -> None:
        with self._lock(f"blob:{agent_id}:{sha256}"):
            refs_path = self.blob_dir(agent_id, sha256) / "refs.json"
            data: dict[str, Any] = self._read_json(refs_path) or {"ref_count": 0, "refs": []}
            refs: list[dict[str, str]] = list(data.get("refs", []))
            key = f"{ref.get('type')}:{ref.get('kb_id')}:{ref.get('doc_id')}"
            if not any(f"{r.get('type')}:{r.get('kb_id')}:{r.get('doc_id')}" == key for r in refs):
                refs.append(ref)
                data["refs"] = refs
                data["ref_count"] = len(refs)
                self._write_json_atomic(refs_path, data)

    def decrement_blob_ref(self, agent_id: str, sha256: str, ref: dict[str, str]) -> int:
        with self._lock(f"blob:{agent_id}:{sha256}"):
            refs_path = self.blob_dir(agent_id, sha256) / "refs.json"
            data: dict[str, Any] = self._read_json(refs_path) or {"ref_count": 0, "refs": []}
            refs: list[dict[str, str]] = list(data.get("refs", []))
            key = f"{ref.get('type')}:{ref.get('kb_id')}:{ref.get('doc_id')}"
            refs = [r for r in refs if f"{r.get('type')}:{r.get('kb_id')}:{r.get('doc_id')}" != key]
            data["refs"] = refs
            data["ref_count"] = len(refs)
            if refs:
                self._write_json_atomic(refs_path, data)
            elif refs_path.exists():
                refs_path.unlink(missing_ok=True)
            return len(refs)

    def delete_blob_if_unreferenced(self, agent_id: str, sha256: str) -> bool:
        with self._lock(f"blob:{agent_id}:{sha256}"):
            refs_path = self.blob_dir(agent_id, sha256) / "refs.json"
            data = self._read_json(refs_path)
            if data and int(data.get("ref_count", 0) or 0) > 0:
                return False
            directory = self.blob_dir(agent_id, sha256)
            if directory.exists():
                shutil.rmtree(directory, ignore_errors=True)
            return True

    def load_bindings(self, agent_id: str) -> AgentKBBindingsFile:
        with self._lock(f"bindings:{agent_id}"):
            raw = self._read_json(self.bindings_path(agent_id))
            if raw is None:
                return AgentKBBindingsFile(agent_id=agent_id, updated_at=_utc_now())
            try:
                return AgentKBBindingsFile.model_validate(raw)
            except ValidationError:
                return AgentKBBindingsFile(agent_id=agent_id, updated_at=_utc_now())

    def save_bindings(self, data: AgentKBBindingsFile, *, expected_revision: int | None = None) -> AgentKBBindingsFile:
        with self._lock(f"bindings:{data.agent_id}"):
            if expected_revision is not None:
                current = self.load_bindings(data.agent_id)
                if current.revision != expected_revision:
                    raise KnowledgeBaseConflictError(expected_revision, current.revision)
            data.updated_at = _utc_now()
            self._write_json_atomic(self.bindings_path(data.agent_id), data.model_dump())
            return data

    def delete_kb_tree(self, agent_id: str, kb_id: str) -> None:
        with self._lock(f"kb:{agent_id}:{kb_id}"):
            directory = self.kb_dir(agent_id, kb_id)
            if directory.exists():
                shutil.rmtree(directory, ignore_errors=True)


kb_store = KnowledgeBaseStore()

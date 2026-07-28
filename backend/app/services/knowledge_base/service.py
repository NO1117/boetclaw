"""Knowledge base lifecycle: CRUD, documents, bindings, purge."""

from __future__ import annotations

import hashlib
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.core.observability import get_logger
from app.services.attachments.models import TextChunk
from app.services.attachments.security import (
    AttachmentSecurityError,
    infer_kind,
    normalize_agent_id,
    validate_upload_payload,
)
from app.services.attachments.service import attachment_service
from app.services.attachments.store import attachment_store
from app.services.knowledge_base.models import (
    AgentKBBinding,
    AgentKBBindingsFile,
    KBDocumentRecord,
    KnowledgeBaseRecord,
)
from app.services.knowledge_base.parse_pipeline import (
    ParsePipelineError,
    build_index_for_chunks,
    parse_document_bytes,
    safe_error_summary,
)
from app.services.knowledge_base.store import KnowledgeBaseStoreError, kb_store

logger = get_logger("knowledge_base")


class KnowledgeBaseServiceError(ValueError):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex[:16]


class KnowledgeBaseService:
    def __init__(self) -> None:
        self._cancel_flags: set[str] = set()
        self._lock = threading.RLock()

    def _get_kb_or_404(self, agent_id: str, kb_id: str, *, allow_deleted: bool = False) -> KnowledgeBaseRecord:
        normalize_agent_id(agent_id)
        kb = kb_store.load_kb(agent_id, kb_id)
        if kb is None or kb.agent_id != agent_id:
            raise KnowledgeBaseServiceError("知识库不存在", 404)
        if kb.status == "deleted" and not allow_deleted:
            raise KnowledgeBaseServiceError("知识库不存在", 404)
        return kb

    def _refresh_kb_stats(self, agent_id: str, kb_id: str) -> None:
        kb = kb_store.load_kb(agent_id, kb_id)
        if kb is None:
            return
        docs = kb_store.list_documents(agent_id, kb_id)
        kb.document_count = len(docs)
        kb.total_size = sum(d.size for d in docs)
        kb_store.save_kb(kb)

    def create_kb(self, agent_id: str, *, name: str, description: str = "") -> KnowledgeBaseRecord:
        agent_id = normalize_agent_id(agent_id)
        name = name.strip()
        if not name:
            raise KnowledgeBaseServiceError("知识库名称不能为空")
        if len(name) > 128:
            raise KnowledgeBaseServiceError("知识库名称过长")
        now = _iso(_utc_now())
        kb = KnowledgeBaseRecord(
            knowledge_base_id=_new_id(),
            agent_id=agent_id,
            name=name,
            description=description.strip()[:2000],
            created_at=now,
            updated_at=now,
        )
        kb_store.save_kb(kb)
        return kb

    def update_kb(
        self,
        agent_id: str,
        kb_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        expected_revision: int | None = None,
    ) -> KnowledgeBaseRecord:
        kb = self._get_kb_or_404(agent_id, kb_id)
        if kb.status == "archived":
            raise KnowledgeBaseServiceError("已归档知识库不可编辑", 409)
        if name is not None:
            name = name.strip()
            if not name:
                raise KnowledgeBaseServiceError("知识库名称不能为空")
            kb.name = name[:128]
        if description is not None:
            kb.description = description.strip()[:2000]
        kb.revision += 1
        return kb_store.save_kb(kb, expected_revision=expected_revision)

    def archive_kb(self, agent_id: str, kb_id: str) -> KnowledgeBaseRecord:
        kb = self._get_kb_or_404(agent_id, kb_id)
        if kb.status == "archived":
            return kb
        kb.status = "archived"
        kb.revision += 1
        return kb_store.save_kb(kb)

    def restore_kb(self, agent_id: str, kb_id: str) -> KnowledgeBaseRecord:
        kb = self._get_kb_or_404(agent_id, kb_id)
        if kb.status != "archived":
            raise KnowledgeBaseServiceError("知识库未处于归档状态", 409)
        kb.status = "active"
        kb.revision += 1
        return kb_store.save_kb(kb)

    def delete_kb(self, agent_id: str, kb_id: str) -> KnowledgeBaseRecord:
        kb = self._get_kb_or_404(agent_id, kb_id)
        kb.status = "deleted"
        kb.deleted_at = _iso(_utc_now())
        kb.revision += 1
        kb_store.save_kb(kb)
        self._remove_bindings(agent_id, kb_id)
        return kb

    def purge_kb(self, agent_id: str, kb_id: str) -> dict[str, Any]:
        kb = self._get_kb_or_404(agent_id, kb_id, allow_deleted=True)
        if kb.status != "deleted":
            raise KnowledgeBaseServiceError("仅已删除知识库可永久清除", 409)
        docs = kb_store.list_documents(agent_id, kb_id, include_removed=True)
        for doc in docs:
            self._release_document_blob(agent_id, kb_id, doc)
        kb_store.delete_kb_tree(agent_id, kb_id)
        self._remove_bindings(agent_id, kb_id)
        return {"purged": True, "knowledge_base_id": kb_id}

    def list_kbs(self, agent_id: str, *, status: str | None = None, q: str = "") -> list[KnowledgeBaseRecord]:
        normalize_agent_id(agent_id)
        rows = kb_store.list_kbs(agent_id, status=status)
        if q.strip():
            needle = q.strip().lower()
            rows = [r for r in rows if needle in r.name.lower() or needle in r.description.lower()]
        return rows

    def get_kb(self, agent_id: str, kb_id: str) -> KnowledgeBaseRecord:
        return self._get_kb_or_404(agent_id, kb_id)

    async def upload_documents(
        self,
        agent_id: str,
        kb_id: str,
        *,
        files: list[tuple[str, str, str, bytes]],
    ) -> list[KBDocumentRecord]:
        kb = self._get_kb_or_404(agent_id, kb_id)
        if kb.status != "active":
            raise KnowledgeBaseServiceError("知识库不可用", 409)
        if len(files) > settings.kb_max_upload_batch:
            raise KnowledgeBaseServiceError(f"单次最多上传 {settings.kb_max_upload_batch} 个文件")
        existing = kb_store.list_documents(agent_id, kb_id)
        if len(existing) + len(files) > settings.kb_max_documents_per_kb:
            raise KnowledgeBaseServiceError("知识库文档数量已达上限")

        records: list[KBDocumentRecord] = []
        for filename, relative_path, declared_mime, data in files:
            record = await self._ingest_bytes(
                agent_id=agent_id,
                kb_id=kb_id,
                filename=filename,
                relative_path=relative_path,
                declared_mime=declared_mime,
                data=data,
            )
            records.append(record)
        self._refresh_kb_stats(agent_id, kb_id)
        return records

    async def add_from_attachments(
        self,
        agent_id: str,
        kb_id: str,
        attachment_ids: list[str],
    ) -> list[KBDocumentRecord]:
        kb = self._get_kb_or_404(agent_id, kb_id)
        if kb.status != "active":
            raise KnowledgeBaseServiceError("知识库不可用", 409)
        if not attachment_ids:
            raise KnowledgeBaseServiceError("未指定附件")
        existing = kb_store.list_documents(agent_id, kb_id)
        if len(existing) + len(attachment_ids) > settings.kb_max_documents_per_kb:
            raise KnowledgeBaseServiceError("知识库文档数量已达上限")

        records: list[KBDocumentRecord] = []
        for attachment_id in attachment_ids:
            att = attachment_service.get_record(agent_id, attachment_id)
            if att is None:
                raise KnowledgeBaseServiceError("附件不存在或无权访问", 404)
            data = attachment_store.read_original(agent_id, attachment_id)
            if data is None:
                raise KnowledgeBaseServiceError("附件数据不存在", 404)
            record = await self._ingest_bytes(
                agent_id=agent_id,
                kb_id=kb_id,
                filename=att.filename,
                relative_path=att.relative_path,
                declared_mime=att.mime_type,
                data=data,
                source_attachment_id=attachment_id,
                precomputed_sha256=att.sha256,
            )
            records.append(record)
        self._refresh_kb_stats(agent_id, kb_id)
        return records

    async def _ingest_bytes(
        self,
        *,
        agent_id: str,
        kb_id: str,
        filename: str,
        relative_path: str,
        declared_mime: str,
        data: bytes,
        source_attachment_id: str = "",
        precomputed_sha256: str = "",
    ) -> KBDocumentRecord:
        safe_name, safe_path, resolved_mime = validate_upload_payload(
            filename=filename,
            relative_path=relative_path,
            declared_mime=declared_mime,
            size=len(data),
            data=data,
        )
        kb = kb_store.load_kb(agent_id, kb_id)
        if kb is None:
            raise KnowledgeBaseServiceError("知识库不存在", 404)
        current_size = sum(d.size for d in kb_store.list_documents(agent_id, kb_id))
        if current_size + len(data) > settings.kb_max_total_bytes_per_kb:
            raise KnowledgeBaseServiceError("知识库总容量已达上限")

        sha256 = precomputed_sha256 or hashlib.sha256(data).hexdigest()
        kb_store.write_blob(agent_id, sha256, data)

        now = _iso(_utc_now())
        doc_id = _new_id()
        kind = infer_kind(resolved_mime, safe_name)
        record = KBDocumentRecord(
            document_id=doc_id,
            knowledge_base_id=kb_id,
            agent_id=agent_id,
            filename=safe_name,
            relative_path=safe_path if safe_path != safe_name else "",
            mime_type=resolved_mime,
            size=len(data),
            sha256=sha256,
            kind=kind,  # type: ignore[arg-type]
            status="uploaded",
            source_attachment_id=source_attachment_id,
            created_at=now,
            updated_at=now,
        )
        kb_store.save_document(record)
        kb_store.increment_blob_ref(
            agent_id,
            sha256,
            {"type": "kb_doc", "kb_id": kb_id, "doc_id": doc_id},
        )
        self._schedule_parse(record)
        return record

    def _schedule_parse(self, record: KBDocumentRecord) -> None:
        key = f"{record.agent_id}:{record.knowledge_base_id}:{record.document_id}"
        with self._lock:
            if key in self._cancel_flags:
                return
            threading.Thread(
                target=self._parse_sync,
                args=(record.agent_id, record.knowledge_base_id, record.document_id),
                daemon=True,
                name=f"kb-parse-{key}",
            ).start()

    def _parse_sync(self, agent_id: str, kb_id: str, doc_id: str) -> None:
        key = f"{agent_id}:{kb_id}:{doc_id}"
        record = kb_store.load_document(agent_id, kb_id, doc_id)
        if record is None or record.status in ("removed", "ready"):
            return
        if key in self._cancel_flags:
            self._cancel_flags.discard(key)
            return

        record.status = "parsing"
        record.parse_attempts += 1
        kb_store.save_document(record)

        try:
            if kb_store.blob_has_artifacts(agent_id, record.sha256):
                chunks = kb_store.load_blob_chunks(agent_id, record.sha256)
                if chunks:
                    summary = record.summary.model_copy(
                        update={
                            "chunk_count": len(chunks),
                            "char_count": sum(len(c.text) for c in chunks),
                            "searchable": True,
                        }
                    )
                    record.summary = summary
                    record.status = "ready"
                    record.error_summary = ""
                    kb_store.save_document(record)
                    return

            if record.source_attachment_id:
                att = attachment_store.load_record(agent_id, record.source_attachment_id)
                if att and att.status == "ready" and att.sha256 == record.sha256:
                    chunks = attachment_store.load_chunks(agent_id, record.source_attachment_id)
                    index = attachment_store.load_keyword_index(agent_id, record.source_attachment_id)
                    if chunks:
                        self._persist_blob_artifacts(agent_id, record.sha256, chunks, index)
                        record.summary = att.summary
                        record.status = "ready"
                        record.error_summary = ""
                        kb_store.save_document(record)
                        return

            data = kb_store.read_blob(agent_id, record.sha256)
            if data is None:
                raise ParsePipelineError("原始文件不存在")

            chunks, summary, kind = parse_document_bytes(
                data=data,
                filename=record.filename,
                mime_type=record.mime_type,
                content_id=doc_id,
            )
            index = build_index_for_chunks(chunks) if chunks else {}
            self._persist_blob_artifacts(agent_id, record.sha256, chunks, index)
            record.kind = kind  # type: ignore[assignment]
            record.summary = summary
            record.status = "ready"
            record.error_summary = ""
            kb_store.save_document(record)
        except Exception as exc:
            logger.warning(
                "kb_document_parse_failed",
                document_id=doc_id,
                knowledge_base_id=kb_id,
                agent_id=agent_id,
                error_type=type(exc).__name__,
            )
            record = kb_store.load_document(agent_id, kb_id, doc_id)
            if record is None:
                return
            record.status = "failed"
            record.error_summary = safe_error_summary(exc)
            kb_store.save_document(record)

    def _persist_blob_artifacts(
        self,
        agent_id: str,
        sha256: str,
        chunks: list[TextChunk],
        index: dict[str, list[str]],
    ) -> None:
        if not kb_store.blob_has_artifacts(agent_id, sha256):
            kb_store.save_blob_chunks(agent_id, sha256, chunks)
            kb_store.save_blob_index(agent_id, sha256, index)

    def list_documents(self, agent_id: str, kb_id: str) -> list[KBDocumentRecord]:
        self._get_kb_or_404(agent_id, kb_id)
        return kb_store.list_documents(agent_id, kb_id)

    def get_document(self, agent_id: str, kb_id: str, doc_id: str) -> KBDocumentRecord:
        self._get_kb_or_404(agent_id, kb_id)
        doc = kb_store.load_document(agent_id, kb_id, doc_id)
        if doc is None or doc.status == "removed":
            raise KnowledgeBaseServiceError("文档不存在", 404)
        return doc

    async def retry_document(self, agent_id: str, kb_id: str, doc_id: str) -> KBDocumentRecord:
        doc = self.get_document(agent_id, kb_id, doc_id)
        if doc.status not in ("failed", "uploaded"):
            raise KnowledgeBaseServiceError("当前状态不可重试解析")
        doc.error_summary = ""
        kb_store.save_document(doc)
        self._schedule_parse(doc)
        refreshed = kb_store.load_document(agent_id, kb_id, doc_id)
        return refreshed or doc

    async def remove_document(self, agent_id: str, kb_id: str, doc_id: str) -> KBDocumentRecord:
        doc = self.get_document(agent_id, kb_id, doc_id)
        doc.status = "removed"
        doc.removed_at = _iso(_utc_now())
        kb_store.save_document(doc)
        self._release_document_blob(agent_id, kb_id, doc)
        self._refresh_kb_stats(agent_id, kb_id)
        return doc

    def _release_document_blob(self, agent_id: str, kb_id: str, doc: KBDocumentRecord) -> None:
        kb_store.decrement_blob_ref(
            agent_id,
            doc.sha256,
            {"type": "kb_doc", "kb_id": kb_id, "doc_id": doc.document_id},
        )
        kb_store.delete_blob_if_unreferenced(agent_id, doc.sha256)

    def get_snippet_preview(
        self,
        agent_id: str,
        kb_id: str,
        doc_id: str,
        chunk_id: str,
        *,
        max_chars: int = 2000,
    ) -> dict[str, Any]:
        doc = self.get_document(agent_id, kb_id, doc_id)
        if doc.status != "ready":
            raise KnowledgeBaseServiceError("文档尚未就绪", 409)
        chunks = kb_store.load_blob_chunks(agent_id, doc.sha256)
        chunk = next((c for c in chunks if c.chunk_id == chunk_id), None)
        if chunk is None:
            raise KnowledgeBaseServiceError("片段不存在", 404)
        text = chunk.text[:max_chars]
        return {
            "document_id": doc_id,
            "chunk_id": chunk_id,
            "filename": doc.filename,
            "location": chunk.location.model_dump(),
            "text": text,
            "truncated": len(chunk.text) > max_chars,
        }

    def wait_document_ready(
        self,
        agent_id: str,
        kb_id: str,
        doc_id: str,
        timeout: float = 30.0,
    ) -> KBDocumentRecord:
        import time

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            doc = self.get_document(agent_id, kb_id, doc_id)
            if doc.status in ("ready", "failed"):
                return doc
            time.sleep(0.05)
        return self.get_document(agent_id, kb_id, doc_id)

    # --- Bindings ---

    def list_bindings(self, agent_id: str) -> list[AgentKBBinding]:
        normalize_agent_id(agent_id)
        data = kb_store.load_bindings(agent_id)
        return list(data.bindings)

    def bind_kb(self, agent_id: str, kb_id: str, *, enabled_by_default: bool = True) -> AgentKBBinding:
        self._get_kb_or_404(agent_id, kb_id)
        data = kb_store.load_bindings(agent_id)
        for binding in data.bindings:
            if binding.knowledge_base_id == kb_id:
                binding.enabled_by_default = enabled_by_default
                kb_store.save_bindings(data)
                return binding
        binding = AgentKBBinding(
            knowledge_base_id=kb_id,
            enabled_by_default=enabled_by_default,
            bound_at=_iso(_utc_now()),
        )
        data.bindings.append(binding)
        data.revision += 1
        kb_store.save_bindings(data)
        return binding

    def unbind_kb(self, agent_id: str, kb_id: str) -> None:
        normalize_agent_id(agent_id)
        data = kb_store.load_bindings(agent_id)
        before = len(data.bindings)
        data.bindings = [b for b in data.bindings if b.knowledge_base_id != kb_id]
        if len(data.bindings) == before:
            raise KnowledgeBaseServiceError("绑定不存在", 404)
        data.revision += 1
        kb_store.save_bindings(data)

    def update_binding(
        self,
        agent_id: str,
        kb_id: str,
        *,
        enabled_by_default: bool,
        expected_revision: int | None = None,
    ) -> AgentKBBinding:
        normalize_agent_id(agent_id)
        data = kb_store.load_bindings(agent_id)
        if expected_revision is not None and data.revision != expected_revision:
            raise KnowledgeBaseStoreError(
                f"绑定 revision 冲突：期望 {expected_revision}，当前 {data.revision}",
                409,
            )
        for binding in data.bindings:
            if binding.knowledge_base_id == kb_id:
                binding.enabled_by_default = enabled_by_default
                data.revision += 1
                kb_store.save_bindings(data)
                return binding
        raise KnowledgeBaseServiceError("绑定不存在", 404)

    def _remove_bindings(self, agent_id: str, kb_id: str) -> None:
        data = kb_store.load_bindings(agent_id)
        data.bindings = [b for b in data.bindings if b.knowledge_base_id != kb_id]
        kb_store.save_bindings(data)

    def resolve_kb_ids_for_chat(
        self,
        agent_id: str,
        knowledge_base_ids: list[str] | None,
    ) -> list[str]:
        """None = use default bindings; [] = disable KB; explicit list = use those."""
        normalize_agent_id(agent_id)
        if knowledge_base_ids is not None:
            if not knowledge_base_ids:
                return []
            resolved: list[str] = []
            for kb_id in knowledge_base_ids:
                kb = kb_store.load_kb(agent_id, kb_id)
                if kb is None or kb.agent_id != agent_id or kb.status != "active":
                    raise KnowledgeBaseServiceError("知识库不存在", 404)
                resolved.append(kb_id)
            return resolved

        data = kb_store.load_bindings(agent_id)
        ids: list[str] = []
        for binding in data.bindings:
            if not binding.enabled_by_default:
                continue
            kb = kb_store.load_kb(agent_id, binding.knowledge_base_id)
            if kb and kb.status == "active":
                ids.append(binding.knowledge_base_id)
        return ids

    def build_run_snapshot(self, agent_id: str, kb_ids: list[str]) -> dict[str, str]:
        snapshot: dict[str, str] = {}
        for kb_id in kb_ids:
            kb = kb_store.load_kb(agent_id, kb_id)
            if kb is None:
                continue
            for doc in kb_store.list_documents(agent_id, kb_id):
                if doc.status == "ready":
                    snapshot[doc.document_id] = doc.updated_at
        return snapshot


kb_service = KnowledgeBaseService()

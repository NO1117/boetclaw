"""Attachment lifecycle service: upload, parse, delete, retry."""

from __future__ import annotations

import hashlib
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.config import settings
from app.core.observability import EventType, emit_event, get_logger
from app.services.attachments.chunking import build_keyword_index
from app.services.attachments.models import AttachmentRecord, AttachmentTombstone, TextChunk
from app.services.attachments.parsers import parser_registry
from app.services.attachments.security import (
    AttachmentSecurityError,
    infer_kind,
    normalize_agent_id,
    validate_upload_payload,
)
from app.services.attachments.store import attachment_store

logger = get_logger("attachments")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


class AttachmentService:
    def __init__(self) -> None:
        self._parse_tasks: dict[str, asyncio.Task[None]] = {}
        self._cancel_flags: set[str] = set()
        self._lock = threading.RLock()

    def _new_id(self) -> str:
        return uuid.uuid4().hex[:16]

    def _expires_at(self) -> str:
        days = settings.attachment_ttl_days
        return _iso(_utc_now() + timedelta(days=days))

    def get_record(self, agent_id: str, attachment_id: str) -> AttachmentRecord | None:
        normalize_agent_id(agent_id)
        record = attachment_store.load_record(agent_id, attachment_id)
        if record is None or record.status == "deleted":
            return None
        return record

    def list_records(self, agent_id: str) -> list[AttachmentRecord]:
        normalize_agent_id(agent_id)
        return attachment_store.list_records(agent_id)

    async def upload(
        self,
        *,
        agent_id: str,
        filename: str,
        relative_path: str,
        declared_mime: str,
        data: bytes,
    ) -> AttachmentRecord:
        agent_id = normalize_agent_id(agent_id)
        safe_name, safe_path, resolved_mime = validate_upload_payload(
            filename=filename,
            relative_path=relative_path,
            declared_mime=declared_mime,
            size=len(data),
            data=data,
        )
        attachment_id = self._new_id()
        sha256 = hashlib.sha256(data).hexdigest()
        now = _utc_now()
        kind = infer_kind(resolved_mime, safe_name)
        record = AttachmentRecord(
            attachment_id=attachment_id,
            agent_id=agent_id,
            filename=safe_name,
            relative_path=safe_path if safe_path != safe_name else "",
            mime_type=resolved_mime,
            declared_mime=declared_mime,
            size=len(data),
            sha256=sha256,
            kind=kind,  # type: ignore[arg-type]
            status="uploading",
            created_at=_iso(now),
            updated_at=_iso(now),
            expires_at=self._expires_at(),
        )
        attachment_store.save_record(record)
        try:
            attachment_store.write_original(agent_id, attachment_id, data)
        except Exception:
            attachment_store.delete_attachment_files(agent_id, attachment_id)
            raise AttachmentSecurityError("附件存储失败", 500) from None

        record.status = "uploaded"
        attachment_store.save_record(record)
        self._schedule_parse(record)
        return record

    def _schedule_parse(self, record: AttachmentRecord) -> None:
        key = f"{record.agent_id}:{record.attachment_id}"

        with self._lock:
            if key in self._cancel_flags:
                return
            threading.Thread(
                target=self._parse_sync,
                args=(record.agent_id, record.attachment_id),
                daemon=True,
                name=f"parse-{key}",
            ).start()

    def _parse_sync(self, agent_id: str, attachment_id: str) -> None:
        key = f"{agent_id}:{attachment_id}"
        record = attachment_store.load_record(agent_id, attachment_id)
        if record is None or record.status in ("deleted", "ready"):
            return
        if key in self._cancel_flags:
            self._cancel_flags.discard(key)
            return

        record.status = "parsing"
        record.parse_attempts += 1
        attachment_store.save_record(record)

        try:
            data = attachment_store.read_original(agent_id, attachment_id)
            if data is None:
                raise RuntimeError("原始文件不存在")

            if record.kind == "image":
                record.status = "ready"
                record.summary = record.summary.model_copy(update={"searchable": False})
                attachment_store.save_record(record)
                return

            if record.kind == "binary":
                record.status = "ready"
                record.summary = record.summary.model_copy(update={"searchable": False})
                attachment_store.save_record(record)
                return

            parser = parser_registry.get(record.mime_type, record.filename)
            if parser is None:
                raise RuntimeError(f"暂不支持解析此格式: {record.mime_type}")

            result = parser.parse(data, attachment_id=attachment_id, filename=record.filename)
            if len(result.plain_text) > settings.attachment_max_parse_chars:
                raise RuntimeError("文档文本超过解析上限")

            attachment_store.save_chunks(agent_id, attachment_id, result.chunks)
            attachment_store.save_keyword_index(agent_id, attachment_id, build_keyword_index(result.chunks))
            record.summary = result.summary
            record.status = "ready"
            record.error_summary = ""
            attachment_store.save_record(record)
        except Exception as exc:
            logger.warning(
                "attachment_parse_failed",
                attachment_id=attachment_id,
                agent_id=agent_id,
                error_type=type(exc).__name__,
            )
            record = attachment_store.load_record(agent_id, attachment_id)
            if record is None:
                return
            record.status = "failed"
            record.error_summary = self._safe_error_summary(exc)
            attachment_store.save_record(record)

    @staticmethod
    def _safe_error_summary(exc: Exception) -> str:
        message = str(exc).strip()
        if not message:
            return "解析失败"
        if any(token in message.lower() for token in ("\\", "/", "traceback", "line ")):
            return "解析失败"
        return message[:240]

    async def retry_parse(self, agent_id: str, attachment_id: str) -> AttachmentRecord:
        record = self.get_record(agent_id, attachment_id)
        if record is None:
            raise AttachmentSecurityError("附件不存在", 404)
        if record.status not in ("failed", "uploaded"):
            raise AttachmentSecurityError("当前状态不可重试解析")
        record.error_summary = ""
        attachment_store.save_record(record)
        self._schedule_parse(record)
        refreshed = attachment_store.load_record(agent_id, attachment_id)
        return refreshed or record

    async def cancel(self, agent_id: str, attachment_id: str) -> AttachmentRecord:
        record = self.get_record(agent_id, attachment_id)
        if record is None:
            raise AttachmentSecurityError("附件不存在", 404)
        key = f"{agent_id}:{attachment_id}"
        self._cancel_flags.add(key)
        task = self._parse_tasks.get(key)
        if task and not task.done():
            task.cancel()
        if record.status in ("uploading", "uploaded", "parsing", "failed"):
            return await self.delete(agent_id, attachment_id, reason="cancelled")
        return record

    async def delete(
        self,
        agent_id: str,
        attachment_id: str,
        *,
        reason: str = "user_delete",
        trace_id: str = "",
    ) -> AttachmentRecord:
        record = attachment_store.load_record(agent_id, attachment_id)
        if record is None or record.status == "deleted":
            raise AttachmentSecurityError("附件不存在", 404)

        tombstone = AttachmentTombstone(
            attachment_id=attachment_id,
            agent_id=agent_id,
            filename=record.filename,
            sha256=record.sha256,
            deleted_at=_iso(_utc_now()),
            reason=reason,
        )
        attachment_store.append_tombstone(agent_id, tombstone)
        attachment_store.delete_attachment_files(agent_id, attachment_id)

        deleted = record.model_copy(update={"status": "deleted", "deleted_at": tombstone.deleted_at})
        attachment_store.save_record(deleted)

        if trace_id:
            emit_event(
                EventType.MEMORY_PERSIST,
                {
                    "action": "attachment_delete",
                    "attachment_id": attachment_id,
                    "agent_id": agent_id,
                    "reason": reason,
                },
                trace_id=trace_id,
                run_id="",
            )
        return deleted

    def get_content(self, agent_id: str, attachment_id: str) -> dict[str, Any]:
        record = self.get_record(agent_id, attachment_id)
        if record is None:
            raise AttachmentSecurityError("附件不存在", 404)
        chunks = attachment_store.load_chunks(agent_id, attachment_id)
        return {
            "attachment": record.to_public_dict(),
            "chunks": [c.model_dump() for c in chunks],
        }

    def wait_until_ready(self, agent_id: str, attachment_id: str, timeout: float = 30.0) -> AttachmentRecord:
        import time

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            record = self.get_record(agent_id, attachment_id)
            if record is None:
                raise AttachmentSecurityError("附件不存在", 404)
            if record.status in ("ready", "failed"):
                return record
            time.sleep(0.05)
        record = self.get_record(agent_id, attachment_id)
        if record is None:
            raise AttachmentSecurityError("附件不存在", 404)
        return record

    def read_image_base64(self, agent_id: str, attachment_id: str) -> tuple[str, str]:
        import base64

        record = self.get_record(agent_id, attachment_id)
        if record is None:
            raise AttachmentSecurityError("附件不存在", 404)
        if record.kind != "image":
            raise AttachmentSecurityError("附件不是图像")
        if record.status != "ready":
            raise AttachmentSecurityError("图像附件尚未就绪")
        data = attachment_store.read_original(agent_id, attachment_id)
        if data is None:
            raise AttachmentSecurityError("图像数据不存在", 404)
        mime = record.mime_type if record.mime_type.startswith("image/") else "image/png"
        return mime, base64.b64encode(data).decode("ascii")


attachment_service = AttachmentService()

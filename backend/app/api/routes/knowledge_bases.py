"""Knowledge base REST routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.services.attachments.security import AttachmentSecurityError
from app.services.chat_attachments import MAX_FILE_BYTES
from app.services.knowledge_base.service import KnowledgeBaseServiceError, kb_service
from app.services.knowledge_base.store import KnowledgeBaseStoreError

router = APIRouter(prefix="/agents", tags=["KnowledgeBase"])

_READ_CHUNK_SIZE = 64 * 1024


class CreateKBRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str = Field("", max_length=2000)


class UpdateKBRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=128)
    description: str | None = Field(None, max_length=2000)
    expected_revision: int | None = None


class AddFromAttachmentsRequest(BaseModel):
    attachment_ids: list[str] = Field(..., min_length=1)


class BindKBRequest(BaseModel):
    enabled_by_default: bool = True


class UpdateBindingRequest(BaseModel):
    enabled_by_default: bool
    expected_revision: int | None = None


async def _read_upload_bounded(file: UploadFile, *, max_bytes: int = MAX_FILE_BYTES) -> bytes:
    chunks: list[bytes] = []
    total = 0
    try:
        while True:
            chunk = await file.read(_READ_CHUNK_SIZE)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise AttachmentSecurityError("单个文件超过 25 MB 限制")
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        await file.close()


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, (KnowledgeBaseServiceError, KnowledgeBaseStoreError, AttachmentSecurityError)):
        return HTTPException(status_code=exc.status_code, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


@router.post("/{agent_id}/knowledge-bases")
async def create_knowledge_base(agent_id: str, body: CreateKBRequest):
    try:
        kb = kb_service.create_kb(agent_id, name=body.name, description=body.description)
        return kb.to_public_dict()
    except KnowledgeBaseServiceError as exc:
        raise _http_error(exc) from exc


@router.get("/{agent_id}/knowledge-bases")
async def list_knowledge_bases(agent_id: str, status: str = "", q: str = ""):
    try:
        rows = kb_service.list_kbs(agent_id, status=status or None, q=q)
        return {"knowledge_bases": [r.to_public_dict() for r in rows]}
    except KnowledgeBaseServiceError as exc:
        raise _http_error(exc) from exc


@router.get("/{agent_id}/knowledge-bases/{kb_id}")
async def get_knowledge_base(agent_id: str, kb_id: str):
    try:
        kb = kb_service.get_kb(agent_id, kb_id)
        return kb.to_public_dict()
    except KnowledgeBaseServiceError as exc:
        raise _http_error(exc) from exc


@router.patch("/{agent_id}/knowledge-bases/{kb_id}")
async def update_knowledge_base(agent_id: str, kb_id: str, body: UpdateKBRequest):
    try:
        kb = kb_service.update_kb(
            agent_id,
            kb_id,
            name=body.name,
            description=body.description,
            expected_revision=body.expected_revision,
        )
        return kb.to_public_dict()
    except (KnowledgeBaseServiceError, KnowledgeBaseStoreError) as exc:
        raise _http_error(exc) from exc


@router.post("/{agent_id}/knowledge-bases/{kb_id}/archive")
async def archive_knowledge_base(agent_id: str, kb_id: str):
    try:
        kb = kb_service.archive_kb(agent_id, kb_id)
        return kb.to_public_dict()
    except KnowledgeBaseServiceError as exc:
        raise _http_error(exc) from exc


@router.post("/{agent_id}/knowledge-bases/{kb_id}/restore")
async def restore_knowledge_base(agent_id: str, kb_id: str):
    try:
        kb = kb_service.restore_kb(agent_id, kb_id)
        return kb.to_public_dict()
    except KnowledgeBaseServiceError as exc:
        raise _http_error(exc) from exc


@router.delete("/{agent_id}/knowledge-bases/{kb_id}")
async def delete_knowledge_base(agent_id: str, kb_id: str):
    try:
        kb = kb_service.delete_kb(agent_id, kb_id)
        return {"deleted": True, "knowledge_base_id": kb.knowledge_base_id}
    except KnowledgeBaseServiceError as exc:
        raise _http_error(exc) from exc


@router.post("/{agent_id}/knowledge-bases/{kb_id}/purge")
async def purge_knowledge_base(agent_id: str, kb_id: str):
    try:
        return kb_service.purge_kb(agent_id, kb_id)
    except KnowledgeBaseServiceError as exc:
        raise _http_error(exc) from exc


@router.get("/{agent_id}/knowledge-bases/{kb_id}/documents")
async def list_kb_documents(agent_id: str, kb_id: str):
    try:
        docs = kb_service.list_documents(agent_id, kb_id)
        return {"documents": [d.to_public_dict() for d in docs]}
    except KnowledgeBaseServiceError as exc:
        raise _http_error(exc) from exc


@router.get("/{agent_id}/knowledge-bases/{kb_id}/documents/{doc_id}")
async def get_kb_document(agent_id: str, kb_id: str, doc_id: str):
    try:
        doc = kb_service.get_document(agent_id, kb_id, doc_id)
        return doc.to_public_dict()
    except KnowledgeBaseServiceError as exc:
        raise _http_error(exc) from exc


@router.post("/{agent_id}/knowledge-bases/{kb_id}/documents/upload")
async def upload_kb_documents(
    agent_id: str,
    kb_id: str,
    files: list[UploadFile] = File(...),
    relative_paths: list[str] = Form(default=[]),
):
    try:
        batch: list[tuple[str, str, str, bytes]] = []
        for index, file in enumerate(files):
            data = await _read_upload_bounded(file)
            rel = relative_paths[index] if index < len(relative_paths) else ""
            batch.append(
                (
                    file.filename or "upload.bin",
                    rel,
                    file.content_type or "application/octet-stream",
                    data,
                )
            )
        records = await kb_service.upload_documents(agent_id, kb_id, files=batch)
        return {"documents": [r.to_public_dict() for r in records]}
    except (KnowledgeBaseServiceError, AttachmentSecurityError) as exc:
        raise _http_error(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="上传失败") from exc


@router.post("/{agent_id}/knowledge-bases/{kb_id}/documents/from-attachments")
async def add_kb_documents_from_attachments(agent_id: str, kb_id: str, body: AddFromAttachmentsRequest):
    try:
        records = await kb_service.add_from_attachments(agent_id, kb_id, body.attachment_ids)
        return {"documents": [r.to_public_dict() for r in records]}
    except KnowledgeBaseServiceError as exc:
        raise _http_error(exc) from exc


@router.post("/{agent_id}/knowledge-bases/{kb_id}/documents/{doc_id}/retry")
async def retry_kb_document(agent_id: str, kb_id: str, doc_id: str):
    try:
        doc = await kb_service.retry_document(agent_id, kb_id, doc_id)
        return doc.to_public_dict()
    except KnowledgeBaseServiceError as exc:
        raise _http_error(exc) from exc


@router.delete("/{agent_id}/knowledge-bases/{kb_id}/documents/{doc_id}")
async def remove_kb_document(agent_id: str, kb_id: str, doc_id: str):
    try:
        doc = await kb_service.remove_document(agent_id, kb_id, doc_id)
        return {"removed": True, "document_id": doc.document_id}
    except KnowledgeBaseServiceError as exc:
        raise _http_error(exc) from exc


@router.get("/{agent_id}/knowledge-bases/{kb_id}/documents/{doc_id}/preview")
async def preview_kb_snippet(agent_id: str, kb_id: str, doc_id: str, chunk_id: str):
    try:
        return kb_service.get_snippet_preview(agent_id, kb_id, doc_id, chunk_id)
    except KnowledgeBaseServiceError as exc:
        raise _http_error(exc) from exc


@router.get("/{agent_id}/knowledge-base-bindings")
async def list_kb_bindings(agent_id: str):
    try:
        bindings = kb_service.list_bindings(agent_id)
        return {
            "bindings": [b.model_dump() for b in bindings],
        }
    except KnowledgeBaseServiceError as exc:
        raise _http_error(exc) from exc


@router.post("/{agent_id}/knowledge-base-bindings/{kb_id}")
async def bind_knowledge_base(agent_id: str, kb_id: str, body: BindKBRequest):
    try:
        binding = kb_service.bind_kb(agent_id, kb_id, enabled_by_default=body.enabled_by_default)
        return binding.model_dump()
    except KnowledgeBaseServiceError as exc:
        raise _http_error(exc) from exc


@router.delete("/{agent_id}/knowledge-base-bindings/{kb_id}")
async def unbind_knowledge_base(agent_id: str, kb_id: str):
    try:
        kb_service.unbind_kb(agent_id, kb_id)
        return {"unbound": True, "knowledge_base_id": kb_id}
    except KnowledgeBaseServiceError as exc:
        raise _http_error(exc) from exc


@router.patch("/{agent_id}/knowledge-base-bindings/{kb_id}")
async def update_kb_binding(agent_id: str, kb_id: str, body: UpdateBindingRequest):
    try:
        binding = kb_service.update_binding(
            agent_id,
            kb_id,
            enabled_by_default=body.enabled_by_default,
            expected_revision=body.expected_revision,
        )
        return binding.model_dump()
    except (KnowledgeBaseServiceError, KnowledgeBaseStoreError) as exc:
        raise _http_error(exc) from exc

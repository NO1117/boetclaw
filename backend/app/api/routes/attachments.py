"""Attachment upload, query, delete, and retry routes."""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.services.attachments.security import AttachmentSecurityError
from app.services.attachments.service import attachment_service
from app.services.chat_attachments import MAX_FILE_BYTES

router = APIRouter(prefix="/agents", tags=["Attachments"])

_READ_CHUNK_SIZE = 64 * 1024


async def _read_upload_bounded(file: UploadFile, *, max_bytes: int = MAX_FILE_BYTES) -> bytes:
    """Read upload body in chunks; abort before buffering more than max_bytes."""
    chunks: list[bytes] = []
    total = 0
    try:
        while True:
            chunk = await file.read(_READ_CHUNK_SIZE)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise AttachmentSecurityError("单个附件超过 25 MB 限制")
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        await file.close()


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, AttachmentSecurityError):
        return HTTPException(status_code=exc.status_code, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


@router.post("/{agent_id}/attachments")
async def upload_attachment(
    agent_id: str,
    file: UploadFile = File(...),
    relative_path: str = Form(""),
):
    try:
        data = await _read_upload_bounded(file)
        record = await attachment_service.upload(
            agent_id=agent_id,
            filename=file.filename or "upload.bin",
            relative_path=relative_path,
            declared_mime=file.content_type or "application/octet-stream",
            data=data,
        )
        return record.to_public_dict()
    except AttachmentSecurityError as exc:
        raise _http_error(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="上传失败") from exc


@router.get("/{agent_id}/attachments")
async def list_attachments(agent_id: str):
    try:
        rows = attachment_service.list_records(agent_id)
        return {"attachments": [row.to_public_dict() for row in rows]}
    except AttachmentSecurityError as exc:
        raise _http_error(exc) from exc


@router.get("/{agent_id}/attachments/{attachment_id}")
async def get_attachment(agent_id: str, attachment_id: str):
    record = attachment_service.get_record(agent_id, attachment_id)
    if record is None:
        raise HTTPException(status_code=404, detail="附件不存在")
    return record.to_public_dict()


@router.get("/{agent_id}/attachments/{attachment_id}/content")
async def get_attachment_content(agent_id: str, attachment_id: str):
    try:
        return attachment_service.get_content(agent_id, attachment_id)
    except AttachmentSecurityError as exc:
        raise _http_error(exc) from exc


@router.post("/{agent_id}/attachments/{attachment_id}/retry")
async def retry_attachment(agent_id: str, attachment_id: str):
    try:
        record = await attachment_service.retry_parse(agent_id, attachment_id)
        return record.to_public_dict()
    except AttachmentSecurityError as exc:
        raise _http_error(exc) from exc


@router.post("/{agent_id}/attachments/{attachment_id}/cancel")
async def cancel_attachment(agent_id: str, attachment_id: str):
    try:
        record = await attachment_service.cancel(agent_id, attachment_id)
        return record.to_public_dict()
    except AttachmentSecurityError as exc:
        raise _http_error(exc) from exc


@router.delete("/{agent_id}/attachments/{attachment_id}")
async def delete_attachment(agent_id: str, attachment_id: str):
    try:
        record = await attachment_service.delete(agent_id, attachment_id)
        return {"deleted": True, "attachment_id": record.attachment_id}
    except AttachmentSecurityError as exc:
        raise _http_error(exc) from exc

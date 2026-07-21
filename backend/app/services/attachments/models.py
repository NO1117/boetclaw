"""Attachment domain models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

AttachmentStatus = Literal[
    "uploading",
    "uploaded",
    "parsing",
    "ready",
    "failed",
    "expired",
    "deleted",
]
ScanStatus = Literal["unscanned", "clean", "infected", "error"]
AttachmentKind = Literal["text", "image", "document", "binary"]


class ChunkLocation(BaseModel):
    page: int | None = None
    sheet: str | None = None
    slide: int | None = None
    section: str | None = None
    row: int | None = None
    col: int | None = None


class TextChunk(BaseModel):
    chunk_id: str
    attachment_id: str
    order: int
    text: str
    location: ChunkLocation = Field(default_factory=ChunkLocation)
    token_estimate: int = 0


class DocumentSummary(BaseModel):
    page_count: int | None = None
    sheet_count: int | None = None
    slide_count: int | None = None
    paragraph_count: int | None = None
    chunk_count: int = 0
    char_count: int = 0
    searchable: bool = False


class AttachmentRecord(BaseModel):
    attachment_id: str
    agent_id: str
    filename: str
    relative_path: str = ""
    mime_type: str
    declared_mime: str = ""
    size: int
    sha256: str
    kind: AttachmentKind = "binary"
    status: AttachmentStatus = "uploading"
    scan_status: ScanStatus = "unscanned"
    error_summary: str = ""
    summary: DocumentSummary = Field(default_factory=DocumentSummary)
    created_at: str
    updated_at: str
    expires_at: str = ""
    deleted_at: str = ""
    parse_attempts: int = 0

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "attachment_id": self.attachment_id,
            "agent_id": self.agent_id,
            "filename": self.filename,
            "relative_path": self.relative_path,
            "mime_type": self.mime_type,
            "size": self.size,
            "kind": self.kind,
            "status": self.status,
            "scan_status": self.scan_status,
            "error_summary": self.error_summary,
            "summary": self.summary.model_dump(),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "expires_at": self.expires_at,
        }


class AttachmentTombstone(BaseModel):
    attachment_id: str
    agent_id: str
    filename: str
    sha256: str
    deleted_at: str
    reason: str = "user_delete"

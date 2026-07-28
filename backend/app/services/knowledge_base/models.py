"""Knowledge base domain models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.services.attachments.models import DocumentSummary, ScanStatus

CURRENT_SCHEMA_VERSION = 1

KnowledgeBaseStatus = Literal["active", "archived", "deleted"]
KBDocumentStatus = Literal["uploading", "uploaded", "parsing", "ready", "failed", "removed"]


class KnowledgeBaseRecord(BaseModel):
    schema_version: int = CURRENT_SCHEMA_VERSION
    knowledge_base_id: str
    agent_id: str
    name: str
    description: str = ""
    status: KnowledgeBaseStatus = "active"
    document_count: int = 0
    total_size: int = 0
    revision: int = 1
    created_at: str
    updated_at: str
    deleted_at: str = ""

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "knowledge_base_id": self.knowledge_base_id,
            "agent_id": self.agent_id,
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "document_count": self.document_count,
            "total_size": self.total_size,
            "revision": self.revision,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class KBDocumentRecord(BaseModel):
    document_id: str
    knowledge_base_id: str
    agent_id: str
    filename: str
    relative_path: str = ""
    mime_type: str
    size: int
    sha256: str
    kind: Literal["text", "image", "document", "binary"] = "document"
    status: KBDocumentStatus = "uploading"
    scan_status: ScanStatus = "unscanned"
    error_summary: str = ""
    summary: DocumentSummary = Field(default_factory=DocumentSummary)
    source_attachment_id: str = ""
    parse_attempts: int = 0
    created_at: str
    updated_at: str
    removed_at: str = ""

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "knowledge_base_id": self.knowledge_base_id,
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
            "source_attachment_id": self.source_attachment_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class AgentKBBinding(BaseModel):
    knowledge_base_id: str
    enabled_by_default: bool = True
    bound_at: str


class AgentKBBindingsFile(BaseModel):
    schema_version: int = CURRENT_SCHEMA_VERSION
    agent_id: str
    bindings: list[AgentKBBinding] = Field(default_factory=list)
    revision: int = 1
    updated_at: str = ""


class KnowledgeCitation(BaseModel):
    knowledge_base_id: str
    knowledge_base_name: str
    document_id: str
    document_name: str
    chunk_id: str
    location: dict[str, Any] = Field(default_factory=dict)
    score: float = 0.0
    truncated: bool = False
    snippet: str = ""


class KBRunSnapshot(BaseModel):
    """Frozen KB state at chat run start."""

    knowledge_base_ids: list[str]
    documents: dict[str, str] = Field(default_factory=dict)  # doc_id -> updated_at

"""Persistent user memory domain models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

MemoryScope = Literal["agent", "thread"]
MemoryStatus = Literal["active", "pending", "rejected", "deleted"]
MemorySourceType = Literal["user_explicit", "user_chat", "manual"]
MemoryAutoMode = Literal["off", "review", "auto"]


class MemoryRecord(BaseModel):
    id: str
    agent_id: str
    scope: MemoryScope
    thread_id: str = ""
    content: str
    summary: str
    tags: list[str] = Field(default_factory=list)
    source_type: MemorySourceType = "user_chat"
    source_thread: str = ""
    source_trace: str = ""
    status: MemoryStatus = "active"
    created_at: str
    updated_at: str
    last_used_at: str = ""
    use_count: int = 0

    def to_public_dict(self, *, include_content: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "agent_id": self.agent_id,
            "scope": self.scope,
            "thread_id": self.thread_id,
            "summary": self.summary,
            "tags": self.tags,
            "source_type": self.source_type,
            "source_thread": self.source_thread,
            "source_trace": self.source_trace,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_used_at": self.last_used_at,
            "use_count": self.use_count,
        }
        if include_content:
            payload["content"] = self.content
        return payload


class MemorySearchFilters(BaseModel):
    q: str = ""
    scope: str = ""
    status: str = ""
    thread_id: str = ""
    tag: str = ""


class MemoryInjectionItem(BaseModel):
    id: str
    scope: MemoryScope
    summary: str
    content: str


class MemoryContextSummary(BaseModel):
    mode: MemoryAutoMode = "review"
    backend: str = "sqlite"
    persistent: bool = True
    saved_count: int = 0
    used_count: int = 0
    pending_count: int = 0
    injected_chars: int = 0
    items: list[dict[str, Any]] = Field(default_factory=list)


class MemoryCandidatePublic(BaseModel):
    id: str
    summary: str
    content: str
    scope: MemoryScope
    source_type: MemorySourceType = "user_chat"
    source_thread: str = ""
    source_trace: str = ""


class MemoryActionResult(BaseModel):
    action: Literal["remember", "forget", "reject_sensitive", "duplicate"]
    success: bool
    memory_id: str = ""
    message: str = ""

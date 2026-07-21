"""Pydantic schemas for API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.core.execution_ref import ExecutionRef


class ChatAttachment(BaseModel):
    filename: str = Field(..., min_length=1, max_length=512)
    relative_path: str = Field("", max_length=2048)
    mime_type: str = Field("application/octet-stream", max_length=256)
    size: int = Field(..., ge=0)
    kind: Literal["text", "image", "binary"] = "binary"
    content_base64: str = Field("", max_length=35_000_000)


class ChatRequest(BaseModel):
    message: str = Field("", description="User message")
    attachments: list[ChatAttachment] = Field(default_factory=list)
    attachment_ids: list[str] = Field(default_factory=list, description="Uploaded attachment IDs")
    thread_id: str | None = Field(None, description="Conversation thread ID")
    agent_id: str | None = Field(None, description="Target agent workspace id")
    source: str = Field("user", description="Request source: user|channel|cron|heartbeat")
    lang: str | None = Field(None, description="Response language override, e.g. zh or en")
    provider: str | None = Field(None, description="Per-request provider override")
    model: str | None = Field(None, description="Per-request model override")

    @model_validator(mode="after")
    def require_message_or_attachments(self) -> "ChatRequest":
        has_inline = bool(self.attachments)
        has_ids = bool(self.attachment_ids)
        if not self.message.strip() and not has_inline and not has_ids:
            raise ValueError("message、attachments 或 attachment_ids 至少提供一个")
        if has_inline and has_ids:
            raise ValueError("attachments 与 attachment_ids 不能同时使用")
        if (self.provider is None) ^ (self.model is None):
            if self.provider or self.model:
                raise ValueError("provider 与 model 必须同时提供")
        return self


class ChatResponse(BaseModel):
    thread_id: str
    trace_id: str
    run_id: str
    response: str
    todos: list[Any] = []
    message_count: int = 0
    interrupted: bool = False
    agent_id: str = "default"
    execution_ref: ExecutionRef | None = None
    payload: Any = None


class RunCancelRequest(BaseModel):
    agent_id: str = Field(..., min_length=1)
    thread_id: str = Field(..., min_length=1)
    run_id: str = ""


class RunCancelResponse(BaseModel):
    cancelled: bool
    status: str
    agent_id: str
    thread_id: str
    run_id: str
    detail: str


class PlanConfirmRequest(BaseModel):
    execution_ref: ExecutionRef | None = None
    thread_id: str | None = Field(None, min_length=1)
    decision: Literal["approve", "reject", "edit"] = "approve"
    edited_todos: list[Any] | None = None

    @model_validator(mode="after")
    def require_ref_or_thread(self) -> "PlanConfirmRequest":
        if self.execution_ref is None and not self.thread_id:
            raise ValueError("execution_ref 或兼容 thread_id 至少提供一个")
        return self


class PlanConfirmResponse(BaseModel):
    execution_ref: ExecutionRef
    agent_id: str
    thread_id: str
    interrupt_id: str
    resumed: bool
    decision: Literal["approve", "reject", "edit"]
    edited_todos: list[Any] = []
    response: str = ""
    message_count: int = 0


class ApprovalResumeRequest(BaseModel):
    approval_id: str = Field(..., min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    execution_ref: ExecutionRef | None = None
    thread_id: str | None = Field(None, min_length=1)
    decision: Literal["approve", "reject"] = "approve"

    @model_validator(mode="after")
    def require_ref_or_thread(self) -> "ApprovalResumeRequest":
        if self.execution_ref is None and not self.thread_id:
            raise ValueError("execution_ref 或兼容 thread_id 至少提供一个")
        return self


class TaskCreateRequest(BaseModel):
    title: str = Field(..., min_length=1)
    prompt: str = Field(..., min_length=1)
    auto_run: bool = True
    gateway: str = ""
    gateway_user: str = ""
    metadata: dict[str, Any] = {}


class TaskResponse(BaseModel):
    id: str
    title: str
    prompt: str
    status: str
    thread_id: str
    trace_id: str = ""
    run_id: str = ""
    result: str = ""
    error: str = ""
    gateway: str = ""
    created_at: str
    updated_at: str


class ToolInfo(BaseModel):
    name: str
    description: str
    source: str


class TraceEventResponse(BaseModel):
    id: str
    trace_id: str
    run_id: str
    event_type: str
    timestamp: str
    data: dict[str, Any]


class GatewayWebhookResponse(BaseModel):
    success: bool
    task_id: str = ""
    message: str = ""
    signature: str = ""  # verified | skipped


class CronJobCreateRequest(BaseModel):
    name: str
    cron: str = Field(..., description="Crontab expression, e.g. '*/5 * * * *'")
    prompt: str
    channel: str = ""
    chat_id: str = ""
    agent_id: str = "default"
    enabled: bool = True


class HeartbeatUpdateRequest(BaseModel):
    enabled: bool | None = None
    interval_minutes: int | None = None
    prompt: str | None = None

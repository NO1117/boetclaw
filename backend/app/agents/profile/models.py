"""Structured AgentProfile schema and effective config resolution."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.config import settings

CURRENT_SCHEMA_VERSION = 1
MAX_SYSTEM_PROMPT_CHARS = 32_000
MAX_DISPLAY_NAME_CHARS = 128
MAX_DESCRIPTION_CHARS = 2_000

ToolPolicy = Literal["inherit", "safe_only", "allowlist"]
MemoryMode = Literal["inherit", "off", "review", "auto"]

EDITABLE_FIELDS = frozenset(
    {
        "display_name",
        "description",
        "avatar_color",
        "system_prompt",
        "provider",
        "model",
        "temperature",
        "max_output_tokens",
        "tool_policy",
        "tool_allowlist",
        "memory_mode",
        "default_language",
        "enabled",
    }
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = CURRENT_SCHEMA_VERSION
    agent_id: str
    display_name: str = ""
    description: str = ""
    avatar_color: str = "#6366f1"
    system_prompt: str = ""
    provider: str = ""
    model: str = ""
    temperature: float | None = None
    max_output_tokens: int | None = None
    tool_policy: ToolPolicy = "inherit"
    tool_allowlist: list[str] = Field(default_factory=list)
    memory_mode: MemoryMode = "inherit"
    default_language: str = "zh"
    enabled: bool = True
    revision: int = 1
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)

    @field_validator("agent_id")
    @classmethod
    def validate_agent_id(cls, value: str) -> str:
        from app.agents.profile.security import validate_agent_id

        return validate_agent_id(value)

    @classmethod
    def default_for(cls, agent_id: str) -> AgentProfile:
        display = "默认智能体" if agent_id == settings.default_agent_id else agent_id
        return cls(agent_id=agent_id, display_name=display)

    def editable_dict(self) -> dict[str, Any]:
        return {field: getattr(self, field) for field in sorted(EDITABLE_FIELDS)}

    def to_public_dict(self) -> dict[str, Any]:
        data = self.model_dump()
        data.pop("schema_version", None)
        return data

    def to_disk_dict(self) -> dict[str, Any]:
        return self.model_dump()


class EffectiveAgentConfig(BaseModel):
    provider: str
    model: str
    model_string: str
    temperature: float | None = None
    max_output_tokens: int | None = None
    tool_policy: ToolPolicy
    tool_allowlist: list[str]
    memory_mode: MemoryMode
    default_language: str
    enabled: bool
    system_prompt: str
    revision: int


class ApplyState(BaseModel):
    revision: int
    status: Literal["applied", "failed", "pending"] = "pending"
    applied_at: str = ""
    error_summary: str = ""


class ProfileVersionRecord(BaseModel):
    revision: int
    created_at: str
    changed_fields: list[str] = Field(default_factory=list)
    operator: str = "system"
    snapshot: dict[str, Any] = Field(default_factory=dict)


class ProfileValidationResult(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ProfileResponse(BaseModel):
    agent_id: str
    configured: dict[str, Any]
    effective: dict[str, Any]
    revision: int
    apply_state: dict[str, Any]

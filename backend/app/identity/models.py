"""Identity domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def utc_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


@dataclass
class UserRecord:
    id: str
    username: str
    username_normalized: str
    display_name: str
    status: str  # active | disabled | deleted
    role: str
    password_hash: str
    token_version: int = 1
    created_at: str = ""
    updated_at: str = ""
    last_login_at: str = ""
    deleted_at: str = ""

    def to_public_dict(self, *, permissions: list[str] | None = None) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "username": self.username,
            "display_name": self.display_name,
            "status": self.status,
            "role": self.role,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_login_at": self.last_login_at or None,
        }
        if permissions is not None:
            data["permissions"] = sorted(permissions)
        return data


@dataclass
class SessionRecord:
    id: str
    user_id: str
    token_version: int
    csrf_token: str
    created_at: str
    expires_at: str
    revoked_at: str = ""
    last_seen_at: str = ""
    ip: str = ""
    user_agent: str = ""


@dataclass
class ResourceAcl:
    resource_type: str
    resource_id: str
    owner_user_id: str
    visibility: str  # private | workspace
    created_at: str = ""
    updated_at: str = ""
    grants: list[dict[str, str]] = field(default_factory=list)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "owner_user_id": self.owner_user_id,
            "visibility": self.visibility,
            "grants": list(self.grants),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class AuditRecord:
    id: str
    actor_id: str
    actor_type: str  # user | api_token | console_legacy | system | open
    action: str
    resource_type: str
    resource_id: str
    result: str  # success | denied | error
    request_id: str = ""
    source: str = ""
    detail: str = ""
    created_at: str = ""

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "actor_id": self.actor_id,
            "actor_type": self.actor_type,
            "action": self.action,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "result": self.result,
            "request_id": self.request_id,
            "source": self.source,
            "detail": self.detail,
            "created_at": self.created_at,
        }

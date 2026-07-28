"""Request actor context — never trust client-supplied user IDs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException, Request

from app.identity.permissions import has_permission, permissions_for_role


@dataclass
class Actor:
    """Authenticated principal attached to the request by middleware."""

    actor_type: str  # user | api_token | console_legacy | open
    user_id: str = ""
    username: str = ""
    display_name: str = ""
    role: str = ""
    session_id: str = ""
    token_version: int = 0
    permissions: frozenset[str] = field(default_factory=frozenset)
    auth_via: str = ""  # cookie | bearer | api_token | open
    csrf_token: str = ""

    @property
    def is_authenticated(self) -> bool:
        return self.actor_type != ""

    @property
    def is_open(self) -> bool:
        return self.actor_type == "open"

    @property
    def is_user(self) -> bool:
        return self.actor_type == "user"

    @property
    def is_admin_like(self) -> bool:
        return self.role in {"owner", "admin"} or self.actor_type == "api_token"

    def has(self, permission: str) -> bool:
        if self.actor_type == "open":
            return True
        if self.actor_type == "api_token":
            # Legacy service principal: admin-level, no owner management / credential plaintext.
            from app.identity.permissions import (
                PROVIDERS_CREDENTIALS,
                USERS_MANAGE_OWNERS,
                permissions_for_role,
            )

            perms = permissions_for_role("admin") - {USERS_MANAGE_OWNERS, PROVIDERS_CREDENTIALS}
            return permission in perms
        if self.actor_type == "console_legacy":
            return has_permission("owner", permission)
        return permission in self.permissions

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "actor_type": self.actor_type,
            "id": self.user_id or None,
            "username": self.username or None,
            "display_name": self.display_name or None,
            "role": self.role or None,
            "permissions": sorted(self.permissions) if self.permissions else sorted(
                p for p in (
                    permissions_for_role(self.role) if self.role else frozenset()
                )
            ),
            "auth_via": self.auth_via,
            "open_mode": self.actor_type == "open",
        }


def get_actor(request: Request | None) -> Actor | None:
    if request is None:
        return Actor(
            actor_type="open",
            user_id="open",
            username="open",
            display_name="Open Mode",
            role="owner",
            permissions=permissions_for_role("owner"),
            auth_via="open",
        )
    actor = getattr(request.state, "actor", None)
    if actor is not None:
        return actor
    from app.identity.resolve import resolve_request_actor

    actor = resolve_request_actor(request)
    request.state.actor = actor
    return actor


def require_actor(request: Request | None) -> Actor:
    actor = get_actor(request)
    if actor is None or not actor.is_authenticated:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return actor


def require_permission(request: Request | None, permission: str) -> Actor:
    actor = require_actor(request)
    if not actor.has(permission):
        raise HTTPException(status_code=403, detail="Forbidden")
    return actor

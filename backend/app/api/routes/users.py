"""User management, resource ACL, and audit query routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.identity.actor import require_actor, require_permission
from app.identity.permissions import (
    AGENTS_ADMIN,
    AUDIT_READ,
    AUDIT_READ_OWN,
    KB_ADMIN,
    SESSIONS_MANAGE,
    USERS_READ,
    USERS_WRITE,
)
from app.identity.resource_acl import require_agent_access, require_kb_access
from app.identity.service import identity_service

users_router = APIRouter(prefix="/users", tags=["users"])
acl_router = APIRouter(prefix="/acl", tags=["acl"])
audit_router = APIRouter(prefix="/audit", tags=["audit"])


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=64)
    password: str = Field(..., min_length=8)
    display_name: str = ""
    role: str = "operator"


class UpdateUserRequest(BaseModel):
    display_name: str | None = None
    role: str | None = None
    status: str | None = None


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=8)


class VisibilityRequest(BaseModel):
    visibility: str = Field(..., pattern="^(private|workspace)$")


class GrantRequest(BaseModel):
    user_id: str
    level: str = Field(..., pattern="^(viewer|editor|runner)$")


@users_router.get("")
async def list_users(request: Request):
    require_permission(request, USERS_READ)
    return {"users": identity_service.list_users_public()}


@users_router.post("")
async def create_user(body: CreateUserRequest, request: Request):
    actor = require_permission(request, USERS_WRITE)
    user = identity_service.create_user(
        username=body.username,
        password=body.password,
        display_name=body.display_name,
        role=body.role,
        actor_role=actor.role if actor.is_user else "owner",
        actor_id=actor.user_id,
    )
    return user.to_public_dict()


@users_router.get("/{user_id}")
async def get_user(user_id: str, request: Request):
    require_permission(request, USERS_READ)
    public = identity_service.get_user_public(user_id)
    if public is None:
        raise HTTPException(status_code=404, detail="Not found")
    return public


@users_router.patch("/{user_id}")
async def update_user(user_id: str, body: UpdateUserRequest, request: Request):
    actor = require_permission(request, USERS_WRITE)
    user = identity_service.update_user(
        user_id,
        actor_role=actor.role if actor.is_user else "owner",
        actor_id=actor.user_id,
        display_name=body.display_name,
        role=body.role,
        status=body.status,
    )
    return user.to_public_dict()


@users_router.delete("/{user_id}")
async def delete_user(user_id: str, request: Request):
    actor = require_permission(request, USERS_WRITE)
    identity_service.delete_user(
        user_id,
        actor_role=actor.role if actor.is_user else "owner",
        actor_id=actor.user_id,
    )
    return {"ok": True}


@users_router.post("/{user_id}/reset-password")
async def reset_password(user_id: str, body: ResetPasswordRequest, request: Request):
    actor = require_permission(request, USERS_WRITE)
    identity_service.reset_password(
        user_id,
        body.new_password,
        actor_role=actor.role if actor.is_user else "owner",
        actor_id=actor.user_id,
    )
    return {"ok": True}


@users_router.post("/{user_id}/revoke-sessions")
async def revoke_user_sessions(user_id: str, request: Request):
    actor = require_permission(request, SESSIONS_MANAGE)
    target = identity_service.store.get_user(user_id)
    if target is None or target.status == "deleted":
        raise HTTPException(status_code=404, detail="Not found")
    if target.role == "owner" and actor.role != "owner" and actor.is_user:
        raise HTTPException(status_code=403, detail="Forbidden")
    count = identity_service.revoke_all_sessions(user_id, bump_version=True)
    return {"ok": True, "revoked": count}


# ── ACL ────────────────────────────────────────────────────────────────


@acl_router.get("/agents/{agent_id}")
async def get_agent_acl(agent_id: str, request: Request):
    actor = require_agent_access(request, agent_id, required="viewer")
    if not (actor.has(AGENTS_ADMIN) or actor.role in {"owner", "admin"}):
        acl = identity_service.get_acl("agent", agent_id)
        if acl.owner_user_id != actor.user_id:
            # Non-admins who are only granted access see limited view
            return {
                "resource_type": "agent",
                "resource_id": agent_id,
                "visibility": acl.visibility,
                "owner_user_id": acl.owner_user_id,
                "grants": [],
            }
    return identity_service.get_acl("agent", agent_id).to_public_dict()


@acl_router.put("/agents/{agent_id}/visibility")
async def set_agent_visibility(agent_id: str, body: VisibilityRequest, request: Request):
    actor = require_agent_access(request, agent_id, required="editor")
    identity_service.ensure_resource(
        "agent", agent_id, owner_user_id=actor.user_id or ""
    )
    acl = identity_service.set_visibility(
        "agent", agent_id, body.visibility, actor_id=actor.user_id
    )
    return acl.to_public_dict()


@acl_router.post("/agents/{agent_id}/grants")
async def grant_agent(agent_id: str, body: GrantRequest, request: Request):
    actor = require_agent_access(request, agent_id, required="editor")
    identity_service.ensure_resource(
        "agent", agent_id, owner_user_id=actor.user_id or ""
    )
    acl = identity_service.grant_access(
        "agent",
        agent_id,
        body.user_id,
        body.level,
        actor_id=actor.user_id,
    )
    return acl.to_public_dict()


@acl_router.delete("/agents/{agent_id}/grants/{user_id}")
async def revoke_agent_grant(agent_id: str, user_id: str, request: Request):
    actor = require_agent_access(request, agent_id, required="editor")
    acl = identity_service.revoke_access(
        "agent", agent_id, user_id, actor_id=actor.user_id
    )
    return acl.to_public_dict()


@acl_router.get("/knowledge-bases/{kb_id}")
async def get_kb_acl(kb_id: str, request: Request):
    require_kb_access(request, kb_id, required="viewer")
    return identity_service.get_acl("knowledge_base", kb_id).to_public_dict()


@acl_router.put("/knowledge-bases/{kb_id}/visibility")
async def set_kb_visibility(kb_id: str, body: VisibilityRequest, request: Request):
    actor = require_kb_access(request, kb_id, required="editor")
    identity_service.ensure_resource(
        "knowledge_base", kb_id, owner_user_id=actor.user_id or ""
    )
    acl = identity_service.set_visibility(
        "knowledge_base", kb_id, body.visibility, actor_id=actor.user_id
    )
    return acl.to_public_dict()


@acl_router.post("/knowledge-bases/{kb_id}/grants")
async def grant_kb(kb_id: str, body: GrantRequest, request: Request):
    actor = require_kb_access(request, kb_id, required="editor")
    identity_service.ensure_resource(
        "knowledge_base", kb_id, owner_user_id=actor.user_id or ""
    )
    acl = identity_service.grant_access(
        "knowledge_base",
        kb_id,
        body.user_id,
        body.level,
        actor_id=actor.user_id,
    )
    return acl.to_public_dict()


@acl_router.delete("/knowledge-bases/{kb_id}/grants/{user_id}")
async def revoke_kb_grant(kb_id: str, user_id: str, request: Request):
    actor = require_kb_access(request, kb_id, required="editor")
    acl = identity_service.revoke_access(
        "knowledge_base", kb_id, user_id, actor_id=actor.user_id
    )
    return acl.to_public_dict()


# ── Audit ──────────────────────────────────────────────────────────────


@audit_router.get("")
async def query_audit(
    request: Request,
    after: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    mine: bool = Query(default=False),
):
    actor = require_actor(request)
    if mine or not actor.has(AUDIT_READ):
        if not actor.has(AUDIT_READ_OWN):
            raise HTTPException(status_code=403, detail="Forbidden")
        entries = identity_service.query_audit(
            actor_id=actor.user_id, after=after, limit=limit
        )
    else:
        require_permission(request, AUDIT_READ)
        entries = identity_service.query_audit(after=after, limit=limit)
    cursor = entries[-1]["created_at"] if entries else after
    return {"entries": entries, "cursor": cursor}

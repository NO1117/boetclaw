"""Resource ACL checks for agents, knowledge bases, and inherited resources."""

from __future__ import annotations

from fastapi import HTTPException, Request

from app.identity.actor import Actor, get_actor, require_actor
from app.identity.permissions import (
    AGENTS_ADMIN,
    KB_ADMIN,
    TASKS_ADMIN,
    GrantLevel,
    grant_satisfies,
)
from app.identity.service import identity_service


def _not_found() -> HTTPException:
    """Uniform 404 to avoid resource enumeration."""
    return HTTPException(status_code=404, detail="Not found")


def actor_or_open(request: Request) -> Actor:
    actor = get_actor(request)
    if actor is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return actor


def check_resource_access(
    actor: Actor,
    resource_type: str,
    resource_id: str,
    *,
    required: GrantLevel = "viewer",
    admin_permission: str | None = None,
) -> None:
    """Raise 404 if actor cannot access the resource at the required grant level."""
    if actor.is_open or actor.actor_type == "console_legacy":
        return
    if actor.actor_type == "api_token":
        return
    if admin_permission and actor.has(admin_permission):
        return
    if actor.role in {"owner", "admin"}:
        return

    identity_service.initialize()
    acl = identity_service.get_acl(resource_type, resource_id)

    if acl.owner_user_id and acl.owner_user_id == actor.user_id:
        return

    # Grant check
    for grant in acl.grants:
        if grant.get("user_id") == actor.user_id and grant_satisfies(
            grant.get("level", ""), required
        ):
            return

    # Workspace visibility: operators/viewers get viewer on workspace resources
    # without an explicit grant; editor/runner still need grants (or ownership).
    if acl.visibility == "workspace" and required == "viewer":
        if actor.role in {"operator", "viewer", "admin", "owner"}:
            return

    # No ACL row yet → treat as workspace (legacy resources created before RBAC)
    if not acl.owner_user_id and acl.visibility == "workspace" and not acl.grants:
        if required == "viewer":
            return
        # Creating/editing workspace resources: operators need create perms handled
        # by callers; for runner on unbound agents allow operators.
        if required in {"editor", "runner"} and actor.role == "operator":
            return

    raise _not_found()


def require_agent_access(
    request: Request,
    agent_id: str,
    *,
    required: GrantLevel = "viewer",
) -> Actor:
    actor = require_actor(request)
    check_resource_access(
        actor,
        "agent",
        agent_id,
        required=required,
        admin_permission=AGENTS_ADMIN,
    )
    return actor


def require_kb_access(
    request: Request,
    kb_id: str,
    *,
    required: GrantLevel = "viewer",
) -> Actor:
    actor = require_actor(request)
    check_resource_access(
        actor,
        "knowledge_base",
        kb_id,
        required=required,
        admin_permission=KB_ADMIN,
    )
    return actor


def can_access_agent(actor: Actor, agent_id: str, *, required: GrantLevel = "viewer") -> bool:
    try:
        check_resource_access(
            actor, "agent", agent_id, required=required, admin_permission=AGENTS_ADMIN
        )
        return True
    except HTTPException:
        return False


def can_access_kb(actor: Actor, kb_id: str, *, required: GrantLevel = "viewer") -> bool:
    try:
        check_resource_access(
            actor, "knowledge_base", kb_id, required=required, admin_permission=KB_ADMIN
        )
        return True
    except HTTPException:
        return False


def require_task_access(
    request: Request,
    *,
    created_by_user_id: str,
    agent_id: str,
    write: bool = False,
) -> Actor:
    """Tasks: creator, agent-authorized users, or admin."""
    actor = require_actor(request)
    if actor.is_open or actor.actor_type in {"console_legacy", "api_token"}:
        return actor
    if actor.has(TASKS_ADMIN) or actor.role in {"owner", "admin"}:
        return actor
    if created_by_user_id and created_by_user_id == actor.user_id:
        return actor
    # Inherited from agent: viewer can read; runner can cancel/operate.
    required: GrantLevel = "runner" if write else "viewer"
    check_resource_access(
        actor, "agent", agent_id, required=required, admin_permission=AGENTS_ADMIN
    )
    return actor


def filter_agents_for_actor(actor: Actor, agent_ids: list[str]) -> list[str]:
    if actor.is_open or actor.actor_type in {"console_legacy", "api_token"}:
        return agent_ids
    if actor.has(AGENTS_ADMIN) or actor.role in {"owner", "admin"}:
        return agent_ids
    return [aid for aid in agent_ids if can_access_agent(actor, aid, required="viewer")]

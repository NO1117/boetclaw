"""Central permission codes and role → permission mapping."""

from __future__ import annotations

from typing import Literal

SystemRole = Literal["owner", "admin", "operator", "viewer"]
GrantLevel = Literal["viewer", "editor", "runner"]
ResourceVisibility = Literal["private", "workspace"]
ResourceType = Literal["agent", "knowledge_base"]

# Permission codes — routes must check these, not role names.
USERS_READ = "users:read"
USERS_WRITE = "users:write"
USERS_MANAGE_OWNERS = "users:manage_owners"
ROLES_ASSIGN = "roles:assign"
AUDIT_READ = "audit:read"
AUDIT_READ_OWN = "audit:read_own"
SESSIONS_MANAGE = "sessions:manage"
SESSIONS_MANAGE_OWN = "sessions:manage_own"
PASSWORD_CHANGE_OWN = "password:change_own"
PROVIDERS_MANAGE = "providers:manage"
PROVIDERS_CREDENTIALS = "providers:credentials"
SECURITY_SETTINGS = "security:settings"
AGENTS_CREATE = "agents:create"
AGENTS_ADMIN = "agents:admin"
KB_CREATE = "kb:create"
KB_ADMIN = "kb:admin"
TASKS_CREATE = "tasks:create"
TASKS_ADMIN = "tasks:admin"
APPROVALS_ADMIN = "approvals:admin"
SYSTEM_SETTINGS = "system:settings"

ALL_PERMISSIONS: frozenset[str] = frozenset(
    {
        USERS_READ,
        USERS_WRITE,
        USERS_MANAGE_OWNERS,
        ROLES_ASSIGN,
        AUDIT_READ,
        AUDIT_READ_OWN,
        SESSIONS_MANAGE,
        SESSIONS_MANAGE_OWN,
        PASSWORD_CHANGE_OWN,
        PROVIDERS_MANAGE,
        PROVIDERS_CREDENTIALS,
        SECURITY_SETTINGS,
        AGENTS_CREATE,
        AGENTS_ADMIN,
        KB_CREATE,
        KB_ADMIN,
        TASKS_CREATE,
        TASKS_ADMIN,
        APPROVALS_ADMIN,
        SYSTEM_SETTINGS,
    }
)

ROLE_PERMISSIONS: dict[SystemRole, frozenset[str]] = {
    "owner": ALL_PERMISSIONS,
    "admin": frozenset(
        {
            USERS_READ,
            USERS_WRITE,
            ROLES_ASSIGN,
            AUDIT_READ,
            AUDIT_READ_OWN,
            SESSIONS_MANAGE,
            SESSIONS_MANAGE_OWN,
            PASSWORD_CHANGE_OWN,
            PROVIDERS_MANAGE,
            PROVIDERS_CREDENTIALS,
            SECURITY_SETTINGS,
            AGENTS_CREATE,
            AGENTS_ADMIN,
            KB_CREATE,
            KB_ADMIN,
            TASKS_CREATE,
            TASKS_ADMIN,
            APPROVALS_ADMIN,
            SYSTEM_SETTINGS,
        }
    ),
    "operator": frozenset(
        {
            AUDIT_READ_OWN,
            SESSIONS_MANAGE_OWN,
            PASSWORD_CHANGE_OWN,
            AGENTS_CREATE,
            KB_CREATE,
            TASKS_CREATE,
        }
    ),
    "viewer": frozenset(
        {
            AUDIT_READ_OWN,
            SESSIONS_MANAGE_OWN,
            PASSWORD_CHANGE_OWN,
        }
    ),
}

# Grant level ordering for resource ACL comparisons.
GRANT_RANK: dict[GrantLevel, int] = {
    "viewer": 1,
    "editor": 2,
    "runner": 3,
}

VALID_ROLES: frozenset[str] = frozenset(ROLE_PERMISSIONS.keys())
VALID_GRANT_LEVELS: frozenset[str] = frozenset(GRANT_RANK.keys())
VALID_VISIBILITIES: frozenset[str] = frozenset({"private", "workspace"})


def permissions_for_role(role: str) -> frozenset[str]:
    return ROLE_PERMISSIONS.get(role, frozenset())  # type: ignore[arg-type]


def has_permission(role: str, code: str) -> bool:
    return code in permissions_for_role(role)


def grant_satisfies(actual: str, required: GrantLevel) -> bool:
    return GRANT_RANK.get(actual, 0) >= GRANT_RANK[required]  # type: ignore[arg-type]

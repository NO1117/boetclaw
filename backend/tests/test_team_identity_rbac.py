"""Team identity, RBAC, sessions, CSRF, and ACL tests."""

from __future__ import annotations

import concurrent.futures

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _app() -> FastAPI:
    from app.api.routes import auth
    from app.api.routes.users import acl_router, audit_router, users_router
    from app.middleware.api_security_mw import ApiSecurityMiddleware

    app = FastAPI()
    app.add_middleware(ApiSecurityMiddleware)
    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(users_router, prefix="/api/v1")
    app.include_router(acl_router, prefix="/api/v1")
    app.include_router(audit_router, prefix="/api/v1")

    @app.get("/api/v1/protected")
    async def protected():
        return {"ok": True}

    @app.post("/api/v1/protected-write")
    async def protected_write():
        return {"ok": True}

    return app


def _auth_headers(token: str, csrf: str = "") -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if csrf:
        headers["X-CSRF-Token"] = csrf
    return headers


def test_argon2id_password_hash():
    from app.identity.passwords import hash_password, verify_password

    digest = hash_password("correct-horse-battery")
    assert digest.startswith("$argon2id$")
    assert verify_password("correct-horse-battery", digest)
    assert not verify_password("wrong", digest)


def test_role_permission_matrix():
    from app.identity.permissions import (
        AGENTS_ADMIN,
        PROVIDERS_CREDENTIALS,
        TASKS_CREATE,
        USERS_MANAGE_OWNERS,
        USERS_WRITE,
        has_permission,
        permissions_for_role,
    )

    assert has_permission("owner", USERS_MANAGE_OWNERS)
    assert has_permission("admin", USERS_WRITE)
    assert not has_permission("admin", USERS_MANAGE_OWNERS)
    assert has_permission("operator", TASKS_CREATE)
    assert not has_permission("viewer", TASKS_CREATE)
    assert AGENTS_ADMIN in permissions_for_role("admin")
    assert PROVIDERS_CREDENTIALS not in permissions_for_role("operator")


def test_bootstrap_owner_then_auth_required(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "api_token", "", raising=False)
    monkeypatch.setattr(settings, "console_password", "", raising=False)
    monkeypatch.setattr(settings, "console_jwt_secret", "jwt-secret", raising=False)
    client = TestClient(_app())

    assert client.get("/api/v1/protected").status_code == 200
    status = client.get("/api/v1/auth/status").json()
    assert status["open_mode"] is True
    assert status["bootstrap_needed"] is True

    boot = client.post(
        "/api/v1/auth/bootstrap",
        json={"username": "Owner1", "password": "password123", "display_name": "Owner"},
    )
    assert boot.status_code == 200
    data = boot.json()
    assert data["authenticated"] is True
    assert data["user"]["role"] == "owner"
    assert data["token"]
    assert data["csrf_token"]

    # Fresh client: open write paths now require auth
    client2 = TestClient(_app())
    assert client2.get("/api/v1/protected").status_code == 401
    assert client2.get(
        "/api/v1/protected", headers=_auth_headers(data["token"])
    ).status_code == 200


def test_login_lockout(monkeypatch):
    from app.core.config import settings
    from app.identity.service import identity_service

    monkeypatch.setattr(settings, "api_token", "", raising=False)
    monkeypatch.setattr(settings, "console_password", "", raising=False)
    monkeypatch.setattr(settings, "console_jwt_secret", "jwt-secret", raising=False)
    monkeypatch.setattr(settings, "login_lock_base_seconds", 30, raising=False)
    client = TestClient(_app())
    client.post(
        "/api/v1/auth/bootstrap",
        json={"username": "alice", "password": "password123"},
    )
    # Use a fresh identity login path
    for _ in range(3):
        resp = client.post(
            "/api/v1/auth/login",
            json={"username": "alice", "password": "wrong-password"},
        )
        assert resp.status_code == 401
    locked = client.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": "wrong-password"},
    )
    assert locked.status_code == 429


def test_session_revoke_and_token_version(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "api_token", "", raising=False)
    monkeypatch.setattr(settings, "console_password", "", raising=False)
    monkeypatch.setattr(settings, "console_jwt_secret", "jwt-secret", raising=False)
    client = TestClient(_app())
    boot = client.post(
        "/api/v1/auth/bootstrap",
        json={"username": "owner", "password": "password123"},
    ).json()
    token = boot["token"]
    assert client.get("/api/v1/protected", headers=_auth_headers(token)).status_code == 200

    revoke = client.post(
        "/api/v1/auth/sessions/revoke-all",
        headers=_auth_headers(token),
    )
    assert revoke.status_code == 200
    assert client.get("/api/v1/protected", headers=_auth_headers(token)).status_code == 401


def test_csrf_required_for_cookie_writes(monkeypatch):
    from app.core.config import settings
    from app.security.console_auth import CSRF_COOKIE, TOKEN_COOKIE

    monkeypatch.setattr(settings, "api_token", "", raising=False)
    monkeypatch.setattr(settings, "console_password", "", raising=False)
    monkeypatch.setattr(settings, "console_jwt_secret", "jwt-secret", raising=False)
    client = TestClient(_app())
    boot = client.post(
        "/api/v1/auth/bootstrap",
        json={"username": "owner", "password": "password123"},
    )
    data = boot.json()
    # Cookie auth without CSRF header
    r = client.post("/api/v1/protected-write")
    assert r.status_code == 403
    # Cookie auth with CSRF
    r2 = client.post(
        "/api/v1/protected-write",
        headers={"X-CSRF-Token": data["csrf_token"]},
    )
    assert r2.status_code == 200
    # Bearer skips CSRF
    r3 = client.post(
        "/api/v1/protected-write",
        headers=_auth_headers(data["token"]),
    )
    assert r3.status_code == 200
    assert TOKEN_COOKIE in boot.cookies or client.cookies.get(TOKEN_COOKIE)
    assert CSRF_COOKIE in boot.cookies or client.cookies.get(CSRF_COOKIE)


def test_console_password_compat_and_api_token(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "api_token", "secret-token", raising=False)
    monkeypatch.setattr(settings, "console_password", "console-secret", raising=False)
    monkeypatch.setattr(settings, "console_jwt_secret", "jwt-secret", raising=False)
    client = TestClient(_app())

    assert client.get("/api/v1/protected").status_code == 401
    assert client.get(
        "/api/v1/protected", headers={"Authorization": "Bearer secret-token"}
    ).status_code == 200

    login = client.post("/api/v1/auth/login", json={"password": "console-secret"})
    assert login.status_code == 200
    token = login.json()["token"]
    assert client.get("/api/v1/protected", headers=_auth_headers(token)).status_code == 200


def test_last_owner_protected_under_concurrency(monkeypatch):
    from app.core.config import settings
    from app.identity.service import identity_service

    monkeypatch.setattr(settings, "api_token", "", raising=False)
    monkeypatch.setattr(settings, "console_password", "", raising=False)
    monkeypatch.setattr(settings, "console_jwt_secret", "jwt-secret", raising=False)
    client = TestClient(_app())
    boot = client.post(
        "/api/v1/auth/bootstrap",
        json={"username": "owner", "password": "password123"},
    ).json()
    owner_id = boot["user"]["id"]
    token = boot["token"]

    def _disable():
        return client.patch(
            f"/api/v1/users/{owner_id}",
            json={"status": "disabled"},
            headers=_auth_headers(token),
        ).status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        codes = list(pool.map(lambda _: _disable(), range(8)))
    assert 409 in codes
    assert identity_service.store.count_active_owners() == 1


def test_admin_cannot_manage_owners(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "api_token", "", raising=False)
    monkeypatch.setattr(settings, "console_password", "", raising=False)
    monkeypatch.setattr(settings, "console_jwt_secret", "jwt-secret", raising=False)
    client = TestClient(_app())
    boot = client.post(
        "/api/v1/auth/bootstrap",
        json={"username": "owner", "password": "password123"},
    ).json()
    owner_token = boot["token"]
    owner_id = boot["user"]["id"]

    admin = client.post(
        "/api/v1/users",
        json={
            "username": "admin1",
            "password": "password123",
            "role": "admin",
            "display_name": "Admin",
        },
        headers=_auth_headers(owner_token),
    ).json()
    login = client.post(
        "/api/v1/auth/login",
        json={"username": "admin1", "password": "password123"},
    ).json()
    admin_token = login["token"]

    assert (
        client.patch(
            f"/api/v1/users/{owner_id}",
            json={"status": "disabled"},
            headers=_auth_headers(admin_token),
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/users",
            json={"username": "owner2", "password": "password123", "role": "owner"},
            headers=_auth_headers(admin_token),
        ).status_code
        == 403
    )
    assert admin["role"] == "admin"


def test_resource_acl_private_agent_idor(monkeypatch):
    from app.core.config import settings
    from app.identity.service import identity_service

    monkeypatch.setattr(settings, "api_token", "", raising=False)
    monkeypatch.setattr(settings, "console_password", "", raising=False)
    monkeypatch.setattr(settings, "console_jwt_secret", "jwt-secret", raising=False)
    client = TestClient(_app())
    boot = client.post(
        "/api/v1/auth/bootstrap",
        json={"username": "owner", "password": "password123"},
    ).json()
    owner_token = boot["token"]

    client.post(
        "/api/v1/users",
        json={"username": "op1", "password": "password123", "role": "operator"},
        headers=_auth_headers(owner_token),
    )
    client.post(
        "/api/v1/users",
        json={"username": "view1", "password": "password123", "role": "viewer"},
        headers=_auth_headers(owner_token),
    )
    op = client.post(
        "/api/v1/auth/login", json={"username": "op1", "password": "password123"}
    ).json()
    viewer = client.post(
        "/api/v1/auth/login", json={"username": "view1", "password": "password123"}
    ).json()

    identity_service.ensure_resource(
        "agent", "secret-agent", owner_user_id=boot["user"]["id"], visibility="private"
    )
    # Grant operator runner
    op_user = identity_service.store.get_user_by_username("op1")
    assert op_user is not None
    identity_service.grant_access(
        "agent", "secret-agent", op_user.id, "runner", actor_id=boot["user"]["id"]
    )

    from app.identity.actor import Actor
    from app.identity.permissions import permissions_for_role
    from app.identity.resource_acl import can_access_agent

    op_actor = Actor(
        actor_type="user",
        user_id=op_user.id,
        role="operator",
        permissions=permissions_for_role("operator"),
    )
    viewer_user = identity_service.store.get_user_by_username("view1")
    assert viewer_user is not None
    viewer_actor = Actor(
        actor_type="user",
        user_id=viewer_user.id,
        role="viewer",
        permissions=permissions_for_role("viewer"),
    )
    assert can_access_agent(op_actor, "secret-agent", required="runner")
    assert not can_access_agent(viewer_actor, "secret-agent", required="viewer")
    assert op["user"]["role"] == "operator"
    assert viewer["user"]["role"] == "viewer"


def test_username_normalization():
    from app.identity.usernames import normalize_username

    assert normalize_username("  Alice ") == "alice"
    assert normalize_username("Bob.Smith") == "bob.smith"
    with pytest.raises(ValueError):
        normalize_username("a")

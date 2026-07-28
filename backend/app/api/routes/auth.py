"""Authentication, bootstrap, session, and current-user routes."""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.core.config import settings
from app.identity.actor import get_actor, require_actor
from app.identity.permissions import PASSWORD_CHANGE_OWN, SESSIONS_MANAGE_OWN, permissions_for_role
from app.identity.service import identity_service
from app.security.console_auth import CSRF_COOKIE, TOKEN_COOKIE

router = APIRouter(prefix="/auth", tags=["auth"])


class ConsoleLoginRequest(BaseModel):
    """Backward-compatible login body: password required; username optional."""

    password: str = Field(..., min_length=1)
    username: str = ""


class BootstrapRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=64)
    password: str = Field(..., min_length=8)
    display_name: str = ""
    bootstrap_token: str = ""


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8)


def _cookie_secure() -> bool:
    return bool(settings.console_cookie_secure)


def _set_session_cookies(
    response: Response,
    *,
    token: str,
    csrf_token: str = "",
) -> None:
    max_age = max(settings.console_jwt_ttl_minutes, 1) * 60
    response.set_cookie(
        TOKEN_COOKIE,
        token,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        secure=_cookie_secure(),
        path="/",
    )
    if csrf_token:
        response.set_cookie(
            CSRF_COOKIE,
            csrf_token,
            max_age=max_age,
            httponly=False,
            samesite="lax",
            secure=_cookie_secure(),
            path="/",
        )


def _clear_session_cookies(response: Response) -> None:
    response.delete_cookie(TOKEN_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else ""


def _status_payload(request: Request) -> dict:
    identity_service.initialize()
    actor = get_actor(request)
    open_mode = identity_service.is_open_mode()
    authenticated = bool(actor and actor.is_authenticated and actor.actor_type != "open")
    if open_mode:
        authenticated = True
    user_payload = None
    if actor and (open_mode or actor.actor_type not in {""}):
        if actor.actor_type != "open" or open_mode:
            user_payload = actor.to_public_dict()
    return {
        "login_required": identity_service.login_required() and not open_mode,
        "authenticated": authenticated,
        "open_mode": open_mode,
        "bootstrap_needed": identity_service.bootstrap_needed(),
        "ttl_minutes": settings.console_jwt_ttl_minutes,
        "deprecate_console_password": bool(
            settings.console_password and identity_service.has_users()
        ),
        "user": user_payload,
    }


@router.get("/status")
async def auth_status(request: Request, authorization: str = Header(default="")):
    return _status_payload(request)


@router.post("/bootstrap")
async def bootstrap(body: BootstrapRequest, request: Request, response: Response):
    user, session, token = identity_service.bootstrap_owner(
        username=body.username,
        password=body.password,
        display_name=body.display_name,
        client_host=_client_ip(request),
        bootstrap_token=body.bootstrap_token,
        ip=_client_ip(request),
        user_agent=request.headers.get("user-agent", ""),
    )
    _set_session_cookies(response, token=token, csrf_token=session.csrf_token)
    return {
        "login_required": True,
        "authenticated": True,
        "bootstrap_needed": False,
        "open_mode": False,
        "token": token,
        "csrf_token": session.csrf_token,
        "ttl_minutes": settings.console_jwt_ttl_minutes,
        "deprecate_console_password": bool(settings.console_password),
        "user": user.to_public_dict(permissions=list(permissions_for_role(user.role))),
    }


@router.post("/login")
async def login(body: ConsoleLoginRequest, request: Request, response: Response):
    identity_service.initialize()
    if not identity_service.login_required() and identity_service.is_open_mode():
        return {
            "login_required": False,
            "authenticated": True,
            "open_mode": True,
            "token": "",
            "csrf_token": "",
        }

    user, session, token, meta = identity_service.login(
        username=body.username,
        password=body.password,
        ip=_client_ip(request),
        user_agent=request.headers.get("user-agent", ""),
    )
    csrf = session.csrf_token if session else ""
    _set_session_cookies(response, token=token, csrf_token=csrf)
    payload = {
        "login_required": True,
        "authenticated": True,
        "open_mode": False,
        "token": token,
        "csrf_token": csrf,
        "ttl_minutes": settings.console_jwt_ttl_minutes,
        "deprecate_console_password": bool(meta.get("deprecate_console_password")),
        "mode": meta.get("mode"),
    }
    if user:
        payload["user"] = user.to_public_dict(
            permissions=list(permissions_for_role(user.role))
        )
    return payload


@router.post("/logout")
async def logout(request: Request, response: Response):
    actor = get_actor(request)
    if actor and actor.session_id:
        identity_service.logout_session(actor.session_id)
        identity_service.audit(
            actor_id=actor.user_id,
            actor_type=actor.actor_type,
            action="logout",
            result="success",
            source=_client_ip(request),
        )
    _clear_session_cookies(response)
    return {"authenticated": False}


@router.get("/me")
async def auth_me(request: Request):
    identity_service.initialize()
    if identity_service.is_open_mode():
        return {
            "open_mode": True,
            "authenticated": True,
            "user": {
                "actor_type": "open",
                "role": "owner",
                "permissions": sorted(permissions_for_role("owner")),
                "open_mode": True,
            },
            "csrf_token": "",
        }
    actor = require_actor(request)
    if actor.is_user:
        public = identity_service.get_user_public(actor.user_id) or actor.to_public_dict()
    else:
        public = actor.to_public_dict()
    return {
        "open_mode": False,
        "authenticated": True,
        "user": public,
        "csrf_token": actor.csrf_token,
        "session_id": actor.session_id or None,
    }


@router.post("/password")
async def change_password(body: ChangePasswordRequest, request: Request, response: Response):
    actor = require_actor(request)
    if not actor.has(PASSWORD_CHANGE_OWN) or not actor.is_user:
        raise HTTPException(status_code=403, detail="Forbidden")
    session = identity_service.change_own_password(
        actor.user_id,
        current_password=body.current_password,
        new_password=body.new_password,
    )
    from app.security.console_auth import create_user_token

    user = identity_service.store.get_user(actor.user_id)
    assert user is not None
    token = create_user_token(
        user_id=user.id,
        role=user.role,
        token_version=user.token_version,
        session_id=session.id,
    )
    _set_session_cookies(response, token=token, csrf_token=session.csrf_token)
    return {
        "ok": True,
        "csrf_token": session.csrf_token,
        "token": token,
    }


@router.get("/sessions")
async def list_sessions(request: Request):
    actor = require_actor(request)
    if not actor.has(SESSIONS_MANAGE_OWN) or not actor.is_user:
        raise HTTPException(status_code=403, detail="Forbidden")
    sessions = identity_service.store.list_sessions(actor.user_id)
    return {
        "sessions": [
            {
                "id": s.id,
                "created_at": s.created_at,
                "expires_at": s.expires_at,
                "last_seen_at": s.last_seen_at,
                "ip": s.ip,
                "user_agent": s.user_agent,
                "current": s.id == actor.session_id,
            }
            for s in sessions
        ]
    }


@router.delete("/sessions/{session_id}")
async def revoke_session(session_id: str, request: Request):
    actor = require_actor(request)
    if not actor.has(SESSIONS_MANAGE_OWN) or not actor.is_user:
        raise HTTPException(status_code=403, detail="Forbidden")
    session = identity_service.store.get_session(session_id)
    if session is None or session.user_id != actor.user_id:
        raise HTTPException(status_code=404, detail="Not found")
    identity_service.store.revoke_session(session_id)
    identity_service.audit(
        actor_id=actor.user_id,
        actor_type="user",
        action="sessions.revoke",
        resource_type="session",
        resource_id=session_id,
        result="success",
    )
    return {"ok": True}


@router.post("/sessions/revoke-all")
async def revoke_all_own_sessions(request: Request, response: Response):
    actor = require_actor(request)
    if not actor.has(SESSIONS_MANAGE_OWN) or not actor.is_user:
        raise HTTPException(status_code=403, detail="Forbidden")
    identity_service.revoke_all_sessions(actor.user_id, bump_version=True)
    _clear_session_cookies(response)
    return {"ok": True, "authenticated": False}

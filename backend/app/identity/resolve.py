"""Resolve request actor — shared by middleware and lazy route helpers."""

from __future__ import annotations

import secrets

from starlette.requests import Request

from app.core.config import settings
from app.identity.actor import Actor
from app.identity.permissions import permissions_for_role
from app.security.console_auth import TOKEN_COOKIE, extract_bearer_token, verify_console_token, verify_user_token


def resolve_request_actor(request: Request) -> Actor | None:
    from app.identity.service import identity_service

    identity_service.initialize()
    auth = request.headers.get("authorization", "")
    bearer = extract_bearer_token(auth)
    api_token = settings.api_token

    if api_token and (
        (bearer and secrets.compare_digest(bearer, api_token))
        or secrets.compare_digest(request.headers.get("x-api-token", ""), api_token)
    ):
        return Actor(
            actor_type="api_token",
            user_id="api_token",
            username="api_token",
            display_name="API Token",
            role="admin",
            permissions=permissions_for_role("admin"),
            auth_via="api_token",
        )

    cookie_token = request.cookies.get(TOKEN_COOKIE, "")
    token = bearer or cookie_token
    auth_via = "bearer" if bearer else ("cookie" if cookie_token else "")

    if token:
        if verify_user_token(token):
            resolved = identity_service.resolve_user_token(token)
            if resolved:
                user, session = resolved
                identity_service.store.touch_session(session.id)
                return Actor(
                    actor_type="user",
                    user_id=user.id,
                    username=user.username,
                    display_name=user.display_name,
                    role=user.role,
                    session_id=session.id,
                    token_version=user.token_version,
                    permissions=permissions_for_role(user.role),
                    auth_via=auth_via,
                    csrf_token=session.csrf_token,
                )
            return None

        console_payload = verify_console_token(token)
        if console_payload and console_payload.get("scope") == "console":
            return Actor(
                actor_type="console_legacy",
                user_id="console_legacy",
                username="console",
                display_name="Console",
                role="owner",
                permissions=permissions_for_role("owner"),
                auth_via=auth_via,
            )

    if identity_service.is_open_mode():
        return Actor(
            actor_type="open",
            user_id="open",
            username="open",
            display_name="Open Mode",
            role="owner",
            permissions=permissions_for_role("owner"),
            auth_via="open",
        )

    return None

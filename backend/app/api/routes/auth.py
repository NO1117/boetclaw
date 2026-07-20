"""Console authentication routes."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.core.config import settings
from app.security.console_auth import (
    TOKEN_COOKIE,
    create_console_token,
    extract_bearer_token,
    verify_console_token,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class ConsoleLoginRequest(BaseModel):
    password: str = Field(..., min_length=1)


def _token_from_request(request: Request, authorization: str = "") -> str:
    return extract_bearer_token(authorization) or request.cookies.get(TOKEN_COOKIE, "")


@router.get("/status")
async def auth_status(request: Request, authorization: str = Header(default="")):
    token = _token_from_request(request, authorization)
    return {
        "login_required": bool(settings.console_password),
        "authenticated": bool(verify_console_token(token)),
        "ttl_minutes": settings.console_jwt_ttl_minutes,
    }


@router.post("/login")
async def login(body: ConsoleLoginRequest, response: Response):
    if not settings.console_password:
        return {"login_required": False, "authenticated": True, "token": ""}
    if not secrets.compare_digest(body.password, settings.console_password):
        raise HTTPException(status_code=401, detail="Invalid password")
    token = create_console_token()
    max_age = max(settings.console_jwt_ttl_minutes, 1) * 60
    response.set_cookie(
        TOKEN_COOKIE,
        token,
        max_age=max_age,
        httponly=True,
        samesite="lax",
    )
    return {
        "login_required": True,
        "authenticated": True,
        "token": token,
        "ttl_minutes": settings.console_jwt_ttl_minutes,
    }


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(TOKEN_COOKIE)
    return {"authenticated": False}

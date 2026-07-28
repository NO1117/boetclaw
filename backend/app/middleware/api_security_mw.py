"""API token / session authentication, CSRF, and lightweight rate limiting."""

from __future__ import annotations

import secrets
import time
from collections import defaultdict, deque
from collections.abc import Callable
from hashlib import sha256

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings
from app.identity.actor import Actor
from app.identity.resolve import resolve_request_actor
from app.security.console_auth import (
    CSRF_COOKIE,
    CSRF_HEADER,
    TOKEN_COOKIE,
    extract_bearer_token,
)


_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


class ApiSecurityMiddleware(BaseHTTPMiddleware):
    """Protect /api/v1 routes when configured.

    Defaults are open for local development: empty API_TOKEN, empty CONSOLE_PASSWORD,
    and no bootstrapped users disables auth. API_RATE_LIMIT_PER_MINUTE=0 disables rate limiting.
    """

    def __init__(self, app, api_prefix: str = "/api/v1") -> None:
        super().__init__(app)
        self.api_prefix = api_prefix
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    @staticmethod
    def _is_health_path(path: str) -> bool:
        return path.endswith("/monitor/health")

    @staticmethod
    def _is_auth_path(path: str) -> bool:
        return "/auth/" in path

    @staticmethod
    def _is_gateway_webhook_path(path: str) -> bool:
        """Platform callbacks cannot send API_TOKEN; rely on channel verify_signature."""
        return "/gateway/" in path and path.endswith("/webhook")

    def _resolve_actor(self, request: Request) -> Actor | None:
        return resolve_request_actor(request)

    def _csrf_ok(self, request: Request, actor: Actor) -> bool:
        if request.method in _SAFE_METHODS:
            return True
        # Bearer / API token / open mode do not use cookie CSRF.
        if actor.auth_via in {"bearer", "api_token", "open"}:
            return True
        if actor.actor_type == "console_legacy" and actor.auth_via == "bearer":
            return True
        if actor.auth_via != "cookie":
            return True
        header = request.headers.get(CSRF_HEADER, "")
        cookie = request.cookies.get(CSRF_COOKIE, "")
        expected = actor.csrf_token or cookie
        if not header or not expected:
            return False
        return secrets.compare_digest(header, expected)

    @staticmethod
    def _rate_key(request: Request, actor: Actor | None) -> str:
        if actor and actor.user_id:
            return f"actor:{actor.actor_type}:{actor.user_id}"
        auth = request.headers.get("authorization", "")
        token = (
            extract_bearer_token(auth)
            or request.headers.get("x-api-token", "")
            or request.cookies.get(TOKEN_COOKIE, "")
        )
        if token:
            digest = sha256(token.encode("utf-8")).hexdigest()[:16]
            return f"token:{digest}"
        client = request.client.host if request.client else "unknown"
        return f"ip:{client}"

    def _rate_limited(self, request: Request, actor: Actor | None) -> bool:
        limit = settings.api_rate_limit_per_minute
        if limit <= 0:
            return False
        key = self._rate_key(request, actor)
        now = time.monotonic()
        window_start = now - 60
        hits = self._hits[key]
        while hits and hits[0] < window_start:
            hits.popleft()
        if len(hits) >= limit:
            return True
        hits.append(now)
        return False

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        if not path.startswith(self.api_prefix):
            return await call_next(request)

        is_exempt = (
            self._is_health_path(path)
            or self._is_auth_path(path)
            or self._is_gateway_webhook_path(path)
        )

        actor = self._resolve_actor(request)
        request.state.actor = actor

        if is_exempt:
            return await call_next(request)

        if actor is None:
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)

        if not self._csrf_ok(request, actor):
            return JSONResponse({"detail": "CSRF validation failed"}, status_code=403)

        if self._rate_limited(request, actor):
            return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429)

        return await call_next(request)

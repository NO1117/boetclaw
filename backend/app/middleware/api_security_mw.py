"""API token authentication and lightweight rate limiting."""

from __future__ import annotations

import time
from hashlib import sha256
from collections import defaultdict, deque
from collections.abc import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings
from app.security.console_auth import TOKEN_COOKIE, extract_bearer_token, verify_console_token


class ApiSecurityMiddleware(BaseHTTPMiddleware):
    """Protect /api/v1 routes when configured.

    Defaults are open for local development: empty API_TOKEN disables auth and
    API_RATE_LIMIT_PER_MINUTE=0 disables rate limiting.
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

    @staticmethod
    def _authorized(request: Request) -> bool:
        api_token = settings.api_token
        console_password = settings.console_password
        if not api_token and not console_password:
            return True
        auth = request.headers.get("authorization", "")
        bearer = extract_bearer_token(auth)
        if api_token and bearer == api_token:
            return True
        if api_token and request.headers.get("x-api-token", "") == api_token:
            return True
        console_token = bearer or request.cookies.get(TOKEN_COOKIE, "")
        return bool(verify_console_token(console_token))

    @staticmethod
    def _rate_key(request: Request) -> str:
        auth = request.headers.get("authorization", "")
        token = extract_bearer_token(auth) or request.headers.get("x-api-token", "") or request.cookies.get(TOKEN_COOKIE, "")
        if token:
            digest = sha256(token.encode("utf-8")).hexdigest()[:16]
            return f"token:{digest}"
        client = request.client.host if request.client else "unknown"
        return f"ip:{client}"

    def _rate_limited(self, request: Request) -> bool:
        limit = settings.api_rate_limit_per_minute
        if limit <= 0:
            return False
        key = self._rate_key(request)
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
        if (
            not path.startswith(self.api_prefix)
            or self._is_health_path(path)
            or self._is_auth_path(path)
            or self._is_gateway_webhook_path(path)
        ):
            return await call_next(request)
        if not self._authorized(request):
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        if self._rate_limited(request):
            return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429)
        return await call_next(request)

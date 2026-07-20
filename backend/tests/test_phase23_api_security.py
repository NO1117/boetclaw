"""Phase 23 tests: API auth and rate limiting middleware."""

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _app() -> FastAPI:
    from app.middleware.api_security_mw import ApiSecurityMiddleware
    from app.api.routes import auth

    app = FastAPI()
    app.add_middleware(ApiSecurityMiddleware)
    app.include_router(auth.router, prefix="/api/v1")

    @app.get("/api/v1/protected")
    async def protected():
        return {"ok": True}

    @app.get("/api/v1/monitor/health")
    async def health():
        return {"status": "healthy"}

    return app


def test_api_token_auth(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "api_token", "secret-token", raising=False)
    monkeypatch.setattr(settings, "api_rate_limit_per_minute", 0, raising=False)
    client = TestClient(_app())

    assert client.get("/api/v1/protected").status_code == 401
    assert client.get("/api/v1/protected", headers={"Authorization": "Bearer secret-token"}).status_code == 200
    assert client.get("/api/v1/protected", headers={"X-API-Token": "secret-token"}).status_code == 200


def test_health_exempt_from_auth(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "api_token", "secret-token", raising=False)
    monkeypatch.setattr(settings, "api_rate_limit_per_minute", 1, raising=False)
    client = TestClient(_app())

    assert client.get("/api/v1/monitor/health").status_code == 200
    assert client.get("/api/v1/monitor/health").status_code == 200


def test_api_rate_limit(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "api_token", "", raising=False)
    monkeypatch.setattr(settings, "api_rate_limit_per_minute", 2, raising=False)
    client = TestClient(_app())

    assert client.get("/api/v1/protected").status_code == 200
    assert client.get("/api/v1/protected").status_code == 200
    assert client.get("/api/v1/protected").status_code == 429


def test_api_rate_limit_buckets_by_token(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "api_token", "", raising=False)
    monkeypatch.setattr(settings, "api_rate_limit_per_minute", 1, raising=False)
    monkeypatch.setattr(settings, "console_password", "console-secret", raising=False)
    monkeypatch.setattr(settings, "console_jwt_secret", "jwt-secret", raising=False)
    monkeypatch.setattr(settings, "console_jwt_ttl_minutes", 10, raising=False)
    client_a = TestClient(_app())
    client_b = TestClient(_app())

    token_a = client_a.post("/api/v1/auth/login", json={"password": "console-secret"}).json()["token"]
    token_b = client_b.post("/api/v1/auth/login", json={"password": "console-secret"}).json()["token"]

    assert client_a.get("/api/v1/protected", headers={"Authorization": f"Bearer {token_a}"}).status_code == 200
    assert client_a.get("/api/v1/protected", headers={"Authorization": f"Bearer {token_a}"}).status_code == 429
    assert client_b.get("/api/v1/protected", headers={"Authorization": f"Bearer {token_b}"}).status_code == 200


def test_console_login_token_auth(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "api_token", "", raising=False)
    monkeypatch.setattr(settings, "api_rate_limit_per_minute", 0, raising=False)
    monkeypatch.setattr(settings, "console_password", "console-secret", raising=False)
    monkeypatch.setattr(settings, "console_jwt_secret", "jwt-secret", raising=False)
    monkeypatch.setattr(settings, "console_jwt_ttl_minutes", 10, raising=False)
    client = TestClient(_app())

    status = client.get("/api/v1/auth/status").json()
    assert status["login_required"] is True
    assert status["authenticated"] is False
    assert client.get("/api/v1/protected").status_code == 401
    assert client.post("/api/v1/auth/login", json={"password": "wrong"}).status_code == 401

    login = client.post("/api/v1/auth/login", json={"password": "console-secret"})
    assert login.status_code == 200
    token = login.json()["token"]
    assert token
    assert client.get("/api/v1/protected").status_code == 200
    assert client.get("/api/v1/protected", headers={"Authorization": f"Bearer {token}"}).status_code == 200

    assert client.post("/api/v1/auth/logout").status_code == 200
    assert client.get("/api/v1/protected").status_code == 401

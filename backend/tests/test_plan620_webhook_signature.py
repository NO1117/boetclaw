"""PLAN-620: channel webhook signature verification and middleware exemption."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _dingtalk_sign(secret: str, timestamp: str) -> str:
    string_to_sign = f"{timestamp}\n{secret}"
    digest = hmac.new(secret.encode(), string_to_sign.encode(), digestmod=hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def test_dingtalk_verify_signature_ok_and_fail():
    from app.services.gateway.channels.dingtalk import DingTalkChannel

    secret = "dt-secret"
    ch = DingTalkChannel(webhook_secret=secret)
    ts = "1710000000000"
    assert ch.signature_configured() is True
    assert ch.verify_signature({"timestamp": ts, "sign": _dingtalk_sign(secret, ts)}, b"{}") is True
    assert ch.verify_signature({"timestamp": ts, "sign": "bad"}, b"{}") is False
    assert ch.verify_signature({}, b"{}") is False


def test_dingtalk_verify_skipped_without_secret():
    from app.services.gateway.channels.dingtalk import DingTalkChannel

    ch = DingTalkChannel()
    assert ch.signature_configured() is False
    assert ch.verify_signature({}, b"{}") is True


def test_feishu_verify_token():
    from app.services.gateway.channels.feishu import FeishuChannel

    ch = FeishuChannel(verification_token="feishu-token")
    assert ch.signature_configured() is True
    body = json.dumps({"token": "feishu-token", "type": "event_callback"}).encode()
    assert ch.verify_signature({}, body) is True
    v2 = json.dumps({"header": {"token": "feishu-token", "event_type": "im.message.receive_v1"}}).encode()
    assert ch.verify_signature({}, v2) is True
    assert ch.verify_signature({}, json.dumps({"token": "wrong"}).encode()) is False
    assert FeishuChannel().verify_signature({}, json.dumps({"token": "x"}).encode()) is True


def test_qq_verify_bearer_and_hmac():
    from app.services.gateway.channels.qq import QQChannel

    secret = "qq-secret"
    ch = QQChannel(webhook_secret=secret)
    body = b'{"post_type":"message"}'
    assert ch.verify_signature({"Authorization": f"Bearer {secret}"}, body) is True
    digest = hmac.new(secret.encode(), body, hashlib.sha1).hexdigest()
    assert ch.verify_signature({"X-Signature": f"sha1={digest}"}, body) is True
    assert ch.verify_signature({"X-Signature": "sha1=deadbeef"}, body) is False
    assert ch.verify_signature({}, body) is False
    assert QQChannel().verify_signature({}, body) is True


def test_telegram_verify_secret_header():
    from app.services.gateway.channels.telegram import TelegramChannel

    ch = TelegramChannel(webhook_secret="tg-secret")
    assert ch.signature_configured() is True
    assert ch.verify_signature({"X-Telegram-Bot-Api-Secret-Token": "tg-secret"}, b"{}") is True
    assert ch.verify_signature({"X-Telegram-Bot-Api-Secret-Token": "nope"}, b"{}") is False
    assert ch.verify_signature({}, b"{}") is False
    assert TelegramChannel().verify_signature({}, b"{}") is True


class _SigChannel:
    channel = "sigtest"
    render_style = type("Style", (), {"value": "plain"})()

    def __init__(self, secret: str = "") -> None:
        self.secret = secret

    def is_configured(self) -> bool:
        return True

    def signature_configured(self) -> bool:
        return bool(self.secret)

    def verify_signature(self, headers=None, body=None, **kwargs):
        if not self.secret:
            return True
        return (headers or {}).get("x-test-sign") == self.secret

    async def parse_incoming(self, payload: dict[str, Any]):
        from app.services.gateway.base import GatewayMessage

        return GatewayMessage(
            platform="sigtest",
            user_id=str(payload.get("user_id", "u1")),
            user_name="n",
            content=str(payload.get("content", "hi")),
            message_id="m1",
            chat_id="c1",
            raw=payload,
        )

    async def send_reply(self, message, content: str):
        return None


def _reset_manager(monkeypatch, channel):
    from app.services.gateway.manager import channel_manager

    monkeypatch.setattr(channel_manager, "_channels", {}, raising=False)
    monkeypatch.setattr(channel_manager, "_queues", {}, raising=False)
    monkeypatch.setattr(channel_manager, "_consumers", {}, raising=False)
    monkeypatch.setattr(channel_manager, "_history", [], raising=False)
    channel_manager.register(channel)
    return channel_manager


def test_webhook_route_rejects_bad_signature(monkeypatch, tmp_path):
    from app.main import app
    from app.services.gateway.access_control import access_control_store

    monkeypatch.setattr(access_control_store, "path", tmp_path / "access_control.json", raising=False)
    access_control_store.update({})
    _reset_manager(monkeypatch, _SigChannel(secret="good"))

    client = TestClient(app)
    bad = client.post("/api/v1/gateway/sigtest/webhook", json={"content": "x"}, headers={"X-Test-Sign": "bad"})
    assert bad.status_code == 401
    assert bad.json()["detail"] == "Invalid webhook signature"

    ok = client.post("/api/v1/gateway/sigtest/webhook", json={"content": "x"}, headers={"X-Test-Sign": "good"})
    assert ok.status_code == 200
    assert ok.json()["signature"] == "verified"
    assert ok.json()["message"] == "Task queued"


def test_webhook_route_skips_when_secret_unset(monkeypatch, tmp_path):
    from app.main import app
    from app.services.gateway.access_control import access_control_store

    monkeypatch.setattr(access_control_store, "path", tmp_path / "access_control.json", raising=False)
    access_control_store.update({})
    _reset_manager(monkeypatch, _SigChannel(secret=""))

    client = TestClient(app)
    res = client.post("/api/v1/gateway/sigtest/webhook", json={"content": "hello"})
    assert res.status_code == 200
    assert res.json()["signature"] == "skipped"
    assert res.json()["message"] == "Task queued"


def test_dingtalk_webhook_route_signature(monkeypatch, tmp_path):
    from app.main import app
    from app.services.gateway.access_control import access_control_store
    from app.services.gateway.channels.dingtalk import DingTalkChannel

    monkeypatch.setattr(access_control_store, "path", tmp_path / "access_control.json", raising=False)
    access_control_store.update({})
    secret = "dt-route-secret"
    _reset_manager(monkeypatch, DingTalkChannel(webhook_secret=secret))

    client = TestClient(app)
    payload = {
        "msgtype": "text",
        "text": {"content": "ping"},
        "senderStaffId": "u1",
        "conversationId": "c1",
    }
    ts = "1710000000000"
    bad = client.post(
        "/api/v1/gateway/dingtalk/webhook",
        json=payload,
        headers={"timestamp": ts, "sign": "nope"},
    )
    assert bad.status_code == 401

    ok = client.post(
        "/api/v1/gateway/dingtalk/webhook",
        json=payload,
        headers={"timestamp": ts, "sign": _dingtalk_sign(secret, ts)},
    )
    assert ok.status_code == 200
    assert ok.json()["signature"] == "verified"


def test_feishu_webhook_route_token(monkeypatch, tmp_path):
    from app.main import app
    from app.services.gateway.access_control import access_control_store
    from app.services.gateway.channels.feishu import FeishuChannel

    monkeypatch.setattr(access_control_store, "path", tmp_path / "access_control.json", raising=False)
    access_control_store.update({})
    _reset_manager(monkeypatch, FeishuChannel(verification_token="vt"))

    client = TestClient(app)
    bad = client.post(
        "/api/v1/gateway/feishu/webhook",
        json={"type": "url_verification", "challenge": "c1", "token": "wrong"},
    )
    assert bad.status_code == 401

    ok = client.post(
        "/api/v1/gateway/feishu/webhook",
        json={"type": "url_verification", "challenge": "c1", "token": "vt"},
    )
    assert ok.status_code == 200
    assert ok.json()["challenge"] == "c1"
    assert ok.json()["signature"] == "verified"


def test_telegram_webhook_route_secret(monkeypatch, tmp_path):
    from app.main import app
    from app.services.gateway.access_control import access_control_store
    from app.services.gateway.channels.telegram import TelegramChannel

    monkeypatch.setattr(access_control_store, "path", tmp_path / "access_control.json", raising=False)
    access_control_store.update({})
    _reset_manager(monkeypatch, TelegramChannel(webhook_secret="tg-wh"))

    client = TestClient(app)
    payload = {
        "message": {
            "text": "hi",
            "message_id": 1,
            "chat": {"id": 9, "type": "private"},
            "from": {"id": 1, "username": "a"},
        }
    }
    bad = client.post("/api/v1/gateway/telegram/webhook", json=payload)
    assert bad.status_code == 401

    ok = client.post(
        "/api/v1/gateway/telegram/webhook",
        json=payload,
        headers={"X-Telegram-Bot-Api-Secret-Token": "tg-wh"},
    )
    assert ok.status_code == 200
    assert ok.json()["signature"] == "verified"


def test_api_security_middleware_exempts_gateway_webhook(monkeypatch):
    from app.middleware.api_security_mw import ApiSecurityMiddleware

    app = FastAPI()
    app.add_middleware(ApiSecurityMiddleware)

    @app.post("/api/v1/gateway/demo/webhook")
    async def webhook():
        return {"ok": True}

    @app.get("/api/v1/protected")
    async def protected():
        return {"ok": True}

    from app.core.config import settings

    monkeypatch.setattr(settings, "api_token", "secret-token", raising=False)
    monkeypatch.setattr(settings, "console_password", "", raising=False)
    monkeypatch.setattr(settings, "api_rate_limit_per_minute", 0, raising=False)
    client = TestClient(app)

    assert client.get("/api/v1/protected").status_code == 401
    assert client.post("/api/v1/gateway/demo/webhook").status_code == 200

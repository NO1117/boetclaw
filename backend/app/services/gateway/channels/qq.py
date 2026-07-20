"""QQ channel (OneBot-style webhook payloads)."""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

from app.core.observability import EventType, emit_event, get_logger
from app.services.gateway.base import BaseChannel, GatewayMessage, GatewayResponse, RenderStyle
from app.services.gateway.renderer import message_renderer

logger = get_logger("channel.qq")


def _body_bytes(body: Any) -> bytes:
    if body is None:
        return b""
    if isinstance(body, (bytes, bytearray)):
        return bytes(body)
    if isinstance(body, str):
        return body.encode("utf-8")
    import json

    return json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


class QQChannel(BaseChannel):
    channel = "qq"
    render_style = RenderStyle.PLAIN

    def __init__(self, webhook_secret: str = "", reply_url: str = "") -> None:
        self.webhook_secret = webhook_secret
        self.reply_url = reply_url

    def signature_configured(self) -> bool:
        return bool(self.webhook_secret)

    def verify_signature(self, headers: Any = None, body: Any = None, **kwargs: Any) -> bool:
        """OneBot/NapCat-style checks: Bearer secret or ``X-Signature: sha1=<hex>`` HMAC."""
        if not self.webhook_secret:
            return True
        hdrs = headers or {}
        auth = str(hdrs.get("authorization") or hdrs.get("Authorization") or "")
        if auth.lower().startswith("bearer "):
            token = auth[7:].strip()
            if hmac.compare_digest(token, self.webhook_secret):
                return True
        sig = str(hdrs.get("x-signature") or hdrs.get("X-Signature") or "")
        if sig.lower().startswith("sha1="):
            digest = sig.split("=", 1)[1].strip()
            expected = hmac.new(
                self.webhook_secret.encode("utf-8"),
                _body_bytes(body),
                hashlib.sha1,
            ).hexdigest()
            return hmac.compare_digest(digest, expected)
        return False

    async def parse_incoming(self, payload: dict[str, Any]) -> GatewayMessage | None:
        if payload.get("post_type") != "message":
            return None
        is_group = payload.get("message_type") == "group"
        return GatewayMessage(
            platform=self.channel,
            user_id=str(payload.get("user_id", "")),
            user_name=str(payload.get("sender", {}).get("nickname", "QQ User")),
            content=str(payload.get("raw_message", payload.get("message", ""))).strip(),
            message_id=str(payload.get("message_id", "")),
            chat_id=str(payload.get("group_id", payload.get("user_id", ""))),
            raw=payload,
            is_group=is_group,
        )

    async def send_reply(self, message: GatewayMessage, content: str) -> GatewayResponse:
        text = message_renderer.truncate(message_renderer.render(content, self.render_style))
        if self.reply_url:
            try:
                import httpx

                action = "send_group_msg" if message.is_group else "send_private_msg"
                target = {"group_id": message.chat_id} if message.is_group else {"user_id": message.user_id}
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(f"{self.reply_url}/{action}", json={**target, "message": text})
                emit_event(EventType.GATEWAY_MESSAGE, {"platform": self.channel, "action": "reply", "http": resp.status_code})
                return GatewayResponse(success=resp.status_code == 200, content=text)
            except Exception as exc:  # noqa: BLE001
                logger.warning("qq_reply_failed", error=str(exc))
                return GatewayResponse(success=False, content=text, error=str(exc))
        emit_event(EventType.GATEWAY_MESSAGE, {"platform": self.channel, "action": "reply_stub", "user": message.user_id})
        return GatewayResponse(success=True, content=text)

"""DingTalk channel: HMAC verification + real reply via webhook when configured."""

from __future__ import annotations

import base64
import hashlib
import hmac
from typing import Any

from app.core.observability import EventType, emit_event, get_logger
from app.services.gateway.base import BaseChannel, GatewayMessage, GatewayResponse, RenderStyle
from app.services.gateway.renderer import message_renderer

logger = get_logger("channel.dingtalk")


class DingTalkChannel(BaseChannel):
    channel = "dingtalk"
    render_style = RenderStyle.MARKDOWN

    def __init__(self, app_key: str = "", app_secret: str = "", webhook_secret: str = "") -> None:
        self.app_key = app_key
        self.app_secret = app_secret
        self.webhook_secret = webhook_secret

    def is_configured(self) -> bool:
        return bool(self.app_key or self.webhook_secret)

    def signature_configured(self) -> bool:
        return bool(self.webhook_secret)

    def verify_signature(self, headers: Any = None, body: Any = None, **kwargs: Any) -> bool:
        if not self.webhook_secret:
            return True
        hdrs = headers or {}
        timestamp = str(hdrs.get("timestamp") or hdrs.get("Timestamp") or "")
        sign = str(hdrs.get("sign") or hdrs.get("Sign") or "")
        if not timestamp or not sign:
            return False
        string_to_sign = f"{timestamp}\n{self.webhook_secret}"
        hmac_code = hmac.new(
            self.webhook_secret.encode(), string_to_sign.encode(), digestmod=hashlib.sha256
        ).digest()
        expected = base64.b64encode(hmac_code).decode()
        return hmac.compare_digest(expected, sign)

    async def parse_incoming(self, payload: dict[str, Any]) -> GatewayMessage | None:
        if payload.get("msgtype") != "text":
            return None
        text = payload.get("text", {}).get("content", "")
        sender = payload.get("senderNick", payload.get("senderStaffId", "unknown"))
        conversation_type = payload.get("conversationType", "1")
        return GatewayMessage(
            platform=self.channel,
            user_id=payload.get("senderStaffId", ""),
            user_name=sender,
            content=text.strip(),
            message_id=payload.get("msgId", ""),
            chat_id=payload.get("conversationId", ""),
            raw=payload,
            is_group=conversation_type == "2",
        )

    async def send_reply(self, message: GatewayMessage, content: str) -> GatewayResponse:
        text = message_renderer.truncate(message_renderer.render(content, self.render_style))
        session_webhook = message.raw.get("sessionWebhook")
        if session_webhook:
            try:
                import httpx

                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(
                        session_webhook, json={"msgtype": "markdown", "markdown": {"title": "回复", "text": text}}
                    )
                emit_event(EventType.GATEWAY_MESSAGE, {"platform": self.channel, "action": "reply", "http": resp.status_code})
                return GatewayResponse(success=resp.status_code == 200, content=text)
            except Exception as exc:  # noqa: BLE001
                logger.warning("dingtalk_reply_failed", error=str(exc))
                return GatewayResponse(success=False, content=text, error=str(exc))
        emit_event(EventType.GATEWAY_MESSAGE, {"platform": self.channel, "action": "reply_stub", "user": message.user_id})
        return GatewayResponse(success=True, content=text)

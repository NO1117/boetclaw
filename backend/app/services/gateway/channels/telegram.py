"""Telegram channel (Bot API webhook payloads)."""

from __future__ import annotations

import hmac
from typing import Any

from app.core.observability import EventType, emit_event, get_logger
from app.services.gateway.base import BaseChannel, GatewayMessage, GatewayResponse, RenderStyle
from app.services.gateway.renderer import message_renderer

logger = get_logger("channel.telegram")

_TG_BASE = "https://api.telegram.org"


class TelegramChannel(BaseChannel):
    channel = "telegram"
    render_style = RenderStyle.MARKDOWN

    def __init__(self, bot_token: str = "", webhook_secret: str = "") -> None:
        self.bot_token = bot_token
        self.webhook_secret = webhook_secret

    def is_configured(self) -> bool:
        return bool(self.bot_token)

    def signature_configured(self) -> bool:
        return bool(self.webhook_secret)

    def verify_signature(self, headers: Any = None, body: Any = None, **kwargs: Any) -> bool:
        """Compare ``X-Telegram-Bot-Api-Secret-Token`` to ``TELEGRAM_WEBHOOK_SECRET``."""
        if not self.webhook_secret:
            return True
        hdrs = headers or {}
        token = str(
            hdrs.get("x-telegram-bot-api-secret-token")
            or hdrs.get("X-Telegram-Bot-Api-Secret-Token")
            or ""
        )
        if not token:
            return False
        return hmac.compare_digest(token, self.webhook_secret)

    async def parse_incoming(self, payload: dict[str, Any]) -> GatewayMessage | None:
        msg = payload.get("message") or payload.get("edited_message")
        if not msg:
            return None
        text = msg.get("text", "")
        if not text:
            return None
        chat = msg.get("chat", {})
        sender = msg.get("from", {})
        return GatewayMessage(
            platform=self.channel,
            user_id=str(sender.get("id", "")),
            user_name=sender.get("username") or sender.get("first_name", "tg-user"),
            content=text.strip(),
            message_id=str(msg.get("message_id", "")),
            chat_id=str(chat.get("id", "")),
            raw=payload,
            is_group=chat.get("type") in ("group", "supergroup"),
        )

    async def send_reply(self, message: GatewayMessage, content: str) -> GatewayResponse:
        text = message_renderer.truncate(message_renderer.render(content, self.render_style))
        if not self.is_configured():
            emit_event(EventType.GATEWAY_MESSAGE, {"platform": self.channel, "action": "reply_stub", "user": message.user_id})
            return GatewayResponse(success=True, content=text)
        try:
            import httpx

            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{_TG_BASE}/bot{self.bot_token}/sendMessage",
                    json={"chat_id": message.chat_id, "text": text, "parse_mode": "Markdown"},
                )
            emit_event(EventType.GATEWAY_MESSAGE, {"platform": self.channel, "action": "reply", "http": resp.status_code})
            return GatewayResponse(success=resp.status_code == 200, content=text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("telegram_reply_failed", error=str(exc))
            return GatewayResponse(success=False, content=text, error=str(exc))

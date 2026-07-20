"""Feishu (Lark) channel: URL verification + real reply via tenant access token."""

from __future__ import annotations

import hmac
import json
from typing import Any

from app.core.observability import EventType, emit_event, get_logger
from app.services.gateway.base import BaseChannel, GatewayMessage, GatewayResponse, RenderStyle
from app.services.gateway.renderer import message_renderer

logger = get_logger("channel.feishu")

_FEISHU_BASE = "https://open.feishu.cn/open-apis"


def _payload_from_body(body: Any) -> dict[str, Any]:
    if isinstance(body, dict):
        return body
    if isinstance(body, (bytes, bytearray)):
        if not body:
            return {}
        return json.loads(body.decode("utf-8"))
    if isinstance(body, str):
        if not body:
            return {}
        return json.loads(body)
    return {}


class FeishuChannel(BaseChannel):
    channel = "feishu"
    render_style = RenderStyle.MARKDOWN

    def __init__(self, app_id: str = "", app_secret: str = "", verification_token: str = "") -> None:
        self.app_id = app_id
        self.app_secret = app_secret
        self.verification_token = verification_token

    def is_configured(self) -> bool:
        return bool(self.app_id and self.app_secret)

    def signature_configured(self) -> bool:
        return bool(self.verification_token)

    def verify_signature(self, headers: Any = None, body: Any = None, **kwargs: Any) -> bool:
        """Check Feishu Verification Token in JSON body (v1 ``token`` or v2 ``header.token``).

        Encrypt-key decryption is not implemented: Settings has no encrypt key field.
        """
        if not self.verification_token:
            return True
        try:
            payload = _payload_from_body(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return False
        token = str(payload.get("token") or payload.get("header", {}).get("token") or "")
        if not token:
            return False
        return hmac.compare_digest(token, self.verification_token)

    async def parse_incoming(self, payload: dict[str, Any]) -> GatewayMessage | None:
        header = payload.get("header", {})
        event = payload.get("event", {})
        if header.get("event_type") != "im.message.receive_v1":
            return None
        message = event.get("message", {})
        sender = event.get("sender", {}).get("sender_id", {})
        content_raw = message.get("content", "{}")
        try:
            text = json.loads(content_raw).get("text", "")
        except json.JSONDecodeError:
            text = content_raw
        return GatewayMessage(
            platform=self.channel,
            user_id=sender.get("open_id", ""),
            user_name=sender.get("open_id", "user"),
            content=text.strip(),
            message_id=message.get("message_id", ""),
            chat_id=message.get("chat_id", ""),
            raw=payload,
            is_group=message.get("chat_type") == "group",
        )

    async def _get_tenant_token(self, client: Any) -> str:
        resp = await client.post(
            f"{_FEISHU_BASE}/auth/v3/tenant_access_token/internal",
            json={"app_id": self.app_id, "app_secret": self.app_secret},
        )
        return resp.json().get("tenant_access_token", "")

    async def send_reply(self, message: GatewayMessage, content: str) -> GatewayResponse:
        text = message_renderer.truncate(message_renderer.render(content, self.render_style))
        if not self.is_configured() or not message.message_id:
            emit_event(EventType.GATEWAY_MESSAGE, {"platform": self.channel, "action": "reply_stub", "user": message.user_id})
            return GatewayResponse(success=True, content=text)
        try:
            import httpx

            async with httpx.AsyncClient(timeout=10.0) as client:
                token = await self._get_tenant_token(client)
                resp = await client.post(
                    f"{_FEISHU_BASE}/im/v1/messages/{message.message_id}/reply",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"msg_type": "text", "content": json.dumps({"text": text})},
                )
            emit_event(EventType.GATEWAY_MESSAGE, {"platform": self.channel, "action": "reply", "http": resp.status_code})
            return GatewayResponse(success=resp.status_code == 200, content=text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("feishu_reply_failed", error=str(exc))
            return GatewayResponse(success=False, content=text, error=str(exc))

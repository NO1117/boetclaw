"""Channel manager: registry + per-channel bounded queues + batch consumers."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from app.core.config import settings
from app.core.observability import EventType, emit_event, get_logger
from app.services.gateway.access_control import access_control_store
from app.services.gateway.base import BaseChannel, GatewayMessage
from app.services.gateway.channels.dingtalk import DingTalkChannel
from app.services.gateway.channels.feishu import FeishuChannel
from app.services.gateway.channels.qq import QQChannel
from app.services.gateway.channels.telegram import TelegramChannel

logger = get_logger("channel_manager")

QUEUE_MAXSIZE = 1000

# handler(channel, message) -> awaitable
MessageHandler = Callable[[BaseChannel, GatewayMessage], Awaitable[None]]


class ChannelManager:
    """Registers channels, buffers inbound messages, and drives consumers."""

    def __init__(self, history_path: Path | None = None) -> None:
        self._channels: dict[str, BaseChannel] = {}
        self._queues: dict[str, asyncio.Queue] = {}
        self._consumers: dict[str, asyncio.Task] = {}
        self._handler: MessageHandler | None = None
        self._running = False
        self.history_path = history_path or (settings.workspace_dir / "gateway" / "message_history.json")
        self._history: list[dict[str, Any]] = self._load_history()
        self._rate_hits: dict[str, deque[float]] = defaultdict(deque)

    def _public_record(self, record: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in record.items() if k != "_message"}

    def _load_history(self) -> list[dict[str, Any]]:
        if not self.history_path.exists():
            return []
        try:
            rows = json.loads(self.history_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(rows, list):
            return []
        return [row for row in rows if isinstance(row, dict)][:500]

    def _save_history(self) -> None:
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        rows = [self._public_record(row) for row in self._history[:500]]
        self.history_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    # ----- registration -----
    def register(self, channel: BaseChannel) -> None:
        self._channels[channel.channel] = channel
        self._queues.setdefault(channel.channel, asyncio.Queue(maxsize=QUEUE_MAXSIZE))

    def get(self, name: str) -> BaseChannel | None:
        return self._channels.get(name)

    def list_channels(self) -> list[str]:
        return list(self._channels.keys())

    def status(self) -> list[dict[str, Any]]:
        return [
            {
                "name": name,
                "configured": channel.is_configured(),
                "queue_depth": self.queue_size(name),
                "running": self._running,
                "consumer_running": name in self._consumers and not self._consumers[name].done(),
                "render_style": channel.render_style.value,
            }
            for name, channel in self._channels.items()
        ]

    def set_handler(self, handler: MessageHandler) -> None:
        self._handler = handler

    # ----- queueing -----
    def is_allowed(self, name: str, message: GatewayMessage) -> bool:
        return access_control_store.is_allowed(name, message.user_id)

    def _rate_key(self, name: str, message: GatewayMessage) -> str:
        user_key = message.user_id or message.chat_id or "unknown"
        return f"{name}:{user_key}"

    def _rate_limited(self, name: str, message: GatewayMessage, *, consume: bool) -> bool:
        limit = settings.gateway_rate_limit_per_minute
        if limit <= 0:
            return False
        key = self._rate_key(name, message)
        now = time.monotonic()
        window_start = now - 60
        hits = self._rate_hits[key]
        while hits and hits[0] < window_start:
            hits.popleft()
        if len(hits) >= limit:
            return True
        if consume:
            hits.append(now)
        return False

    def is_rate_limited(self, name: str, message: GatewayMessage) -> bool:
        return self._rate_limited(name, message, consume=False)

    def consume_rate_limit(self, name: str, message: GatewayMessage) -> bool:
        return self._rate_limited(name, message, consume=True)

    def record_access_denied(self, name: str, message: GatewayMessage) -> dict[str, Any]:
        emit_event(
            EventType.GATEWAY_MESSAGE,
            {
                "platform": name,
                "action": "denied",
                "reason": "user_not_allowed",
                "user_id": message.user_id,
            },
        )
        return self.record_message(name, message, "denied", "user_not_allowed")

    def record_rate_limited(self, name: str, message: GatewayMessage) -> dict[str, Any]:
        emit_event(
            EventType.GATEWAY_MESSAGE,
            {
                "platform": name,
                "action": "rate_limited",
                "reason": "user_rate_limit",
                "user_id": message.user_id,
            },
        )
        return self.record_message(name, message, "rate_limited", "user_rate_limit")

    def enqueue(self, name: str, message: GatewayMessage) -> bool:
        """Enqueue an inbound message. Returns False if dropped (queue full/unknown)."""
        if not self.is_allowed(name, message):
            self.record_access_denied(name, message)
            logger.warning("gateway_user_denied", channel=name, user_id=message.user_id)
            return False
        if self.consume_rate_limit(name, message):
            self.record_rate_limited(name, message)
            logger.warning("gateway_user_rate_limited", channel=name, user_id=message.user_id)
            return False
        q = self._queues.get(name)
        if q is None:
            logger.warning("enqueue_unknown_channel", channel=name)
            self.record_message(name, message, "failed", "unknown_channel")
            return False
        try:
            q.put_nowait(message)
            self.record_message(name, message, "queued", "message queued")
            return True
        except asyncio.QueueFull:
            emit_event(EventType.GATEWAY_MESSAGE, {"platform": name, "action": "dropped", "reason": "queue_full"})
            logger.warning("queue_full_drop", channel=name)
            self.record_message(name, message, "failed", "queue_full")
            return False

    def queue_size(self, name: str) -> int:
        q = self._queues.get(name)
        return q.qsize() if q else 0

    def record_message(
        self,
        platform: str,
        message: GatewayMessage,
        status: str,
        detail: str = "",
        *,
        task_id: str = "",
        trace_id: str = "",
    ) -> dict[str, Any]:
        record = {
            "id": uuid.uuid4().hex[:12],
            "platform": platform,
            "status": status,
            "detail": detail,
            "message_id": message.message_id,
            "chat_id": message.chat_id,
            "user_id": message.user_id,
            "user_name": message.user_name,
            "content": message.content[:500],
            "task_id": task_id,
            "trace_id": trace_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "_message": message,
        }
        self._history.insert(0, record)
        self._history = self._history[:500]
        self._save_history()
        return record

    def message_history(self, platform: str = "", status: str = "", limit: int = 100) -> list[dict[str, Any]]:
        rows = [
            r for r in self._history
            if (not platform or r["platform"] == platform) and (not status or r["status"] == status)
        ][:limit]
        return [self._public_record(r) for r in rows]

    def retry_message(self, record_id: str) -> bool:
        for record in self._history:
            if record["id"] == record_id:
                message = record.get("_message")
                if not isinstance(message, GatewayMessage):
                    return False
                return self.enqueue(record["platform"], message)
        return False

    # ----- consumers -----
    async def _consume(self, name: str) -> None:
        q = self._queues[name]
        channel = self._channels[name]
        while self._running:
            try:
                message = await q.get()
            except asyncio.CancelledError:  # pragma: no cover
                break
            try:
                if self._handler is not None:
                    await self._handler(channel, message)
            except Exception as exc:  # noqa: BLE001
                logger.warning("consumer_error", channel=name, error=str(exc))
            finally:
                q.task_done()

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        for name in self._channels:
            self._consumers[name] = asyncio.create_task(self._consume(name))
        logger.info("channel_manager_started", channels=list(self._channels.keys()))

    async def stop(self) -> None:
        self._running = False
        for task in self._consumers.values():
            task.cancel()
        self._consumers.clear()

    def bootstrap_from_settings(self) -> None:
        """Register channels that have credentials configured (plus always-on ones)."""
        self.register(
            DingTalkChannel(
                app_key=settings.dingtalk_app_key,
                app_secret=settings.dingtalk_app_secret,
                webhook_secret=settings.dingtalk_webhook_secret,
            )
        )
        self.register(
            FeishuChannel(
                app_id=settings.feishu_app_id,
                app_secret=settings.feishu_app_secret,
                verification_token=settings.feishu_verification_token,
            )
        )
        self.register(QQChannel(webhook_secret=settings.qq_webhook_secret))
        self.register(
            TelegramChannel(
                bot_token=getattr(settings, "telegram_bot_token", ""),
                webhook_secret=getattr(settings, "telegram_webhook_secret", ""),
            )
        )


channel_manager = ChannelManager()

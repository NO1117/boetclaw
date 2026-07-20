"""Gateway webhook routes backed by ChannelManager (DingTalk/Feishu/QQ/Telegram)."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from app.api.schemas import GatewayWebhookResponse
from app.core.agent import agent_manager
from app.core.observability import get_logger, new_run_id, new_trace_id
from app.services.gateway.access_control import access_control_store
from app.services.gateway.base import BaseChannel, GatewayMessage
from app.services.gateway.manager import channel_manager
from app.services.run_registry import run_registry
from app.services.task_scheduler import TaskStatus, task_scheduler

logger = get_logger("gateway.webhook")

router = APIRouter(prefix="/gateway", tags=["Gateway"])

_PLATFORM_LABELS = {"dingtalk": "钉钉", "feishu": "飞书", "qq": "QQ", "telegram": "Telegram"}


async def default_message_handler(channel: BaseChannel, message: GatewayMessage) -> None:
    """Consume an inbound channel message: run the agent and reply."""
    label = _PLATFORM_LABELS.get(channel.channel, channel.channel)
    task = task_scheduler.create(
        title=f"[{label}] {message.content[:50]}",
        prompt=message.content,
        gateway=channel.channel,
        gateway_user=message.user_id,
        metadata={"chat_id": message.chat_id, "message_id": message.message_id},
    )
    trace_id = new_trace_id()
    run_id = new_run_id()

    async def execute() -> None:
        task_scheduler.update_status(
            task.id,
            TaskStatus.RUNNING,
            expected={TaskStatus.PENDING},
            trace_id=trace_id,
            run_id=run_id,
        )
        try:
            result = await agent_manager.invoke(
                message.content,
                task.thread_id,
                source="channel",
                trace_id=trace_id,
                run_id=run_id,
                task_id=task.id,
            )
            response_text = str(result.get("response", ""))
            task_scheduler.update_status(
                task.id,
                TaskStatus.COMPLETED,
                expected={TaskStatus.RUNNING},
                result=response_text,
                trace_id=trace_id,
                run_id=run_id,
            )
            reply = await channel.send_reply(message, response_text)
            channel_manager.record_message(
                channel.channel,
                message,
                "replied" if reply.success else "failed",
                reply.error or "reply sent",
                task_id=task.id,
                trace_id=trace_id,
            )
        except asyncio.CancelledError:
            task_scheduler.update_status(
                task.id,
                TaskStatus.CANCELLED,
                expected={TaskStatus.PENDING, TaskStatus.RUNNING, TaskStatus.CANCELLING},
                trace_id=trace_id,
                run_id=run_id,
            )
            channel_manager.record_message(
                channel.channel,
                message,
                "cancelled",
                "run cancelled",
                task_id=task.id,
                trace_id=trace_id,
            )
            raise
        except Exception as exc:  # noqa: BLE001
            task_scheduler.update_status(
                task.id,
                TaskStatus.FAILED,
                expected={TaskStatus.PENDING, TaskStatus.RUNNING},
                error=str(exc),
                trace_id=trace_id,
                run_id=run_id,
            )
            channel_manager.record_message(channel.channel, message, "failed", str(exc), task_id=task.id)

    entry = run_registry.start(
        execute(),
        agent_id="default",
        thread_id=task.thread_id,
        run_id=run_id,
        task_id=task.id,
        trace_id=trace_id,
    )
    execution_task = entry.task
    if execution_task is not None:
        try:
            await execution_task
        except asyncio.CancelledError:
            return


channel_manager.set_handler(default_message_handler)


def _signature_status(channel: BaseChannel) -> str:
    configured = getattr(channel, "signature_configured", None)
    if callable(configured) and configured():
        return "verified"
    return "skipped"


async def _handle_webhook(request: Request, background_tasks: BackgroundTasks, platform: str) -> dict:
    channel = channel_manager.get(platform)
    if channel is None:
        raise HTTPException(status_code=503, detail=f"{platform} channel not configured")

    body = await request.body()
    verify = getattr(channel, "verify_signature", None)
    if callable(verify) and not verify(request.headers, body):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    sig = _signature_status(channel)
    if sig == "skipped":
        logger.info("webhook_signature_skipped", platform=platform)

    try:
        payload = json.loads(body) if body else {}
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="JSON body must be an object")

    # Feishu URL verification handshake
    if platform == "feishu" and payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge", ""), "signature": sig}

    message = await channel.parse_incoming(payload)
    if not message or not message.content:
        return GatewayWebhookResponse(success=True, message="Ignored", signature=sig).model_dump()

    if not channel_manager.is_allowed(platform, message):
        channel_manager.record_access_denied(platform, message)
        return GatewayWebhookResponse(success=True, message="Denied by access control", signature=sig).model_dump()
    if channel_manager.is_rate_limited(platform, message):
        channel_manager.record_rate_limited(platform, message)
        return GatewayWebhookResponse(success=True, message="Rate limited", signature=sig).model_dump()

    # Prefer the async queue; fall back to background task if consumers are idle.
    queued = channel_manager.enqueue(platform, message)
    if not queued:
        background_tasks.add_task(default_message_handler, channel, message)
        return GatewayWebhookResponse(success=True, message="Queued (fallback)", signature=sig).model_dump()
    return GatewayWebhookResponse(success=True, message="Task queued", signature=sig).model_dump()


@router.get("/platforms")
async def list_platforms():
    return {"platforms": channel_manager.list_channels()}


@router.get("/status")
async def gateway_status():
    return {"channels": channel_manager.status()}


@router.get("/access-control")
async def get_gateway_access_control():
    return access_control_store.list()


@router.put("/access-control")
async def update_gateway_access_control(payload: dict):
    channels = payload.get("channels", {})
    if not isinstance(channels, dict):
        raise HTTPException(status_code=400, detail="channels must be an object")
    return access_control_store.update(channels)


@router.get("/messages")
async def gateway_messages(platform: str = "", status: str = "", limit: int = 100):
    return {"messages": channel_manager.message_history(platform=platform, status=status, limit=limit)}


@router.post("/messages/{record_id}/retry")
async def retry_gateway_message(record_id: str):
    ok = channel_manager.retry_message(record_id)
    if not ok:
        raise HTTPException(status_code=404, detail="message record not found or cannot retry")
    return {"retried": record_id}


@router.post("/dingtalk/webhook", response_model=GatewayWebhookResponse)
async def dingtalk_webhook(request: Request, background_tasks: BackgroundTasks):
    return await _handle_webhook(request, background_tasks, "dingtalk")


@router.post("/feishu/webhook")
async def feishu_webhook(request: Request, background_tasks: BackgroundTasks):
    return await _handle_webhook(request, background_tasks, "feishu")


@router.post("/qq/webhook", response_model=GatewayWebhookResponse)
async def qq_webhook(request: Request, background_tasks: BackgroundTasks):
    return await _handle_webhook(request, background_tasks, "qq")


@router.post("/telegram/webhook", response_model=GatewayWebhookResponse)
async def telegram_webhook(request: Request, background_tasks: BackgroundTasks):
    return await _handle_webhook(request, background_tasks, "telegram")


@router.post("/{platform}/webhook", response_model=GatewayWebhookResponse)
async def generic_webhook(platform: str, request: Request, background_tasks: BackgroundTasks):
    return await _handle_webhook(request, background_tasks, platform)

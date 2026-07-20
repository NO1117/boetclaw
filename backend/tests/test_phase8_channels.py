"""Phase 8 tests: channel parsing, renderer, manager queue behavior."""

import asyncio

import pytest

from app.services.gateway.base import GatewayMessage, RenderStyle
from app.services.gateway.channels.dingtalk import DingTalkChannel
from app.services.gateway.channels.feishu import FeishuChannel
from app.services.gateway.channels.qq import QQChannel
from app.services.gateway.channels.telegram import TelegramChannel


@pytest.mark.asyncio
async def test_dingtalk_parse():
    ch = DingTalkChannel()
    msg = await ch.parse_incoming(
        {"msgtype": "text", "text": {"content": "钻井日报"}, "senderStaffId": "u1", "conversationId": "c1", "conversationType": "2"}
    )
    assert msg is not None
    assert msg.content == "钻井日报"
    assert msg.is_group is True


@pytest.mark.asyncio
async def test_feishu_parse():
    ch = FeishuChannel()
    payload = {
        "header": {"event_type": "im.message.receive_v1"},
        "event": {
            "sender": {"sender_id": {"open_id": "ou_x"}},
            "message": {"content": '{"text": "生成图表"}', "message_id": "m1", "chat_id": "c1", "chat_type": "group"},
        },
    }
    msg = await ch.parse_incoming(payload)
    assert msg is not None and msg.content == "生成图表"
    assert msg.user_id == "ou_x"


@pytest.mark.asyncio
async def test_qq_parse():
    ch = QQChannel()
    msg = await ch.parse_incoming(
        {"post_type": "message", "message_type": "group", "user_id": 123, "group_id": 456, "raw_message": "hi", "sender": {"nickname": "n"}}
    )
    assert msg is not None and msg.content == "hi"
    assert msg.is_group is True and msg.chat_id == "456"


@pytest.mark.asyncio
async def test_telegram_parse():
    ch = TelegramChannel()
    msg = await ch.parse_incoming(
        {"message": {"text": "hello", "message_id": 7, "chat": {"id": -100, "type": "supergroup"}, "from": {"id": 9, "username": "bob"}}}
    )
    assert msg is not None and msg.content == "hello"
    assert msg.is_group is True


@pytest.mark.asyncio
async def test_parse_ignores_non_message():
    ch = QQChannel()
    assert await ch.parse_incoming({"post_type": "notice"}) is None


def test_renderer_plain_strips_markdown():
    from app.services.gateway.renderer import message_renderer

    out = message_renderer.render("# Title\n**bold** and `code`", RenderStyle.PLAIN)
    assert "**" not in out and "`" not in out and "# " not in out


def test_renderer_truncate():
    from app.services.gateway.renderer import message_renderer

    out = message_renderer.truncate("x" * 5000, limit=100)
    assert len(out) <= 100 and "截断" in out


@pytest.mark.asyncio
async def test_manager_queue_full_drops():
    from app.services.gateway.manager import ChannelManager

    mgr = ChannelManager()
    ch = QQChannel()
    mgr.register(ch)
    # shrink the queue to force overflow
    mgr._queues["qq"] = asyncio.Queue(maxsize=2)

    m = GatewayMessage(platform="qq", user_id="1", user_name="n", content="c", message_id="1", chat_id="1")
    assert mgr.enqueue("qq", m) is True
    assert mgr.enqueue("qq", m) is True
    # third exceeds maxsize -> dropped
    assert mgr.enqueue("qq", m) is False
    assert mgr.enqueue("unknown", m) is False


@pytest.mark.asyncio
async def test_manager_consumer_processes():
    from app.services.gateway.manager import ChannelManager

    mgr = ChannelManager()
    mgr.register(QQChannel())
    seen: list[str] = []

    async def handler(channel, message):
        seen.append(message.content)

    mgr.set_handler(handler)
    await mgr.start()
    m = GatewayMessage(platform="qq", user_id="1", user_name="n", content="ping", message_id="1", chat_id="1")
    mgr.enqueue("qq", m)
    await asyncio.sleep(0.05)
    await mgr.stop()
    assert "ping" in seen

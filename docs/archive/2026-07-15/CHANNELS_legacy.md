# 渠道接入说明

BoetClaw 通过 `BaseChannel` 抽象统一处理钉钉、飞书、QQ（OneBot/NapCat）和 Telegram。Webhook 进入后会被解析为 `GatewayMessage`，放入每渠道独立队列，再由消费者调用 Agent 并回发。

## 通用流程

1. 在平台配置 webhook URL。
2. 在 `backend/.env` 填入对应凭据。
3. 启动服务。
4. 平台消息进入 `/api/v1/gateway/{platform}/webhook`。
5. `ChannelManager` 入队并触发 `source="channel"` 的 Agent 调用。

## 钉钉

Webhook URL：

```text
http(s)://<host>/api/v1/gateway/dingtalk/webhook
```

配置：

```env
DINGTALK_APP_KEY=
DINGTALK_APP_SECRET=
DINGTALK_WEBHOOK_SECRET=
```

回发优先使用钉钉 payload 中的 `sessionWebhook`。未提供时进入 stub 回发（只记录事件，不发真实消息）。

## 飞书

Webhook URL：

```text
http(s)://<host>/api/v1/gateway/feishu/webhook
```

配置：

```env
FEISHU_APP_ID=
FEISHU_APP_SECRET=
FEISHU_VERIFICATION_TOKEN=
```

飞书 URL verification 会直接返回 `challenge`。真实回发会先获取 `tenant_access_token`，再调用消息回复 API。

## QQ（OneBot / NapCat）

Webhook URL：

```text
http(s)://<host>/api/v1/gateway/qq/webhook
```

配置：

```env
QQ_WEBHOOK_SECRET=
```

当前回发支持 OneBot 风格 `send_group_msg` / `send_private_msg`，未配置回发地址时走 stub。

## Telegram

Webhook URL：

```text
http(s)://<host>/api/v1/gateway/telegram/webhook
```

配置：

```env
TELEGRAM_BOT_TOKEN=
```

使用 Bot API `sendMessage` 回发。

## 队列与降级

每个渠道拥有 `asyncio.Queue(maxsize=1000)`：

- 正常：Webhook 解析后入队，快速返回。
- 队列满：记录 `gateway_message` dropped 事件，并降级到 FastAPI `BackgroundTask`。
- 无凭据：解析仍可用，回发降级为 stub。

## 本地模拟

```bash
curl -X POST http://localhost:8000/api/v1/gateway/qq/webhook \
  -H "Content-Type: application/json" \
  -d '{"post_type":"message","message_type":"private","user_id":1,"raw_message":"生成日报"}'
```

# 渠道接入说明

> 文档基线：2026-07-17（PLAN-620 验签接入）。

当前网关通过 `BaseChannel` 和 `ChannelManager` 统一处理钉钉、飞书、QQ（OneBot/NapCat）
和 Telegram。四个渠道在启动时都会注册，即使没有凭据；`GET /api/v1/gateway/status`
中的 `configured` 只表示渠道类认为凭据充分，不表示 webhook 已完成真实平台联调。

## 通用处理链路

1. 平台向 `/api/v1/gateway/{platform}/webhook` 发送 JSON。
2. 路由读取 raw body，调用 `channel.verify_signature(headers, body)`；失败返回 401。
3. 渠道解析器把支持的事件转换为 `GatewayMessage`；非消息或空内容返回 `Ignored`。
4. 路由检查渠道用户白名单和用户级限流。
5. 消息进入该渠道的内存队列。
6. 消费者创建持久化任务，以 `source="channel"` 调用 Agent，再调用渠道回发。
7. 处理状态写入消息历史。

还存在通用的 `POST /api/v1/gateway/{platform}/webhook` 路由，但未知平台会返回 503。

### 两层鉴权

| 层 | 作用范围 | 行为 |
|---|---|---|
| `ApiSecurityMiddleware` | 绝大多数 `/api/v1/*` | 配置 `API_TOKEN`/`CONSOLE_PASSWORD` 时要求 Bearer/`X-API-Token`/Console JWT |
| 平台 webhook 验签 | `POST /api/v1/gateway/*/webhook` | **豁免**中间件 HTTP 鉴权；依赖各渠道 `verify_signature` |

未配置对应平台密钥时验签放行（本地开发），响应带 `signature=skipped` 并打 info 日志；配置密钥后强制校验，成功为 `signature=verified`。

## 四个渠道

### 钉钉

```text
POST /api/v1/gateway/dingtalk/webhook
```

```env
DINGTALK_APP_KEY=
DINGTALK_APP_SECRET=
DINGTALK_WEBHOOK_SECRET=
```

仅解析 `msgtype=text`。回发使用入站 payload 中的 `sessionWebhook`；没有该字段时返回 stub 成功，
只记录事件，不发送真实消息。配置 `DINGTALK_WEBHOOK_SECRET` 时校验请求头 `timestamp` + `sign`
（HMAC-SHA256，与钉钉文档一致）；未配置则 `signature=skipped`。

### 飞书

```text
POST /api/v1/gateway/feishu/webhook
```

```env
FEISHU_APP_ID=
FEISHU_APP_SECRET=
FEISHU_VERIFICATION_TOKEN=
```

URL verification 在验签通过后返回 `challenge`。配置 `FEISHU_VERIFICATION_TOKEN` 时校验
body 的 `token`（或事件 v2 的 `header.token`）。消息解析只接受 `im.message.receive_v1`。
配置 app id/secret 且有 `message_id` 时，回发先获取 `tenant_access_token`，再调用消息
reply API；否则走 stub。

项目 Settings 无飞书 encrypt key 字段，**不**实现加密事件解密；明文/已解密 payload 才可解析。

### QQ（OneBot / NapCat）

```text
POST /api/v1/gateway/qq/webhook
```

```env
QQ_WEBHOOK_SECRET=
```

解析 `post_type=message`，支持群聊和私聊字段。`QQChannel` 类在显式传入 `reply_url`
时可调用 `send_group_msg` 或 `send_private_msg`，但当前 Settings 和启动注册流程没有
QQ reply URL 配置项，因此按现行默认启动路径回发始终是 stub。

配置 `QQ_WEBHOOK_SECRET` 时接受其一：`Authorization: Bearer <secret>`，或 OneBot 常见
`X-Signature: sha1=<hmac-sha1(body)>`。未配置则跳过。

### Telegram

```text
POST /api/v1/gateway/telegram/webhook
```

```env
TELEGRAM_BOT_TOKEN=
TELEGRAM_WEBHOOK_SECRET=
```

解析 `message` 和 `edited_message` 中的文本。配置 bot token 后通过 Bot API
`sendMessage` 回发；未配置时走 stub。配置 `TELEGRAM_WEBHOOK_SECRET` 时校验请求头
`X-Telegram-Bot-Api-Secret-Token`（与 `setWebhook` 的 `secret_token` 对应）。

## 队列与 fallback

每个渠道有独立的 `asyncio.Queue(maxsize=1000)`：

- 队列和消费者都在单个后端进程内，不持久化，也不跨 worker/副本共享。
- 正常入队会记录 `queued` 并快速返回 `Task queued`。
- 队列满时，`enqueue()` 记录 `failed/queue_full` 和 dropped 事件；路由随后使用 FastAPI
  `BackgroundTasks` 直接执行同一处理器，并返回 `Queued (fallback)`。
- fallback 不提供外部队列的耐久性、背压或进程崩溃恢复能力。
- 消费者捕获处理异常并记录；没有自动指数退避或死信队列。

由于四渠道始终注册，“无凭据”通常不会阻止入站解析和 Agent 执行，只会影响真实回发。
生产环境不要把 `configured=false` 当作入站关闭开关。

## 渠道白名单

访问控制 API：

```text
GET /api/v1/gateway/access-control
PUT /api/v1/gateway/access-control
```

策略持久化到：

```text
backend/workspace/access_control.json
```

实际路径跟随 `WORKSPACE_DIR`。数据格式示例：

```json
{
  "channels": {
    "dingtalk": {"allowed_users": ["staff-id-1"]},
    "feishu": {"allowed_users": ["ou_xxx"]},
    "qq": {"allowed_users": ["10001"]},
    "telegram": {"allowed_users": ["123456789"]}
  }
}
```

用户 ID 会规范化为字符串并精确匹配。某渠道配置缺失或 `allowed_users` 为空时默认开放。
要限制公网 webhook，必须为每个启用渠道设置非空列表；白名单不能替代平台签名验证。

## 用户级限流

```env
GATEWAY_RATE_LIMIT_PER_MINUTE=0
```

值大于 0 时，使用 60 秒进程内窗口，按“渠道 + user_id”分桶；user_id 为空时回退到 chat_id，
再为空时使用 `unknown`。超限消息记录为 `rate_limited/user_rate_limit`，路由仍返回 HTTP 成功
响应和 `Rate limited` 文本，避免平台盲目重投。

值为 0 时关闭。该限流重启即清空，多进程/多副本不共享。

## 消息历史与重试

消息历史 API：

```text
GET  /api/v1/gateway/messages?platform=&status=&limit=100
POST /api/v1/gateway/messages/{record_id}/retry
```

历史默认保存在：

```text
backend/workspace/gateway/message_history.json
```

实际路径跟随 `WORKSPACE_DIR`。最多保留最近 500 条，每条包含平台、状态、用户/会话 ID、
最多 500 字符内容、任务/trace ID 和时间。文件未加密，应按敏感数据管理。

运行中的进程会在内存记录里保留原始 `GatewayMessage`，因此可重新入队。写盘时该对象会被移除，
服务重启后加载的记录不能重试，重试 API 会返回 404。重试仍会重新经过白名单和限流。
当前没有自动重试次数、退避、幂等去重或平台 message_id 去重。

## stub 行为

stub 表示“没有向外部平台发送，但渠道方法返回 `success=True` 并记录 `reply_stub` 事件”。
因此上层消息历史可能记录为 `replied`，不能仅凭该状态断言用户实际收到消息。

- 钉钉：缺少 `sessionWebhook` 时 stub。
- 飞书：凭据不足或缺少 message_id 时 stub。
- QQ：未提供构造参数 `reply_url` 时 stub；现行配置路径不会提供该参数。
- Telegram：未配置 bot token 时 stub。

## 本地模拟

本地开发默认 API 可能未鉴权、渠道白名单可能为空。以下请求会触发 Agent 处理，QQ 回发为 stub：

```bash
curl -X POST http://localhost:8000/api/v1/gateway/qq/webhook \
  -H "Content-Type: application/json" \
  -d '{"post_type":"message","message_type":"private","user_id":1,"raw_message":"生成日报"}'
```

如已设置 `API_TOKEN`，还需添加：

```text
Authorization: Bearer <API_TOKEN>
```

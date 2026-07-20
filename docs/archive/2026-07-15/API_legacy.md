# BoetClaw API 索引

默认前缀：`/api/v1`

## Agent

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/agent/chat` | 同步对话，支持 `agent_id`、`source` |
| `POST` | `/agent/chat/stream` | SSE 流式对话 |
| `POST` | `/agent/plan/confirm` | 计划确认/拒绝/编辑后继续 |
| `GET` | `/agent/tools` | 当前可用工具 |
| `GET` | `/agent/trace/{trace_id}` | trace 事件 |
| `GET` | `/agent/trace/run/{run_id}` | run 事件 |

## Monitoring

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/monitor/health` | 就绪状态 |
| `GET` | `/monitor/stats` | 任务与事件统计 |
| `GET` | `/monitor/events` | 最近事件 |
| `GET` | `/monitor/trace/{trace_id}/timeline` | 结构化时间线 |

## Tasks / Cron / Heartbeat

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/tasks` | 创建任务 |
| `GET` | `/tasks` | 任务列表 |
| `GET` | `/tasks/{task_id}` | 任务详情 |
| `POST` | `/tasks/{task_id}/run` | 重新运行 |
| `POST` | `/tasks/{task_id}/cancel` | 取消 |
| `GET` | `/tasks/cron` | Cron 任务列表 |
| `POST` | `/tasks/cron` | 新建 Cron 任务 |
| `DELETE` | `/tasks/cron/{job_id}` | 删除 Cron 任务 |
| `GET` | `/tasks/heartbeat` | 心跳配置 |
| `PUT` | `/tasks/heartbeat` | 更新心跳配置 |

## Skills / Agents / Providers

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/skills` | 技能池与工作区技能 |
| `POST` | `/skills/install` | 安装技能到全局池 |
| `POST` | `/skills/{name}/add-to-workspace` | 添加到指定 agent 工作区 |
| `POST` | `/skills/{name}/enable` | 启停工作区技能 |
| `POST` | `/skills/scan` | 扫描技能目录 |
| `GET` | `/agents` | Agent 工作区列表 |
| `POST` | `/agents` | 创建 Agent 工作区 |
| `GET` | `/agents/{agent_id}` | Agent 详情 |
| `DELETE` | `/agents/{agent_id}` | 删除 Agent（默认 Agent 不可删） |
| `GET` | `/providers` | Provider 列表 |
| `GET` | `/providers/{name}/models` | Provider 模型列表 |
| `POST` | `/providers/{name}/check` | Provider 连通性检测 |

## Security / Plugins / Gateway

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/security/config` | ToolGuard 配置 |
| `PUT` | `/security/config` | 更新 ToolGuard 级别 |
| `GET` | `/security/approvals` | 待审批工具调用 |
| `POST` | `/security/approvals/resume` | 审批后恢复 |
| `GET` | `/plugins` | 插件列表 |
| `POST` | `/plugins/reload` | 重载插件 |
| `GET` | `/commands` | `/slash` 命令列表 |
| `GET` | `/gateway/platforms` | 渠道列表 |
| `POST` | `/gateway/{platform}/webhook` | 通用渠道 webhook |
| `POST` | `/gateway/dingtalk/webhook` | 钉钉 webhook |
| `POST` | `/gateway/feishu/webhook` | 飞书 webhook |
| `POST` | `/gateway/qq/webhook` | QQ webhook |
| `POST` | `/gateway/telegram/webhook` | Telegram webhook |

## 常用请求示例

```bash
curl -X POST http://localhost:8000/api/v1/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"/plan 生成钻井日报","thread_id":"demo","source":"user"}'
```

```bash
curl -X POST http://localhost:8000/api/v1/tasks/cron \
  -H "Content-Type: application/json" \
  -d '{"name":"日报","cron":"0 8 * * *","prompt":"汇总昨日钻井日报"}'
```

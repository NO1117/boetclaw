# 安全设计

BoetClaw 的安全目标是：默认不执行高风险动作、敏感路径不可访问、插件默认不加载、工具风险可审批。

## ToolGuard

ToolGuard 由三类 guardian 组成：

- `RuleBasedToolGuardian`：按工具名识别高风险工具和显式拒绝工具。
- `FilePathToolGuardian`：扫描常见路径参数，阻止访问 `.env`、`.git`、`.ssh` 等敏感目录。
- `ShellEvasionGuardian`：识别 shell 混淆、危险命令、`rm -rf` 等模式。

配置：

```env
TOOL_GUARD_ENABLED=true
TOOL_GUARD_LEVEL=smart
TOOL_GUARD_DENIED_TOOLS=
FILE_GUARD_DENY_DIRS=.env,.git,.ssh,.qwenpaw.secret
```

级别：

- `strict`：风险工具直接阻断。
- `smart`：中高风险进入人工审批。
- `auto`：尽量自动放行，仅严重风险阻断。
- `off`：关闭安全策略（不建议生产使用）。

## 人工审批

当工具调用需要审批时：

1. `ToolGuardMiddleware` 创建 `ApprovalRequest`。
2. LangGraph `interrupt()` 暂停执行。
3. 前端 `ApprovalCard` 轮询 `/security/approvals`。
4. 用户批准/拒绝后调用 `/security/approvals/resume`。

## Plan Gate

`/plan` 进入规划态后，智能体必须先写入 todos，非规划工具会被阻断。计划生成后通过 `interrupt()` 等待用户确认。

## 技能扫描

技能安装前由 `SkillScanner` 检查：

- 常见密钥模式：OpenAI、AWS、GitHub token、硬编码 password/secret。
- 危险代码：`os.system`、`subprocess`、`eval`、`exec`、动态 import、`rm -rf`。

## 插件安全默认

插件目录 `backend/plugins_ext/` 中存在插件不代表启用。只有 `ENABLED_PLUGINS` 中列出的插件才会被动态 import 并注册工具。

```env
ENABLED_PLUGINS=example_echo
```

## 记忆污染防护

`source="cron"` 和 `source="heartbeat"` 的自动化请求不会写入长期记忆，避免定时任务污染人工上下文。

## 部署建议

- 生产环境必须设置 `API_TOKEN` 或在网关层加鉴权。
- 不要把真实 `.env`、凭据文件、私钥提交到仓库。
- 如启用插件，先在隔离环境扫描和审查插件源码。
- 对外暴露 webhook 时建议使用 HTTPS。

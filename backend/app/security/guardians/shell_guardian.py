"""Shell evasion guardian: detects obfuscated/dangerous shell commands."""

from __future__ import annotations

import re

from app.security.execution_level import GuardSeverity
from app.security.guardians.base import BaseGuardian
from app.security.models import GuardFinding, GuardResult

SHELL_TOOLS = {"execute_shell_command", "execute", "run_shell"}

DANGER_PATTERNS = [
    (r"rm\s+-rf\s+/", "rm -rf 根路径"),
    (r"\brm\s+-rf\b", "递归强制删除"),
    (r"base64\s+-d.*\|\s*(sh|bash)", "base64 解码后管道执行"),
    (r"curl[^\n|]*\|\s*(sh|bash)", "curl 管道执行"),
    (r"wget[^\n|]*\|\s*(sh|bash)", "wget 管道执行"),
    (r"[`$]\(", "命令替换嵌套"),
    (r":\(\)\s*\{.*\|.*&\s*\}", "fork bomb"),
    (r"\bmkfs\b", "格式化磁盘"),
    (r"\bdd\s+if=", "dd 磁盘写入"),
    (r">\s*/dev/sd", "写入块设备"),
    (r"chmod\s+-R\s+777", "危险权限"),
]


class ShellEvasionGuardian(BaseGuardian):
    name = "shell_guardian"

    def inspect(self, tool_name: str, args: dict) -> GuardResult:
        if tool_name not in SHELL_TOOLS:
            return GuardResult()
        command = " ".join(str(v) for v in args.values())
        for pattern, desc in DANGER_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return GuardResult(
                    allowed=False,
                    reason=f"检测到危险 Shell 模式: {desc}",
                    findings=[GuardFinding(GuardSeverity.CRITICAL, "shell_evasion", desc, self.name)],
                )
        return GuardResult()

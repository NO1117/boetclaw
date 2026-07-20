"""Rule-based guardian: flags high-risk tools and config-denied tools."""

from __future__ import annotations

from app.core.config import settings
from app.security.execution_level import GuardSeverity
from app.security.guardians.base import BaseGuardian
from app.security.models import GuardFinding, GuardResult

HIGH_RISK_TOOLS = {"execute_shell_command", "execute", "delete"}
MEDIUM_RISK_TOOLS = {"write_file", "edit_file"}


class RuleBasedToolGuardian(BaseGuardian):
    name = "rule_guardian"

    def __init__(self, denied: list[str] | None = None) -> None:
        self._denied = set(denied if denied is not None else settings.denied_tools_list)

    def inspect(self, tool_name: str, args: dict) -> GuardResult:
        if tool_name in self._denied:
            return GuardResult(
                allowed=False,
                reason=f"工具 {tool_name} 已在配置中被禁用",
                findings=[GuardFinding(GuardSeverity.CRITICAL, "denied", f"{tool_name} denied by config", self.name)],
            )
        if tool_name in HIGH_RISK_TOOLS:
            return GuardResult(
                requires_approval=True,
                findings=[GuardFinding(GuardSeverity.HIGH, "high_risk", f"{tool_name} 为高危工具", self.name)],
            )
        if tool_name in MEDIUM_RISK_TOOLS:
            return GuardResult(
                requires_approval=True,
                findings=[GuardFinding(GuardSeverity.MEDIUM, "write", f"{tool_name} 会修改文件", self.name)],
            )
        return GuardResult()

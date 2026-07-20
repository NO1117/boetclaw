"""Tool guard engine: aggregates guardians and applies the execution-level policy."""

from __future__ import annotations

from app.core.config import settings
from app.core.observability import get_logger
from app.security.execution_level import GuardSeverity, ToolExecutionLevel
from app.security.guardians.base import BaseGuardian
from app.security.guardians.file_guardian import FilePathToolGuardian
from app.security.guardians.rule_guardian import RuleBasedToolGuardian
from app.security.guardians.shell_guardian import ShellEvasionGuardian
from app.security.models import GuardResult

logger = get_logger("tool_guard")


class ToolGuardEngine:
    def __init__(self, level: ToolExecutionLevel, guardians: list[BaseGuardian], enabled: bool = True) -> None:
        self.level = level
        self.enabled = enabled
        self._guardians = guardians

    @classmethod
    def from_settings(cls) -> "ToolGuardEngine":
        return cls(
            level=ToolExecutionLevel.from_str(settings.tool_guard_level),
            guardians=[
                RuleBasedToolGuardian(),
                FilePathToolGuardian(),
                ShellEvasionGuardian(),
            ],
            enabled=settings.tool_guard_enabled,
        )

    def evaluate(self, tool_name: str, args: dict) -> GuardResult:
        if not self.enabled or self.level == ToolExecutionLevel.OFF:
            return GuardResult(allowed=True)

        result = GuardResult(allowed=True)
        for g in self._guardians:
            result = result.merge(g.inspect(tool_name, args))

        # Hard deny always wins.
        if not result.allowed:
            return result

        # Apply level policy to decide whether approval is required.
        sev = result.max_severity
        if self.level == ToolExecutionLevel.STRICT:
            result.requires_approval = True
        elif self.level == ToolExecutionLevel.SMART:
            result.requires_approval = sev.value >= GuardSeverity.MEDIUM.value
        elif self.level == ToolExecutionLevel.AUTO:
            # only explicit high-risk/guarded findings require approval
            result.requires_approval = result.requires_approval and sev.value >= GuardSeverity.HIGH.value
        return result


_engine: ToolGuardEngine | None = None


def get_guard_engine() -> ToolGuardEngine:
    global _engine
    if _engine is None:
        _engine = ToolGuardEngine.from_settings()
    return _engine


def reload_guard_engine() -> ToolGuardEngine:
    global _engine
    _engine = ToolGuardEngine.from_settings()
    return _engine

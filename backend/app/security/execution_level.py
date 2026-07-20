"""Tool guard execution levels and severity enums."""

from __future__ import annotations

from enum import Enum


class ToolExecutionLevel(str, Enum):
    STRICT = "strict"  # 所有工具需审批
    SMART = "smart"    # INFO/LOW 自动放行，MEDIUM+ 需审批（推荐）
    AUTO = "auto"      # 仅显式 denied/guarded 需审批
    OFF = "off"        # 完全关闭

    @classmethod
    def from_str(cls, value: str) -> "ToolExecutionLevel":
        try:
            return cls(value.lower())
        except ValueError:
            return cls.SMART


class GuardSeverity(int, Enum):
    INFO = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

    @property
    def label(self) -> str:
        return self.name.lower()

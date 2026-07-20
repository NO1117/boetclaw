"""Example echo plugin (disabled by default; enable via ENABLED_PLUGINS)."""

from __future__ import annotations

from langchain_core.tools import tool

__all__ = ["echo_tool"]


@tool
def echo_tool(text: str) -> str:
    """回显输入文本（示例插件工具）。

    Args:
        text: 待回显的文本
    """
    return f"echo: {text}"

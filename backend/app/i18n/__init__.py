"""Tiny i18n helpers for API and command responses."""

from __future__ import annotations

from contextvars import ContextVar, Token

from app.core.config import settings

SUPPORTED_LANGS = {"zh", "en"}
lang_var: ContextVar[str] = ContextVar("boetclaw_lang", default="")

_MESSAGES: dict[str, dict[str, str]] = {
    "zh": {
        "commands.new.description": "开启新会话（新线程）",
        "commands.clear.description": "清空当前上下文",
        "commands.stop.description": "请求停止当前运行",
        "commands.restart.description": "重启智能体运行时",
        "commands.help.description": "查看可用命令",
        "commands.plan.description": "进入规划模式",
        "commands.new.response": "已开启新会话。",
        "commands.clear.response": "已清空上下文。",
        "commands.stop.response": "已请求停止当前运行。",
        "commands.stop.cancelled": "服务端已确认取消当前运行。",
        "commands.stop.no_run": "当前 Agent 和会话没有可停止的运行。",
        "commands.restart.response": "智能体运行时将重启。",
        "commands.help.header": "可用命令：",
        "security.blocked": "[安全拦截] {reason}",
        "security.user_rejected": "[用户拒绝执行]",
    },
    "en": {
        "commands.new.description": "Start a new conversation thread",
        "commands.clear.description": "Clear the current context",
        "commands.stop.description": "Request stopping the current run",
        "commands.restart.description": "Restart the agent runtime",
        "commands.help.description": "Show available commands",
        "commands.plan.description": "Enter planning mode",
        "commands.new.response": "Started a new conversation.",
        "commands.clear.response": "Cleared the current context.",
        "commands.stop.response": "Requested stopping the current run.",
        "commands.stop.cancelled": "The server confirmed cancellation of the current run.",
        "commands.stop.no_run": "No active run exists for this agent and thread.",
        "commands.restart.response": "The agent runtime will restart.",
        "commands.help.header": "Available commands:",
        "security.blocked": "[Security blocked] {reason}",
        "security.user_rejected": "[User rejected execution]",
    },
}


def normalize_lang(lang: str | None = None) -> str:
    raw = (lang or lang_var.get() or settings.lang or "zh").strip().lower()
    primary = raw.split(",", 1)[0].split("-", 1)[0].strip()
    return primary if primary in SUPPORTED_LANGS else "zh"


def t(key: str, lang: str | None = None, **kwargs: object) -> str:
    normalized = normalize_lang(lang)
    template = _MESSAGES.get(normalized, _MESSAGES["zh"]).get(key) or _MESSAGES["zh"].get(key) or key
    return template.format(**kwargs) if kwargs else template


def lang_from_headers(headers: dict[str, str] | None, explicit: str | None = None) -> str:
    if explicit:
        return normalize_lang(explicit)
    if headers:
        return normalize_lang(headers.get("accept-language"))
    return normalize_lang()


def set_lang(lang: str | None) -> Token[str]:
    return lang_var.set(normalize_lang(lang))


def reset_lang(token: Token[str]) -> None:
    lang_var.reset(token)

"""Message renderer: adapt agent output to each channel's render style."""

from __future__ import annotations

import re

from app.services.gateway.base import RenderStyle


class MessageRenderer:
    """Renders agent text into channel-appropriate payloads."""

    _MD_MARKS = re.compile(r"(\*\*|__|`{1,3}|^#{1,6}\s|^[-*]\s|\[(.+?)\]\((.+?)\))", re.MULTILINE)

    def render(self, text: str, style: RenderStyle) -> str:
        if style == RenderStyle.PLAIN:
            return self._to_plain(text)
        return text

    def render_card(self, title: str, text: str, style: RenderStyle) -> dict:
        """Return a card-ish structured payload (used by DingTalk/Feishu)."""
        body = self.render(text, style)
        return {"title": title, "text": body, "style": style.value}

    def _to_plain(self, text: str) -> str:
        # strip common markdown markers for plain-text channels
        out = re.sub(r"`{1,3}", "", text)
        out = re.sub(r"\*\*(.+?)\*\*", r"\1", out)
        out = re.sub(r"__(.+?)__", r"\1", out)
        out = re.sub(r"^#{1,6}\s*", "", out, flags=re.MULTILINE)
        out = re.sub(r"\[(.+?)\]\((.+?)\)", r"\1 (\2)", out)
        return out.strip()

    def truncate(self, text: str, limit: int = 4000) -> str:
        if len(text) <= limit:
            return text
        return text[: limit - 20] + "\n...(内容已截断)"


message_renderer = MessageRenderer()

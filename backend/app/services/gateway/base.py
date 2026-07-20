"""Channel gateway base: unified message models and BaseChannel ABC."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RenderStyle(str, Enum):
    MARKDOWN = "markdown"
    PLAIN = "plain"
    CARD = "card"


@dataclass
class GatewayMessage:
    platform: str
    user_id: str
    user_name: str
    content: str
    message_id: str
    chat_id: str
    raw: dict[str, Any] = field(default_factory=dict)
    is_group: bool = False


@dataclass
class GatewayResponse:
    success: bool
    content: str = ""
    error: str = ""


class BaseChannel(ABC):
    """Abstract messaging channel.

    Subclasses declare `channel` and a preferred `render_style`, and implement
    incoming parsing + reply sending. `verify_signature` defaults to permissive.
    """

    channel: str = "base"
    render_style: RenderStyle = RenderStyle.MARKDOWN

    # Backward-compatible alias used across older code paths.
    @property
    def platform(self) -> str:
        return self.channel

    @abstractmethod
    async def parse_incoming(self, payload: dict[str, Any]) -> GatewayMessage | None:
        """Parse a raw webhook payload into a GatewayMessage (or None to ignore)."""

    @abstractmethod
    async def send_reply(self, message: GatewayMessage, content: str) -> GatewayResponse:
        """Deliver a reply back to the originating conversation."""

    def signature_configured(self) -> bool:
        """True when a platform webhook secret/token is set and must be checked."""
        return False

    def verify_signature(self, headers: Any = None, body: Any = None, **kwargs: Any) -> bool:
        """Verify platform webhook authenticity.

        When ``signature_configured()`` is False, returns True (local-dev skip).
        Subclasses should accept Starlette/Mapping headers and raw body bytes or JSON.
        """
        return True

    def is_configured(self) -> bool:
        return True

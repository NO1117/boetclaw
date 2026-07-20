"""Guardian base class."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.security.models import GuardResult


class BaseGuardian(ABC):
    name: str = "base"

    @abstractmethod
    def inspect(self, tool_name: str, args: dict) -> GuardResult:
        ...

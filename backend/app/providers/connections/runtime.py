"""Runtime credential context for provider calls."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator


@dataclass
class RuntimeConnectionConfig:
    connection_id: str
    provider_type: str
    base_url: str
    api_key: str  # noqa: S105 - ephemeral secret holder

    def __repr__(self) -> str:
        return f"RuntimeConnectionConfig(connection_id={self.connection_id!r}, provider_type={self.provider_type!r})"


_runtime_ctx: ContextVar[RuntimeConnectionConfig | None] = ContextVar("provider_runtime_config", default=None)


def get_runtime_config() -> RuntimeConnectionConfig | None:
    return _runtime_ctx.get()


@contextmanager
def runtime_connection(config: RuntimeConnectionConfig | None) -> Iterator[None]:
    token = _runtime_ctx.set(config)
    try:
        yield
    finally:
        _runtime_ctx.reset(token)

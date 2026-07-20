"""Immutable identifiers for resumable LangGraph interrupts."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExecutionRef(BaseModel):
    """Server-issued identity of one interrupted graph execution."""

    model_config = ConfigDict(frozen=True)

    agent_id: str = Field(..., min_length=1)
    thread_id: str = Field(..., min_length=1)
    checkpoint_ns: str
    interrupt_id: str = Field(..., min_length=1)
    interrupt_type: str = Field(..., min_length=1)


class InterruptEnvelope(BaseModel):
    execution_ref: ExecutionRef
    payload: Any


def parse_interrupt(
    interrupt: Any,
    *,
    agent_id: str,
    thread_id: str,
    checkpoint_ns: str,
) -> InterruptEnvelope | None:
    """Parse a LangGraph Interrupt or a compatible test dictionary safely."""

    if isinstance(interrupt, dict):
        interrupt_id = interrupt.get("id")
        payload = interrupt.get("value")
    else:
        interrupt_id = getattr(interrupt, "id", None)
        payload = getattr(interrupt, "value", None)

    if not isinstance(interrupt_id, str) or not interrupt_id:
        return None
    if not isinstance(payload, dict):
        return None
    interrupt_type = payload.get("type")
    if not isinstance(interrupt_type, str) or not interrupt_type:
        return None

    try:
        execution_ref = ExecutionRef(
            agent_id=agent_id,
            thread_id=thread_id,
            checkpoint_ns=checkpoint_ns,
            interrupt_id=interrupt_id,
            interrupt_type=interrupt_type,
        )
    except ValueError:
        return None
    return InterruptEnvelope(execution_ref=execution_ref, payload=payload)


def parse_interrupt_result(
    result: Any,
    *,
    agent_id: str,
    thread_id: str,
    checkpoint_ns: str = "",
) -> InterruptEnvelope | None:
    if not isinstance(result, dict):
        return None
    interrupts = result.get("__interrupt__")
    if not isinstance(interrupts, (list, tuple)) or not interrupts:
        return None
    return parse_interrupt(
        interrupts[0],
        agent_id=agent_id,
        thread_id=thread_id,
        checkpoint_ns=checkpoint_ns,
    )

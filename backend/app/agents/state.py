"""Extended agent state with plan-gate phase tracking."""

from __future__ import annotations

from deepagents import DeepAgentState


class BoetClawState(DeepAgentState):
    """DeepAgentState + plan_phase.

    plan_phase transitions: idle -> planning -> awaiting_confirm -> executing -> idle
    """

    plan_phase: str

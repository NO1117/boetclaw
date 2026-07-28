"""Per-run latency, token usage and cost estimation."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.providers.capabilities import EnrichedModelInfo, enrich_model
from app.providers.manager import provider_manager


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RunMetricsSummary:
    trace_id: str
    run_id: str
    agent_id: str = "default"
    provider: str | None = None
    model: str | None = None
    status: str = "running"
    started_at: str = field(default_factory=_now_iso)
    first_token_at: str | None = None
    completed_at: str | None = None
    time_to_first_token_ms: float | None = None
    total_duration_ms: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    estimated_cost: float | None = None
    cost_currency: str | None = None
    cost_is_estimate: bool = False
    graph_cache_hit: bool | None = None
    graph_cache_build_ms: float | None = None
    attachment_count: int = 0
    retrieval_hits: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "run_id": self.run_id,
            "agent_id": self.agent_id,
            "provider": self.provider,
            "model": self.model,
            "status": self.status,
            "started_at": self.started_at,
            "first_token_at": self.first_token_at,
            "completed_at": self.completed_at,
            "time_to_first_token_ms": self.time_to_first_token_ms,
            "total_duration_ms": self.total_duration_ms,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "estimated_cost": self.estimated_cost,
            "cost_currency": self.cost_currency,
            "cost_is_estimate": self.cost_is_estimate,
            "graph_cache_hit": self.graph_cache_hit,
            "graph_cache_build_ms": self.graph_cache_build_ms,
            "attachment_count": self.attachment_count,
            "retrieval_hits": self.retrieval_hits,
        }


class RunMetricsTracker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._runs: dict[str, RunMetricsSummary] = {}
        self._started_mono: dict[str, float] = {}

    def start(
        self,
        *,
        trace_id: str,
        run_id: str,
        agent_id: str,
        provider: str | None = None,
        model: str | None = None,
        attachment_count: int = 0,
        retrieval_hits: int = 0,
        graph_cache_hit: bool | None = None,
        graph_cache_build_ms: float | None = None,
    ) -> RunMetricsSummary:
        summary = RunMetricsSummary(
            trace_id=trace_id,
            run_id=run_id,
            agent_id=agent_id,
            provider=provider,
            model=model,
            attachment_count=attachment_count,
            retrieval_hits=retrieval_hits,
            graph_cache_hit=graph_cache_hit,
            graph_cache_build_ms=graph_cache_build_ms,
        )
        with self._lock:
            self._runs[trace_id] = summary
            self._started_mono[trace_id] = time.monotonic()
        return summary

    def record_first_token(self, trace_id: str) -> None:
        with self._lock:
            summary = self._runs.get(trace_id)
            mono = self._started_mono.get(trace_id)
            if summary is None or mono is None or summary.first_token_at is not None:
                return
            summary.first_token_at = _now_iso()
            summary.time_to_first_token_ms = round((time.monotonic() - mono) * 1000, 1)

    def complete(
        self,
        trace_id: str,
        *,
        usage: dict[str, Any] | None = None,
        provider: str | None = None,
        model: str | None = None,
        status: str = "completed",
    ) -> RunMetricsSummary | None:
        with self._lock:
            summary = self._runs.get(trace_id)
            mono = self._started_mono.get(trace_id)
            if summary is None:
                return None
            summary.status = status
            summary.completed_at = _now_iso()
            if mono is not None:
                summary.total_duration_ms = round((time.monotonic() - mono) * 1000, 1)
            if provider:
                summary.provider = provider
            if model:
                summary.model = model
            if usage:
                self._apply_usage(summary, usage)
            self._apply_cost_estimate(summary)
            return summary

    def get(self, trace_id: str) -> RunMetricsSummary | None:
        with self._lock:
            return self._runs.get(trace_id)

    def _apply_usage(self, summary: RunMetricsSummary, usage: dict[str, Any]) -> None:
        inp = usage.get("input_tokens")
        out = usage.get("output_tokens")
        total = usage.get("total_tokens")
        summary.input_tokens = int(inp) if inp is not None else None
        summary.output_tokens = int(out) if out is not None else None
        if total is not None:
            summary.total_tokens = int(total)
        elif summary.input_tokens is not None and summary.output_tokens is not None:
            summary.total_tokens = summary.input_tokens + summary.output_tokens
        else:
            summary.total_tokens = None

    def _apply_cost_estimate(self, summary: RunMetricsSummary) -> None:
        if summary.provider is None or summary.model is None:
            return
        if summary.input_tokens is None and summary.output_tokens is None:
            return
        try:
            enriched = enrich_model(
                name=summary.model,
                provider=summary.provider,
            )
        except Exception:
            return
        inp_price = enriched.pricing.get("input_per_million")
        out_price = enriched.pricing.get("output_per_million")
        if inp_price is None and out_price is None:
            return
        cost = 0.0
        has_component = False
        if inp_price is not None and summary.input_tokens is not None:
            cost += (summary.input_tokens / 1_000_000) * float(inp_price)
            has_component = True
        if out_price is not None and summary.output_tokens is not None:
            cost += (summary.output_tokens / 1_000_000) * float(out_price)
            has_component = True
        if has_component:
            summary.estimated_cost = round(cost, 6)
            summary.cost_currency = "USD"
            summary.cost_is_estimate = True


def extract_usage_from_messages(messages: list[Any]) -> dict[str, int | None]:
    """Best-effort usage extraction from LangChain response metadata."""
    for msg in reversed(messages):
        meta = getattr(msg, "response_metadata", None) or getattr(msg, "usage_metadata", None)
        if not meta:
            continue
        if isinstance(meta, dict):
            token_usage = meta.get("token_usage") or meta.get("usage") or meta
            inp = token_usage.get("input_tokens") or token_usage.get("prompt_tokens")
            out = token_usage.get("output_tokens") or token_usage.get("completion_tokens")
            total = token_usage.get("total_tokens")
            return {
                "input_tokens": int(inp) if inp is not None else None,
                "output_tokens": int(out) if out is not None else None,
                "total_tokens": int(total) if total is not None else None,
            }
    return {"input_tokens": None, "output_tokens": None, "total_tokens": None}


run_metrics_tracker = RunMetricsTracker()

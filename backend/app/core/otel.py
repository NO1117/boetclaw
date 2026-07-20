"""OpenTelemetry setup for FastAPI with BoetClaw trace_id correlation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import settings
from app.core.observability import get_logger, new_trace_id, trace_id_var

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = get_logger("otel")

_instrumented = False
_middleware_registered = False


def setup_otel(app: FastAPI) -> None:
    """Instrument FastAPI and bind HTTP spans to BoetClaw trace_id."""
    global _instrumented
    if _instrumented or not settings.otel_enabled:
        return

    try:
        from opentelemetry import trace
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider

        if not isinstance(trace.get_tracer_provider(), TracerProvider):
            resource = Resource.create({"service.name": "boetclaw"})
            provider = TracerProvider(resource=resource)
            if settings.otel_console_exporter:
                from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

                provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
            trace.set_tracer_provider(provider)

        FastAPIInstrumentor.instrument_app(app, excluded_urls="health,metrics")
        _register_trace_middleware(app)
        _instrumented = True
        logger.info("otel_initialized")
    except Exception as exc:  # noqa: BLE001
        logger.warning("otel_init_failed", error=str(exc))


def _register_trace_middleware(app: FastAPI) -> None:
    global _middleware_registered
    if _middleware_registered:
        return

    from opentelemetry import trace

    @app.middleware("http")
    async def boetclaw_trace_middleware(request, call_next):  # type: ignore[no-untyped-def]
        tid = request.headers.get("x-trace-id") or new_trace_id()
        trace_id_var.set(tid)

        span = trace.get_current_span()
        if span.is_recording():
            span.set_attribute("boetclaw.trace_id", tid)
            span.set_attribute("http.route", request.url.path)

        response = await call_next(request)
        response.headers["X-Trace-Id"] = tid
        return response

    _middleware_registered = True

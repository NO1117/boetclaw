"""Agent interaction routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from sse_starlette.sse import EventSourceResponse

from app.api.schemas import (
    ChatRequest,
    ChatResponse,
    PlanConfirmRequest,
    PlanConfirmResponse,
    RunCancelRequest,
    RunCancelResponse,
    TraceEventResponse,
)
from app.core.agent import agent_manager
from app.core.observability import serialize_for_sse, trace_store
from app.memory.plan_history_store import plan_history_store
from app.memory.session_store import session_store
from app.services.chat_orchestration import ChatPreparationError, PreparedChat, prepare_chat
from app.services.run_registry import run_registry

router = APIRouter(prefix="/agent", tags=["Agent"])


SSE_VERSION = "1"


def _http_error(exc: ChatPreparationError) -> HTTPException:
    if exc.detail:
        return HTTPException(status_code=exc.status_code, detail=exc.detail)
    return HTTPException(status_code=exc.status_code, detail=str(exc))


def _sse_envelope(prepared: PreparedChat, event: str, data: object) -> dict:
    return {
        "event": event,
        "data": data,
        "version": SSE_VERSION,
        "thread_id": prepared.response_thread_id,
        "agent_id": prepared.agent_id,
        "trace_id": prepared.trace_id,
        "run_id": prepared.run_id,
    }


def _sse(prepared: PreparedChat, event: str, data: object) -> dict[str, str]:
    return {
        "event": event,
        "data": serialize_for_sse(_sse_envelope(prepared, event, data)),
    }


@router.post("/chat", response_model=ChatResponse)
async def chat(request: Request, body: ChatRequest):
    from app.agents.runtime import invoke_agent
    from app.i18n import reset_lang, set_lang

    try:
        prepared = await prepare_chat(
            message=body.message,
            attachments=[item.model_dump() for item in body.attachments],
            attachment_ids=body.attachment_ids,
            thread_id=body.thread_id,
            agent_id=body.agent_id,
            source=body.source,
            lang=body.lang,
            headers=request.headers,
            provider=body.provider,
            model=body.model,
        )
        lang_token = set_lang(prepared.lang)
        try:
            if prepared.command is not None:
                return ChatResponse(
                    thread_id=prepared.response_thread_id,
                    trace_id=prepared.trace_id,
                    run_id=prepared.run_id,
                    response=prepared.command.response,
                    message_count=0,
                    agent_id=prepared.agent_id,
                )

            async with run_registry.track_current(
                agent_id=prepared.agent_id,
                thread_id=prepared.thread_id,
                run_id=prepared.run_id,
                trace_id=prepared.trace_id,
            ):
                result = await invoke_agent(
                    prepared.agent,
                    prepared.message,
                    prepared.thread_id,
                    agent_id=prepared.agent_id,
                    source=prepared.source,
                    trace_id=prepared.trace_id,
                    run_id=prepared.run_id,
                    user_content=prepared.user_content,
                    model_string=prepared.model_string,
                )
        finally:
            reset_lang(lang_token)
        session_store.record_turn(
            thread_id=prepared.thread_id,
            agent_id=prepared.agent_id,
            user_message=prepared.history_user_message,
            assistant_message=str(result.get("response", "")),
            trace_id=prepared.trace_id,
            run_id=prepared.run_id,
            source=prepared.source,
            attachment_refs=prepared.attachment_refs,
        )
        payload = {k: v for k, v in result.items() if k in ChatResponse.model_fields}
        payload["memory_context"] = prepared.memory_context
        payload["memory_candidates"] = prepared.memory_candidates
        payload["memory_actions"] = prepared.memory_actions
        return ChatResponse(**payload)
    except ChatPreparationError as exc:
        raise _http_error(exc) from exc
    except Exception as exc:
        status_code = getattr(exc, "status_code", 500)
        if 400 <= status_code < 500:
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/plan/confirm", response_model=PlanConfirmResponse)
async def plan_confirm(request: PlanConfirmRequest):
    from app.services.execution_resume import ResumeValidationError
    from app.services.plan_resume import plan_resume_service

    try:
        return await plan_resume_service.resume(
            execution_ref=request.execution_ref,
            thread_id=request.thread_id or "",
            decision=request.decision,
            edited_todos=request.edited_todos,
        )
    except ResumeValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/plan/history")
async def plan_history(agent_id: str = "", thread_id: str = "", limit: int = 100):
    return {
        "plans": plan_history_store.list(
            agent_id=agent_id,
            thread_id=thread_id,
            limit=limit,
        )
    }


@router.post("/chat/stream")
async def chat_stream(request: Request, body: ChatRequest):
    try:
        prepared = await prepare_chat(
            message=body.message,
            attachments=[item.model_dump() for item in body.attachments],
            attachment_ids=body.attachment_ids,
            thread_id=body.thread_id,
            agent_id=body.agent_id,
            source=body.source,
            lang=body.lang,
            headers=request.headers,
            provider=body.provider,
            model=body.model,
        )
    except ChatPreparationError as exc:
        raise _http_error(exc) from exc
    except Exception as exc:
        status_code = getattr(exc, "status_code", 500)
        if 400 <= status_code < 500:
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    async def event_generator():
        from app.agents.runtime import stream_agent
        from app.i18n import reset_lang, set_lang

        lang_token = set_lang(prepared.lang)
        try:
            if prepared.command is not None:
                yield _sse(
                    prepared,
                    "command",
                    {
                        "response": prepared.command.response,
                        "action": prepared.command.action,
                    },
                )
                yield _sse(prepared, "done", {"response": prepared.command.response})
                return

            async with run_registry.track_current(
                agent_id=prepared.agent_id,
                thread_id=prepared.thread_id,
                run_id=prepared.run_id,
                trace_id=prepared.trace_id,
            ):
                result: dict = {}
                async for event in stream_agent(
                    prepared.agent,
                    prepared.message,
                    prepared.thread_id,
                    agent_id=prepared.agent_id,
                    source=prepared.source,
                    trace_id=prepared.trace_id,
                    run_id=prepared.run_id,
                    user_content=prepared.user_content,
                    model_string=prepared.model_string,
                    attachment_count=len(prepared.attachment_summaries),
                    retrieval_hits=prepared.retrieval_hits,
                ):
                    if event.pop("kind") == "update":
                        yield _sse(prepared, "update", event)
                    else:
                        result = event

                session_store.record_turn(
                    thread_id=prepared.thread_id,
                    agent_id=prepared.agent_id,
                    user_message=prepared.history_user_message,
                    assistant_message=str(result.get("response", "")),
                    trace_id=prepared.trace_id,
                    run_id=prepared.run_id,
                    source=prepared.source,
                    attachment_refs=prepared.attachment_refs,
                )
                if result.get("interrupted"):
                    yield _sse(prepared, "interrupt", result)
                yield _sse(
                    prepared,
                    "done",
                    {
                        "response": result.get("response", ""),
                        "interrupted": bool(result.get("interrupted")),
                        "run_metrics": result.get("run_metrics"),
                        "memory_context": prepared.memory_context,
                        "memory_candidates": prepared.memory_candidates,
                        "memory_actions": prepared.memory_actions,
                    },
                )
        except Exception as exc:
            yield _sse(prepared, "error", {"error": str(exc)})
        finally:
            reset_lang(lang_token)

    return EventSourceResponse(event_generator())


@router.get("/runs/metrics/{trace_id}")
async def get_run_metrics(trace_id: str):
    from app.services.run_metrics import run_metrics_tracker

    summary = run_metrics_tracker.get(trace_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="run metrics not found")
    return summary.to_dict()


@router.post("/runs/cancel", response_model=RunCancelResponse)
async def cancel_run(body: RunCancelRequest):
    result = await run_registry.cancel(
        run_id=body.run_id,
        agent_id=body.agent_id,
        thread_id=body.thread_id,
    )
    if not result.found:
        raise HTTPException(status_code=404, detail=result.detail)
    if not result.cancelled:
        raise HTTPException(status_code=409, detail=result.detail)
    return RunCancelResponse(
        cancelled=True,
        status=result.status.value if result.status else "",
        agent_id=body.agent_id,
        thread_id=body.thread_id,
        run_id=result.run_id,
        detail=result.detail,
    )


@router.get("/sessions")
async def list_sessions(
    q: str = "",
    limit: int = 50,
    include_archived: bool = False,
    archived_only: bool = False,
):
    return {
        "sessions": session_store.list_sessions(
            q,
            limit,
            include_archived=include_archived,
            archived_only=archived_only,
        )
    }


@router.get("/sessions/{thread_id}")
async def get_session(thread_id: str):
    data = session_store.get_session(thread_id)
    if data is None:
        raise HTTPException(status_code=404, detail="session not found")
    return data


@router.get("/sessions/{thread_id}/export")
async def export_session(thread_id: str):
    content = session_store.export_markdown(thread_id)
    if content is None:
        raise HTTPException(status_code=404, detail="session not found")
    return Response(content, media_type="text/markdown; charset=utf-8")


@router.post("/sessions/{thread_id}/archive")
async def archive_session(thread_id: str):
    data = session_store.archive_session(thread_id)
    if data is None:
        raise HTTPException(status_code=404, detail="session not found")
    return {
        "thread_id": thread_id,
        "archived": True,
        "archived_at": data.get("archived_at", ""),
    }


@router.post("/sessions/{thread_id}/unarchive")
async def unarchive_session(thread_id: str):
    data = session_store.unarchive_session(thread_id)
    if data is None:
        raise HTTPException(status_code=404, detail="session not found")
    return {
        "thread_id": thread_id,
        "archived": False,
        "archived_at": "",
    }


@router.delete("/sessions/{thread_id}")
async def delete_session(thread_id: str):
    if not session_store.delete_session(thread_id):
        raise HTTPException(status_code=404, detail="session not found")
    return {"deleted": thread_id}


@router.get("/tools")
async def list_tools():
    return {"tools": agent_manager.list_tools()}


@router.get("/trace/{trace_id}", response_model=list[TraceEventResponse])
async def get_trace(trace_id: str):
    events = trace_store.get_by_trace(trace_id)
    return [TraceEventResponse(**e.to_dict()) for e in events]


@router.get("/trace/run/{run_id}", response_model=list[TraceEventResponse])
async def get_run_trace(run_id: str):
    events = trace_store.get_by_run(run_id)
    return [TraceEventResponse(**e.to_dict()) for e in events]

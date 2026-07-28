"""Resolve stored attachment IDs into chat model content."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any

from app.core.observability import EventType, emit_event
from app.services.attachments.retrieval import retrieve_for_query
from app.services.attachments.security import AttachmentSecurityError, validate_batch_limits
from app.services.attachments.service import attachment_service
from app.services.chat_attachments import (
    AttachmentSummary,
    AttachmentValidationError,
    MAX_FILE_COUNT,
    prepare_attachment_content,
    ChatAttachmentInput,
)


@dataclass(frozen=True)
class ResolvedAttachmentContent:
    user_content: str | list[dict[str, Any]]
    history_text: str
    summaries: list[AttachmentSummary]
    has_images: bool
    attachment_refs: list[dict[str, Any]]
    retrieval_trace: dict[str, Any]


def _location_label(location: dict[str, Any]) -> str:
    if location.get("page"):
        return f"p.{location['page']}"
    if location.get("sheet"):
        return f"sheet:{location['sheet']}"
    if location.get("slide"):
        return f"slide:{location['slide']}"
    if location.get("section"):
        return str(location["section"])
    return ""


def _format_chunk_citation(filename: str, location: dict[str, Any], chunk_id: str) -> str:
    loc = _location_label(location)
    suffix = f" @{loc}" if loc else ""
    return f"[{filename}{suffix} · {chunk_id}]"


async def resolve_attachment_ids_for_chat(
    *,
    message: str,
    agent_id: str,
    attachment_ids: list[str],
    inline_attachments: list[ChatAttachmentInput] | None = None,
    trace_id: str = "",
) -> ResolvedAttachmentContent:
    if inline_attachments:
        prepared = prepare_attachment_content(message, inline_attachments)
        return ResolvedAttachmentContent(
            user_content=prepared.user_content,
            history_text=prepared.history_text,
            summaries=prepared.summaries,
            has_images=prepared.has_images,
            attachment_refs=[],
            retrieval_trace={},
        )

    ids = [item.strip() for item in attachment_ids if item and item.strip()]
    if len(ids) > MAX_FILE_COUNT:
        raise AttachmentValidationError(f"单次最多发送 {MAX_FILE_COUNT} 个附件")

    summaries: list[AttachmentSummary] = []
    blocks: list[dict[str, Any]] = []
    has_images = False
    text_parts: list[str] = []
    attachment_refs: list[dict[str, Any]] = []
    total_bytes = 0
    retrieval_hits = 0
    retrieval_chars = 0

    user_text = message.strip()
    if user_text:
        text_parts.append(user_text)

    for attachment_id in ids:
        record = attachment_service.get_record(agent_id, attachment_id)
        if record is None:
            raise AttachmentValidationError("附件不存在或无权访问", 404)
        if record.status == "parsing":
            raise AttachmentValidationError(f"附件 {record.filename} 仍在解析中")
        if record.status == "failed":
            raise AttachmentValidationError(f"附件 {record.filename} 解析失败，请重试")
        if record.status != "ready":
            raise AttachmentValidationError(f"附件 {record.filename} 尚未就绪")

        total_bytes += record.size
        path = record.relative_path or record.filename
        ref_entry = {
            "attachment_id": record.attachment_id,
            "filename": record.filename,
            "kind": record.kind,
            "size": record.size,
        }
        attachment_refs.append(ref_entry)

        if record.kind == "image":
            has_images = True
            mime, payload = attachment_service.read_image_base64(agent_id, attachment_id)
            data_url = f"data:{mime};base64,{payload}"
            blocks.append({"type": "image_url", "image_url": {"url": data_url}})
            summaries.append(
                AttachmentSummary(
                    filename=record.filename,
                    relative_path=record.relative_path,
                    mime_type=mime,
                    size=record.size,
                    kind="image",
                    status="ready",
                    detail="图像待模型读取",
                )
            )
            continue

        if record.kind in ("text", "document"):
            retrieval = retrieve_for_query(agent_id, [attachment_id], message)
            if retrieval.chunks:
                chunk_lines: list[str] = []
                citations: list[str] = []
                for item in retrieval.chunks:
                    loc = item.chunk.location.model_dump()
                    cite = _format_chunk_citation(record.filename, loc, item.chunk.chunk_id)
                    citations.append(cite)
                    chunk_lines.append(f"{cite}\n{item.chunk.text}")
                header = f"--- 附件: {path} ({record.mime_type}, {record.size} bytes) ---"
                text_parts.append(f"{header}\n" + "\n\n".join(chunk_lines) + f"\n--- 结束: {path} ---")
                detail = f"检索 {len(retrieval.chunks)} 块"
                if retrieval.truncated:
                    detail += " · 已截断"
                summaries.append(
                    AttachmentSummary(
                        filename=record.filename,
                        relative_path=record.relative_path,
                        mime_type=record.mime_type,
                        size=record.size,
                        kind="text" if record.kind == "text" else "binary",
                        status="ready",
                        detail=detail,
                    )
                )
                retrieval_hits += len(retrieval.chunks)
                retrieval_chars += retrieval.total_chars
                if trace_id:
                    emit_event(
                        EventType.MEMORY_PERSIST,
                        {
                            "action": "attachment_retrieval",
                            "attachment_id": attachment_id,
                            "chunk_ids": [item.chunk.chunk_id for item in retrieval.chunks],
                            "citations": citations,
                            "truncated": retrieval.truncated,
                            "total_chars": retrieval.total_chars,
                            "query_tokens": retrieval.query_tokens,
                        },
                        trace_id=trace_id,
                        run_id="",
                    )
            else:
                content = attachment_service.get_content(agent_id, attachment_id)
                chunks = content.get("chunks", [])
                if chunks:
                    body = "\n\n".join(str(c.get("text", "")) for c in chunks[:5])
                else:
                    body = ""
                header = f"--- 附件: {path} ({record.mime_type}, {record.size} bytes) ---"
                text_parts.append(f"{header}\n{body}\n--- 结束: {path} ---")
                summaries.append(
                    AttachmentSummary(
                        filename=record.filename,
                        relative_path=record.relative_path,
                        mime_type=record.mime_type,
                        size=record.size,
                        kind="text",
                        status="ready",
                        detail="全文注入",
                    )
                )
            continue

        meta = (
            f"[二进制附件 metadata] 路径={path}; 文件名={record.filename}; "
            f"MIME={record.mime_type}; 大小={record.size} bytes; "
            "内容未解码，模型无法直接读取字节。"
        )
        text_parts.append(meta)
        summaries.append(
            AttachmentSummary(
                filename=record.filename,
                relative_path=record.relative_path,
                mime_type=record.mime_type,
                size=record.size,
                kind="binary",
                status="metadata",
                detail="仅发送元数据",
            )
        )

    validate_batch_limits(len(ids), total_bytes)

    combined_text = "\n\n".join(part for part in text_parts if part).strip()
    if blocks:
        content: str | list[dict[str, Any]]
        if combined_text:
            blocks.insert(0, {"type": "text", "text": combined_text})
            content = blocks
        else:
            content = blocks
    else:
        content = combined_text

    if not content:
        raise AttachmentValidationError("消息与附件均为空")

    history_suffix = ""
    if summaries:
        lines = []
        for s in summaries:
            label = s.relative_path or s.filename
            lines.append(f"▧ {label} · {s.size} bytes · id:{next(r['attachment_id'] for r in attachment_refs if r['filename'] == s.filename)}")
        history_suffix = "\n".join(lines)

    history_text = user_text
    if history_suffix:
        history_text = f"{user_text}\n{history_suffix}".strip() if user_text else history_suffix

    return ResolvedAttachmentContent(
        user_content=content,
        history_text=history_text,
        summaries=summaries,
        has_images=has_images,
        attachment_refs=attachment_refs,
        retrieval_trace={
            "hits": retrieval_hits,
            "total_chars": retrieval_chars,
        },
    )

"""Validate and convert chat attachments into multimodal user content."""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_FILE_COUNT = 20
MAX_TOTAL_BYTES = 100 * 1024 * 1024

TEXT_MIME_PREFIXES = ("text/",)
TEXT_MIME_TYPES = {
    "application/json",
    "application/xml",
    "application/javascript",
    "application/x-yaml",
    "application/yaml",
}
TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".markdown",
    ".json",
    ".yaml",
    ".yml",
    ".csv",
    ".tsv",
    ".xml",
    ".html",
    ".htm",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".py",
    ".java",
    ".go",
    ".rs",
    ".sql",
    ".sh",
    ".bat",
    ".ps1",
    ".log",
    ".ini",
    ".cfg",
    ".env",
}
IMAGE_MIME_PREFIX = "image/"


class ChatAttachmentInput(BaseModel):
    filename: str = Field(..., min_length=1, max_length=512)
    relative_path: str = Field("", max_length=2048)
    mime_type: str = Field("application/octet-stream", max_length=256)
    size: int = Field(..., ge=0)
    kind: Literal["text", "image", "binary"] = "binary"
    content_base64: str = Field("", max_length=MAX_FILE_BYTES * 2 + 4096)

    @model_validator(mode="after")
    def validate_filename(self) -> "ChatAttachmentInput":
        name = self.filename.strip()
        if not name or ".." in name or name.startswith("/") or "\\" in name:
            raise ValueError("附件文件名无效")
        if self.relative_path and (".." in self.relative_path.replace("\\", "/")):
            raise ValueError("附件相对路径无效")
        return self


class AttachmentSummary(BaseModel):
    filename: str
    relative_path: str = ""
    mime_type: str
    size: int
    kind: str
    status: str
    detail: str = ""


@dataclass(frozen=True)
class PreparedAttachmentContent:
    user_content: str | list[dict[str, Any]]
    history_text: str
    summaries: list[AttachmentSummary]
    has_images: bool


class AttachmentValidationError(ValueError):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def _display_path(item: ChatAttachmentInput) -> str:
    return item.relative_path or item.filename


def _is_text_like(item: ChatAttachmentInput) -> bool:
    mime = (item.mime_type or "").lower()
    if mime.startswith(TEXT_MIME_PREFIXES) or mime in TEXT_MIME_TYPES:
        return True
    lower = item.filename.lower()
    for ext in TEXT_EXTENSIONS:
        if lower.endswith(ext):
            return True
    return item.kind == "text"


def _is_image(item: ChatAttachmentInput) -> bool:
    return item.kind == "image" or (item.mime_type or "").lower().startswith(IMAGE_MIME_PREFIX)


def _decode_base64(payload: str, expected_size: int) -> bytes:
    if not payload:
        raise AttachmentValidationError("附件缺少内容数据")
    try:
        raw = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise AttachmentValidationError("附件 Base64 无效") from exc
    if len(raw) > MAX_FILE_BYTES:
        raise AttachmentValidationError("单个附件超过 25 MB 限制")
    if expected_size and abs(len(raw) - expected_size) > max(64, int(expected_size * 0.05)):
        raise AttachmentValidationError("附件大小与声明不一致")
    return raw


def _decode_text(raw: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "gb18030", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise AttachmentValidationError("无法安全解码文本附件")


def prepare_attachment_content(
    message: str,
    attachments: list[ChatAttachmentInput],
) -> PreparedAttachmentContent:
    """Convert validated attachments into LangChain-compatible user content."""
    if len(attachments) > MAX_FILE_COUNT:
        raise AttachmentValidationError(f"单次最多发送 {MAX_FILE_COUNT} 个附件")

    total_bytes = 0
    summaries: list[AttachmentSummary] = []
    blocks: list[dict[str, Any]] = []
    has_images = False
    text_parts: list[str] = []
    user_text = message.strip()

    if user_text:
        text_parts.append(user_text)

    for item in attachments:
        if item.size > MAX_FILE_BYTES:
            raise AttachmentValidationError("单个附件超过 25 MB 限制")
        total_bytes += item.size
        if total_bytes > MAX_TOTAL_BYTES:
            raise AttachmentValidationError("附件总大小超过 100 MB 限制")

        path = _display_path(item)
        raw = _decode_base64(item.content_base64, item.size)
        total_bytes = total_bytes - item.size + len(raw)

        if _is_image(item):
            has_images = True
            mime = item.mime_type if item.mime_type.startswith(IMAGE_MIME_PREFIX) else "image/png"
            data_url = f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"
            blocks.append({"type": "image_url", "image_url": {"url": data_url}})
            summaries.append(
                AttachmentSummary(
                    filename=item.filename,
                    relative_path=item.relative_path,
                    mime_type=mime,
                    size=len(raw),
                    kind="image",
                    status="ready",
                    detail="图像待模型读取",
                )
            )
            continue

        if _is_text_like(item):
            text = _decode_text(raw)
            header = f"--- 附件: {path} ({item.mime_type or 'text'}, {len(raw)} bytes) ---"
            text_parts.append(f"{header}\n{text}\n--- 结束: {path} ---")
            summaries.append(
                AttachmentSummary(
                    filename=item.filename,
                    relative_path=item.relative_path,
                    mime_type=item.mime_type,
                    size=len(raw),
                    kind="text",
                    status="ready",
                    detail="文本提取完成",
                )
            )
            continue

        meta = (
            f"[二进制附件 metadata] 路径={path}; 文件名={item.filename}; "
            f"MIME={item.mime_type}; 大小={len(raw)} bytes; "
            "内容未解码，模型无法直接读取字节。"
        )
        text_parts.append(meta)
        summaries.append(
            AttachmentSummary(
                filename=item.filename,
                relative_path=item.relative_path,
                mime_type=item.mime_type,
                size=len(raw),
                kind="binary",
                status="metadata",
                detail="仅发送元数据",
            )
        )

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
            lines.append(f"▧ {label} · {s.size} bytes")
        history_suffix = "\n".join(lines)

    history_text = user_text
    if history_suffix:
        history_text = f"{user_text}\n{history_suffix}".strip() if user_text else history_suffix

    return PreparedAttachmentContent(
        user_content=content,
        history_text=history_text,
        summaries=summaries,
        has_images=has_images,
    )

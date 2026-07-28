"""Attachment upload validation: paths, MIME signatures, and size limits."""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from app.services.chat_attachments import MAX_FILE_BYTES, MAX_FILE_COUNT, MAX_TOTAL_BYTES

# Magic-byte signatures for supported formats (prefix match).
SIGNATURES: list[tuple[bytes, str, set[str]]] = [
    (b"%PDF-", "application/pdf", {".pdf"}),
    (b"PK\x03\x04", "application/zip", {".docx", ".xlsx", ".pptx"}),
    (b"\x89PNG\r\n\x1a\n", "image/png", {".png"}),
    (b"\xff\xd8\xff", "image/jpeg", {".jpg", ".jpeg"}),
    (b"GIF87a", "image/gif", {".gif"}),
    (b"GIF89a", "image/gif", {".gif"}),
    (b"RIFF", "image/webp", {".webp"}),
]

OFFICE_MIMES = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}

TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".json", ".yaml", ".yml", ".csv", ".tsv", ".xml",
    ".html", ".htm", ".js", ".ts", ".jsx", ".tsx", ".py", ".java", ".go", ".rs",
    ".sql", ".sh", ".bat", ".ps1", ".log", ".ini", ".cfg", ".env",
}

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}

BLOCKED_EXTENSIONS = {
    ".exe", ".dll", ".cmd", ".com", ".msi", ".scr", ".vbs", ".jar",
    ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz",
}

_SAFE_AGENT_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_SAFE_FILENAME = re.compile(r'^[^/\\<>:"|?*\x00-\x1f]+$')


class AttachmentSecurityError(ValueError):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def normalize_agent_id(agent_id: str) -> str:
    value = (agent_id or "").strip()
    if not value or not _SAFE_AGENT_ID.match(value):
        raise AttachmentSecurityError("无效的 agent_id")
    return value


def normalize_relative_path(raw: str, filename: str) -> str:
    candidate = (raw or filename or "").strip().replace("\\", "/")
    if not candidate:
        raise AttachmentSecurityError("附件路径无效")
    parts = [p for p in PurePosixPath(candidate).parts if p not in (".", "")]
    if not parts or any(p == ".." for p in parts):
        raise AttachmentSecurityError("附件相对路径无效")
    normalized = "/".join(parts)
    if len(normalized) > 2048:
        raise AttachmentSecurityError("附件相对路径过长")
    return normalized


def normalize_filename(filename: str) -> str:
    name = (filename or "").strip().replace("\\", "/").split("/")[-1]
    if not name or ".." in name or not _SAFE_FILENAME.match(name):
        raise AttachmentSecurityError("附件文件名无效")
    if len(name) > 512:
        raise AttachmentSecurityError("附件文件名过长")
    return name


def extension_of(filename: str) -> str:
    lower = filename.lower()
    dot = lower.rfind(".")
    return lower[dot:] if dot >= 0 else ""


def detect_mime_from_signature(data: bytes, ext: str) -> str | None:
    for prefix, mime, exts in SIGNATURES:
        if data.startswith(prefix) and ext in exts:
            if ext in OFFICE_MIMES:
                return OFFICE_MIMES[ext]
            return mime
    if ext in TEXT_EXTENSIONS:
        return "text/plain"
    if ext in IMAGE_EXTENSIONS and ext != ".svg":
        return f"image/{ext.lstrip('.').replace('jpg', 'jpeg')}"
    if ext == ".svg":
        return "image/svg+xml"
    return None


def validate_upload_payload(
    *,
    filename: str,
    relative_path: str,
    declared_mime: str,
    size: int,
    data: bytes,
) -> tuple[str, str, str]:
    """Return (filename, relative_path, resolved_mime)."""
    if size > MAX_FILE_BYTES:
        raise AttachmentSecurityError("单个附件超过 25 MB 限制")
    if len(data) > MAX_FILE_BYTES:
        raise AttachmentSecurityError("单个附件超过 25 MB 限制")
    if size and abs(len(data) - size) > max(64, int(size * 0.05)):
        raise AttachmentSecurityError("附件大小与声明不一致")

    safe_name = normalize_filename(filename)
    safe_path = normalize_relative_path(relative_path, safe_name)
    ext = extension_of(safe_name)

    if ext in BLOCKED_EXTENSIONS and ext not in TEXT_EXTENSIONS:
        raise AttachmentSecurityError(f"不支持的文件类型: {ext or 'unknown'}")

    signature_mime = detect_mime_from_signature(data[:16], ext)
    declared = (declared_mime or "application/octet-stream").lower().split(";")[0].strip()

    if ext in OFFICE_MIMES:
        expected = OFFICE_MIMES[ext]
        if signature_mime != expected:
            raise AttachmentSecurityError("文件签名与 Office 格式不匹配")
        resolved = expected
    elif ext in TEXT_EXTENSIONS:
        resolved = declared if declared.startswith("text/") or declared in {
            "application/json", "application/xml", "application/yaml", "application/x-yaml",
        } else "text/plain"
    elif ext in IMAGE_EXTENSIONS:
        if not signature_mime and ext == ".svg":
            if not data.lstrip().startswith((b"<", b"<?xml")):
                raise AttachmentSecurityError("SVG 文件签名无效")
            resolved = "image/svg+xml"
        elif signature_mime:
            resolved = signature_mime
        else:
            raise AttachmentSecurityError("图像文件签名无效")
    elif ext == ".pdf":
        if signature_mime != "application/pdf":
            raise AttachmentSecurityError("PDF 文件签名无效")
        resolved = "application/pdf"
    else:
        resolved = declared

    if signature_mime and declared not in ("application/octet-stream", "") and not declared.startswith("text/"):
        if signature_mime.split("/")[0] != declared.split("/")[0] and declared != signature_mime:
            raise AttachmentSecurityError("声明 MIME 与文件签名不一致")

    return safe_name, safe_path, resolved


def infer_kind(mime: str, filename: str) -> str:
    ext = extension_of(filename)
    if mime.startswith("image/"):
        return "image"
    if mime == "application/pdf" or ext in OFFICE_MIMES or ext in TEXT_EXTENSIONS:
        return "document" if ext in OFFICE_MIMES or ext == ".pdf" else "text"
    if mime.startswith("text/") or ext in TEXT_EXTENSIONS:
        return "text"
    return "binary"


def validate_batch_limits(count: int, total_bytes: int) -> None:
    if count > MAX_FILE_COUNT:
        raise AttachmentSecurityError(f"单次最多 {MAX_FILE_COUNT} 个附件")
    if total_bytes > MAX_TOTAL_BYTES:
        raise AttachmentSecurityError("附件总大小超过 100 MB 限制")

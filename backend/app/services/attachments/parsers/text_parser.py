"""Plain text and code file parser."""

from __future__ import annotations

from app.services.attachments.chunking import chunk_flat_text
from app.services.attachments.models import DocumentSummary
from app.services.attachments.parsers import ParseResult
from app.services.chat_attachments import AttachmentValidationError


class TextParser:
    def parse(self, data: bytes, *, attachment_id: str, filename: str) -> ParseResult:
        text = self._decode(data)
        chunks = chunk_flat_text(attachment_id, text)
        return ParseResult(
            chunks=chunks,
            summary=DocumentSummary(
                paragraph_count=text.count("\n\n") + 1,
                chunk_count=len(chunks),
                char_count=len(text),
                searchable=len(chunks) > 0,
            ),
            plain_text=text,
        )

    @staticmethod
    def _decode(raw: bytes) -> str:
        for encoding in ("utf-8", "utf-8-sig", "gb18030", "latin-1"):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise AttachmentValidationError("无法安全解码文本附件")

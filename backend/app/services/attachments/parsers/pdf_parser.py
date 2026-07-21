"""PDF text extraction with page numbers."""

from __future__ import annotations

from app.services.attachments.chunking import chunk_plain_sections
from app.services.attachments.models import ChunkLocation, DocumentSummary
from app.services.attachments.parsers import ParseResult


class PdfParser:
    def parse(self, data: bytes, *, attachment_id: str, filename: str) -> ParseResult:
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError("缺少 PDF 解析依赖 pypdf，请安装 requirements.txt") from exc

        import io

        reader = PdfReader(io.BytesIO(data))
        sections: list[tuple[str, ChunkLocation]] = []
        for page_num, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                sections.append((text, ChunkLocation(page=page_num)))
        chunks = chunk_plain_sections(attachment_id, sections)
        plain = "\n\n".join(text for text, _ in sections)
        return ParseResult(
            chunks=chunks,
            summary=DocumentSummary(
                page_count=len(reader.pages),
                chunk_count=len(chunks),
                char_count=len(plain),
                searchable=len(chunks) > 0,
            ),
            plain_text=plain,
        )

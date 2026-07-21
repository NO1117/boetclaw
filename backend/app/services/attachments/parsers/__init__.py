"""Parser registry for supported attachment formats."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.services.attachments.models import DocumentSummary, TextChunk


@dataclass(frozen=True)
class ParseResult:
    chunks: list[TextChunk]
    summary: DocumentSummary
    plain_text: str = ""


class AttachmentParser(Protocol):
    def parse(self, data: bytes, *, attachment_id: str, filename: str) -> ParseResult: ...


class ParserRegistry:
    def __init__(self) -> None:
        self._parsers: dict[str, AttachmentParser] = {}
        self._extensions: dict[str, str] = {}

    def register(self, mime: str, parser: AttachmentParser, extensions: tuple[str, ...] = ()) -> None:
        self._parsers[mime] = parser
        for ext in extensions:
            self._extensions[ext.lower()] = mime

    def resolve_mime(self, mime: str, filename: str) -> str:
        ext = ""
        dot = filename.lower().rfind(".")
        if dot >= 0:
            ext = filename.lower()[dot:]
        if mime in self._parsers:
            return mime
        if ext in self._extensions:
            return self._extensions[ext]
        if mime.startswith("text/"):
            return "text/plain"
        return mime

    def get(self, mime: str, filename: str) -> AttachmentParser | None:
        resolved = self.resolve_mime(mime, filename)
        return self._parsers.get(resolved)


parser_registry = ParserRegistry()


def _register_defaults() -> None:
    from app.services.attachments.parsers.docx_parser import DocxParser
    from app.services.attachments.parsers.pdf_parser import PdfParser
    from app.services.attachments.parsers.pptx_parser import PptxParser
    from app.services.attachments.parsers.text_parser import TextParser
    from app.services.attachments.parsers.xlsx_parser import XlsxParser

    text = TextParser()
    parser_registry.register("text/plain", text, (".txt", ".md", ".markdown", ".csv", ".tsv", ".log", ".ini", ".cfg", ".env", ".sh", ".bat", ".ps1"))
    parser_registry.register("application/json", text, (".json",))
    parser_registry.register("application/xml", text, (".xml", ".html", ".htm"))
    parser_registry.register("application/yaml", text, (".yaml", ".yml"))
    parser_registry.register("application/x-yaml", text, (".yaml", ".yml"))
    for code_ext in (".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs", ".sql"):
        parser_registry.register(f"text/x{code_ext}", text, (code_ext,))

    parser_registry.register("application/pdf", PdfParser(), (".pdf",))
    parser_registry.register(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        DocxParser(),
        (".docx",),
    )
    parser_registry.register(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        XlsxParser(),
        (".xlsx",),
    )
    parser_registry.register(
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        PptxParser(),
        (".pptx",),
    )


_register_defaults()

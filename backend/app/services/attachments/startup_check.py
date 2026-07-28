"""Startup checks for attachment parser dependencies."""

from __future__ import annotations

from app.core.observability import get_logger

logger = get_logger("attachments.startup")

REQUIRED = (
    ("pypdf", "PDF"),
    ("docx", "DOCX"),
    ("openpyxl", "XLSX"),
    ("pptx", "PPTX"),
)


def verify_attachment_parser_dependencies() -> list[str]:
    missing: list[str] = []
    for module, label in REQUIRED:
        try:
            __import__(module)
        except ImportError:
            missing.append(label)
    if missing:
        logger.error(
            "attachment_parser_dependencies_missing",
            missing=missing,
            hint="pip install -r backend/requirements.txt",
        )
    return missing

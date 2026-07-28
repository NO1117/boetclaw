"""XLSX sheet and cell value extraction — formulas as text only."""

from __future__ import annotations

from app.services.attachments.chunking import chunk_plain_sections
from app.services.attachments.models import ChunkLocation, DocumentSummary
from app.services.attachments.parsers import ParseResult


class XlsxParser:
    def parse(self, data: bytes, *, attachment_id: str, filename: str) -> ParseResult:
        try:
            from openpyxl import load_workbook
        except ImportError as exc:
            raise RuntimeError("缺少 XLSX 解析依赖 openpyxl，请安装 requirements.txt") from exc

        import io

        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=False)
        sections: list[tuple[str, ChunkLocation]] = []
        for sheet in wb.worksheets:
            lines: list[str] = []
            for row_idx, row in enumerate(sheet.iter_rows(values_only=False), start=1):
                cells: list[str] = []
                for col_idx, cell in enumerate(row, start=1):
                    value = cell.value
                    if value is None:
                        continue
                    if isinstance(value, str) and value.startswith("="):
                        cached = cell.internal_value if hasattr(cell, "internal_value") else value
                        cells.append(f"{value} -> {cached}")
                    else:
                        cells.append(str(value))
                if cells:
                    lines.append(f"R{row_idx}: " + " | ".join(cells))
            if lines:
                sections.append(("\n".join(lines), ChunkLocation(sheet=sheet.title)))
        wb.close()
        chunks = chunk_plain_sections(attachment_id, sections)
        plain = "\n\n".join(text for text, _ in sections)
        return ParseResult(
            chunks=chunks,
            summary=DocumentSummary(
                sheet_count=len(wb.sheetnames),
                chunk_count=len(chunks),
                char_count=len(plain),
                searchable=len(chunks) > 0,
            ),
            plain_text=plain,
        )

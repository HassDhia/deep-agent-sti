"""Executive letter PDF renderer."""

from __future__ import annotations

import logging
import textwrap
from pathlib import Path
from typing import Any, Dict, List

from .base import BaseRenderer

LOGGER = logging.getLogger(__name__)


class ExecutiveLetterPDFRenderer(BaseRenderer):
    """Render the executive letter markdown into a lightweight PDF."""

    name = "executive_letter_pdf"

    def render(self, report_bundle: Dict[str, Any], report_dir: str) -> List[str]:
        markdown = (report_bundle.get("public_markdown") or report_bundle.get("executive_letter_markdown") or "").strip()
        if not markdown:
            raise ValueError("Executive letter markdown missing from report bundle.")
        base = Path(report_dir)
        output_path = base / "executive_letter.pdf"
        self._write_pdf_from_markdown(markdown, output_path)

        alias_path = base / "market_path_report.pdf"
        try:
            alias_path.write_bytes(output_path.read_bytes())
        except Exception:
            LOGGER.warning("Could not write Market-Path alias PDF", exc_info=True)

        return [str(output_path)]

    def _write_pdf_from_markdown(self, markdown: str, output_path: Path) -> None:
        lines: List[str] = []
        for raw_line in markdown.splitlines():
            cleaned = _sanitize_line(raw_line.rstrip())
            if not cleaned:
                lines.append("")
                continue
            wrapped = textwrap.wrap(cleaned, width=90)
            lines.extend(wrapped or [cleaned])
        _write_simple_pdf(lines or ["Executive letter"], output_path)


def _sanitize_line(text: str) -> str:
    return text.encode("latin-1", "ignore").decode("latin-1")


def _pdf_escape_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _chunk_lines(lines: List[str], chunk_size: int = 45) -> List[List[str]]:
    return [lines[i : i + chunk_size] for i in range(0, len(lines), chunk_size)]


def _build_page_stream(lines: List[str]) -> str:
    y = 760
    commands = ["BT", "/F1 11 Tf"]
    for line in lines:
        safe = _pdf_escape_text(line)
        commands.append(f"1 0 0 1 50 {y} Tm ({safe}) Tj")
        y -= 14
    commands.append("ET")
    return "\n".join(commands)


def _write_simple_pdf(lines: List[str], output_path: Path) -> None:
    chunks = _chunk_lines(lines) or [[]]
    objects: List[Dict[str, Any]] = []

    def add_object(obj: Dict[str, Any]) -> int:
        objects.append(obj)
        obj["_id"] = len(objects)
        return obj["_id"]

    font_id = add_object({"type": "font"})
    page_ids: List[int] = []
    for chunk in chunks:
        stream_data = _build_page_stream(chunk)
        content_id = add_object({"type": "stream", "data": stream_data})
        page_obj = {"type": "page", "content_id": content_id, "font_id": font_id, "parent_id": None}
        page_id = add_object(page_obj)
        page_ids.append(page_id)
    pages_id = add_object({"type": "pages", "kids": page_ids})
    for obj in objects:
        if obj.get("type") == "page":
            obj["parent_id"] = pages_id
    catalog_id = add_object({"type": "catalog", "pages_id": pages_id})

    xref_offsets: List[int] = []
    pieces: List[bytes] = []

    def append_piece(text: str) -> None:
        pieces.append(text.encode("latin-1"))

    append_piece("%PDF-1.4\n")
    for obj in objects:
        xref_offsets.append(sum(len(p) for p in pieces))
        obj_id = obj["_id"]
        body = ""
        if obj["type"] == "font":
            body = "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
        elif obj["type"] == "stream":
            data = obj["data"]
            encoded = data.encode("latin-1", errors="ignore")
            body = f"<< /Length {len(encoded)} >>\nstream\n{data}\nendstream"
        elif obj["type"] == "page":
            body = (
                f"<< /Type /Page /Parent {obj['parent_id']} 0 R "
                f"/Resources << /Font << /F1 {obj['font_id']} 0 R >> >> "
                f"/MediaBox [0 0 612 792] /Contents {obj['content_id']} 0 R >>"
            )
        elif obj["type"] == "pages":
            kids = " ".join(f"{kid} 0 R" for kid in obj["kids"])
            body = f"<< /Type /Pages /Kids [{kids}] /Count {len(obj['kids'])} >>"
        elif obj["type"] == "catalog":
            body = f"<< /Type /Catalog /Pages {obj['pages_id']} 0 R >>"
        append_piece(f"{obj_id} 0 obj\n{body}\nendobj\n")

    xref_start = sum(len(p) for p in pieces)
    append_piece("xref\n0 {}\n".format(len(objects) + 1))
    append_piece("0000000000 65535 f \n")
    for offset in xref_offsets:
        append_piece(f"{offset:010} 00000 n \n")
    append_piece("trailer\n")
    append_piece(f"<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\nstartxref\n{xref_start}\n%%EOF")

    output_path.write_bytes(b"".join(pieces))

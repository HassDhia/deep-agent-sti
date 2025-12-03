"""Market-Path PDF renderer (Typst + fallback)."""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path
from typing import Any, Dict, List

from .base import BaseRenderer
from .context import build_market_path_context
from .templates import render_markdown, render_typst

LOGGER = logging.getLogger(__name__)


class MarketPathPDFRenderer(BaseRenderer):
    """Render Market-Path dossier as a PDF."""

    name = "market_path_pdf"

    def render(self, report_bundle: Dict[str, Any], report_dir: str) -> List[str]:
        deep_link = None
        html_candidate = Path(report_dir) / "intelligence_report.html"
        if html_candidate.exists():
            deep_link = html_candidate.name
        pdf_path = Path(report_dir) / "market_path_report.pdf"
        letter_markdown = (report_bundle.get("executive_letter_markdown") or "").strip()
        if letter_markdown:
            LOGGER.info("Rendering Market-Path PDF from executive letter markdown.")
            self._write_pdf_from_markdown(letter_markdown, pdf_path)
            return [str(pdf_path)]
        context = build_market_path_context(report_bundle, deep_link=deep_link, report_dir=report_dir)
        if not self._render_with_typst(context, pdf_path):
            LOGGER.info("Typst not available. Falling back to inline PDF writer.")
            self._render_fallback_pdf(context, pdf_path)
        return [str(pdf_path)]

    def _render_with_typst(self, context: Dict[str, Any], output_path: Path) -> bool:
        typst_bin = shutil.which("typst")
        if not typst_bin:
            return False
        typst_source = render_typst(context)
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                typst_file = Path(tmpdir) / "market_path_report.typ"
                typst_file.write_text(typst_source, encoding="utf-8")
                subprocess.run(
                    [typst_bin, "compile", str(typst_file), str(output_path)],
                    check=True,
                    capture_output=True,
                )
            return output_path.exists()
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            LOGGER.warning("Typst rendering failed: %s", exc)
            return False

    def _render_fallback_pdf(self, context: Dict[str, Any], output_path: Path) -> None:
        markdown = render_markdown(context)
        self._write_pdf_from_markdown(markdown, output_path)

    def _write_pdf_from_markdown(self, markdown: str, output_path: Path) -> None:
        lines: List[str] = []
        for raw_line in markdown.splitlines():
            cleaned = _sanitize_line(raw_line.rstrip())
            if not cleaned:
                lines.append("")
                continue
            wrapped = textwrap.wrap(cleaned, width=90)
            if wrapped:
                lines.extend(wrapped)
            else:
                lines.append(cleaned)
        _write_simple_pdf(lines or ["Market-Path dossier"], output_path)


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


def _sanitize_line(text: str) -> str:
    return text.encode("latin-1", "ignore").decode("latin-1")

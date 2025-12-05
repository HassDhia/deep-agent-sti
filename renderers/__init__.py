"""Renderer registry."""

from __future__ import annotations

from typing import List

from .base import BaseRenderer


def _normalized(name: str) -> str:
    return (name or "").strip().lower()


def get_renderer(name: str) -> BaseRenderer:
    normalized = _normalized(name)
    if normalized in {"executive_letter_markdown", "market_path_markdown"}:
        from .executive_letter_markdown import ExecutiveLetterMarkdownRenderer

        return ExecutiveLetterMarkdownRenderer()
    if normalized in {"executive_letter_pdf", "market_path_pdf"}:
        from .executive_letter_pdf import ExecutiveLetterPDFRenderer

        return ExecutiveLetterPDFRenderer()
    if normalized in {"legacy_html", "html"}:
        from .legacy_html import LegacyHTMLRenderer

        return LegacyHTMLRenderer()
    raise ValueError(f"Unknown renderer '{name}'")


def available_renderers() -> List[str]:
    return ["executive_letter_markdown", "executive_letter_pdf", "legacy_html"]

"""Renderer registry."""

from __future__ import annotations

from typing import Dict, List

from .base import BaseRenderer


def _normalized(name: str) -> str:
    return (name or "").strip().lower()


def get_renderer(name: str) -> BaseRenderer:
    normalized = _normalized(name)
    if normalized == "market_path_markdown":
        from .market_path_markdown import MarketPathMarkdownRenderer

        return MarketPathMarkdownRenderer()
    if normalized == "market_path_pdf":
        from .market_path_pdf import MarketPathPDFRenderer

        return MarketPathPDFRenderer()
    if normalized in {"legacy_html", "html"}:
        from .legacy_html import LegacyHTMLRenderer

        return LegacyHTMLRenderer()
    raise ValueError(f"Unknown renderer '{name}'")


def available_renderers() -> List[str]:
    return ["market_path_markdown", "market_path_pdf", "legacy_html"]

"""Market-Path Markdown renderer."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from .base import BaseRenderer
from .context import build_market_path_context
from .templates import render_markdown


class MarketPathMarkdownRenderer(BaseRenderer):
    """Render the Market-Path dossier as Markdown."""

    name = "market_path_markdown"

    def render(self, report_bundle: Dict[str, Any], report_dir: str) -> List[str]:
        base = Path(report_dir)
        deep_link = None
        html_candidate = base / "intelligence_report.html"
        if html_candidate.exists():
            deep_link = html_candidate.name
        letter_markdown = (report_bundle.get("executive_letter_markdown") or "").strip()
        if letter_markdown:
            markdown = letter_markdown
        else:
            artifact_links = []
            pdf_candidate = base / "market_path_report.pdf"
            if pdf_candidate.exists():
                artifact_links.append({"label": "Download PDF dossier", "href": pdf_candidate.name})
            if deep_link:
                artifact_links.append({"label": "Read HTML intelligence report", "href": deep_link})
            context = build_market_path_context(
                report_bundle,
                deep_link=deep_link,
                artifact_links=artifact_links,
                report_dir=report_dir,
            )
            markdown = render_markdown(context)
        output_path = Path(report_dir) / "market_path_report.md"
        output_path.write_text(markdown.strip() + "\n", encoding="utf-8")
        return [str(output_path)]

"""Executive letter Markdown renderer."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from .base import BaseRenderer


class ExecutiveLetterMarkdownRenderer(BaseRenderer):
    """Persist the executive letter markdown (plus backward-compatible alias)."""

    name = "executive_letter_markdown"

    def render(self, report_bundle: Dict[str, Any], report_dir: str) -> List[str]:
        markdown = (report_bundle.get("public_markdown") or report_bundle.get("executive_letter_markdown") or "").strip()
        if not markdown:
            raise ValueError("Executive letter markdown missing from report bundle.")
        base = Path(report_dir)
        output_path = base / "executive_letter.md"
        output_path.write_text(markdown + "\n", encoding="utf-8")

        # Maintain legacy compatibility for any automation that still looks for Market-Path files.
        alias_path = base / "market_path_report.md"
        alias_path.write_text(markdown + "\n", encoding="utf-8")

        return [str(output_path)]

"""Markdown → HTML renderer that wraps HTMLConverterAgent."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Set

from config import STIConfig
from html_converter_agent import HTMLConverterAgent
from markdown_utils import insert_image_anchors
from visual_lint import REQUIRED_ANCHORS, lint_visual_stats

from .base import BaseRenderer

logger = logging.getLogger(__name__)


class LegacyHTMLRenderer(BaseRenderer):
    """Render minimalist HTML companions for both Markdown artifacts."""

    name = "legacy_html"

    def __init__(self) -> None:
        self.converter = HTMLConverterAgent()

    def render(self, report_bundle: Dict[str, Any], report_dir: str) -> List[str]:
        outputs: List[str] = []
        base = Path(report_dir)
        intel_path = base / "intelligence_report.md"
        market_path = base / "market_path_report.md"
        shared_meta = self._build_metadata(report_bundle)
        image_context = self.converter.build_image_context(report_dir, shared_meta)

        sections = report_bundle.get("sections")
        required_anchors: Set[str] = set(report_bundle.get("visual_required_anchors") or []) or set(REQUIRED_ANCHORS)

        def _write_visual_stats(stats: Dict[str, Any]) -> None:
            if not stats:
                return
            payload = dict(stats)
            payload["required_anchors"] = sorted(required_anchors)
            try:
                (base / "visual_stats.json").write_text(
                    json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
            except Exception:
                logger.warning("Could not write visual stats for %s", base, exc_info=True)

        def _enforce_visuals(label: str) -> None:
            stats = self.converter.last_visual_stats or {}
            issues = lint_visual_stats(stats, required_anchors=required_anchors)
            warnings = [issue for issue in issues if issue.startswith("WARN:")]
            errors = [issue for issue in issues if issue.startswith("ERROR:")]
            for warning in warnings:
                logger.warning("%s - %s", label, warning)
            _write_visual_stats(stats)
            if errors:
                raise RuntimeError(f"Visual lint failed for {label}: {errors}")

        if intel_path.exists():
            intel_text = intel_path.read_text(encoding="utf-8")
            intel_text = insert_image_anchors(intel_text, sections)
            intel_title = (
                report_bundle.get("title")
                or self.converter._first_heading(intel_text)
                or "Operator Briefing"
            )
            html = self.converter.convert_markdown_article(
                intel_text,
                title=intel_title,
                metadata=shared_meta,
                subtitle=report_bundle.get("query"),
                images=image_context,
            )
            _enforce_visuals("intelligence_report.html")
            intel_output = intel_path.with_suffix(".html")
            intel_output.write_text(html, encoding="utf-8")
            outputs.append(str(intel_output))
        if market_path.exists():
            market_text = market_path.read_text(encoding="utf-8")
            market_text = insert_image_anchors(market_text, sections)
            market_title = self.converter._first_heading(market_text) or "Market-Path Dossier"
            market_meta = {**shared_meta, "report_label": "Market-Path Dossier"}
            html = self.converter.convert_markdown_article(
                market_text,
                title=market_title,
                metadata=market_meta,
                subtitle="Market-Path collaboration brief",
                images=image_context,
            )
            _enforce_visuals("market_path_report.html")
            market_output = market_path.with_suffix(".html")
            market_output.write_text(html, encoding="utf-8")
            outputs.append(str(market_output))

        return outputs

    def _build_metadata(self, bundle: Dict[str, Any]) -> Dict[str, Any]:
        window = bundle.get("time_window") or {}
        start = window.get("start") or ""
        end = window.get("end") or ""
        if start and end:
            window_label = f"{start} → {end}"
        else:
            window_label = start or end or "Active window"
        read_time = bundle.get("read_time_minutes") or STIConfig.TARGET_READ_TIME_MINUTES
        confidence = bundle.get("confidence") or {}
        confidence_label = confidence.get("band") or confidence.get("label")
        if not confidence_label and confidence.get("score") is not None:
            confidence_label = f"Score {confidence['score']:.2f}" if isinstance(confidence["score"], (int, float)) else str(confidence["score"])
        qa_scope = (bundle.get("qa") or {}).get("scope") or {}
        region = qa_scope.get("target_region") or bundle.get("region") or "US"
        metadata = {
            "window": window_label,
            "read_time": f"~{read_time} min read",
            "confidence": confidence_label,
            "region": region,
            "generated_at": bundle.get("generated_at"),
        }
        return metadata

"""
File utilities for the operator-focused STI workflow.

Handles report directory creation, markdown/HTML/json saves, and optional
social content persistence.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, List, Optional, Tuple

from config import STIConfig
from image_generator import ImageGenerator
from markdown_utils import insert_image_anchors
from renderers import get_renderer

logger = logging.getLogger(__name__)


def compute_content_sha(content: str) -> str:
    import hashlib

    return hashlib.sha256((content or "").encode("utf-8")).hexdigest()


def _atomic_write_text(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", delete=False, encoding="utf-8", dir=str(path.parent)) as tmp:
        tmp.write(data)
        tmp_name = tmp.name
    os.replace(tmp_name, path)


def write_text(path: Path, content: str) -> None:
    _atomic_write_text(path, content)


def write_json(path: Path, payload: Any) -> None:
    serialized = json.dumps(payload, indent=2, ensure_ascii=False)
    _atomic_write_text(path, serialized)


class STIFileManager:
    def __init__(self, base_output_dir: str = "sti_reports"):
        self.base_output_dir = base_output_dir
        Path(self.base_output_dir).mkdir(exist_ok=True)

    def create_report_directory(self, agent_type: str, query: str, days_back: int) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        query_slug = "".join(c.lower() if c.isalnum() else "_" for c in query)[:24]
        dirname = f"sti_{agent_type}_output_{timestamp}_{query_slug}"
        path = Path(self.base_output_dir) / dirname
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    def save_enhanced_report(
        self, report_bundle: Dict[str, Any], generate_html: bool = True, report_dir: Optional[str] = None
    ) -> str:
        query = report_bundle.get("query", "STI Brief")
        window = report_bundle.get("time_window", {})
        days_back = int(window.get("days", STIConfig.DEFAULT_DAYS_BACK))
        report_dir = report_dir or self.create_report_directory("operator", query, days_back)

        markdown = report_bundle.get("markdown", "")
        sections = report_bundle.get("sections")
        markdown = insert_image_anchors(markdown, sections)
        write_text(Path(report_dir) / "intelligence_report.md", markdown)
        write_json(Path(report_dir) / "intelligence_report.jsonld", report_bundle.get("json_ld", {}))

        source_stats = report_bundle.get("source_stats", {})
        metadata = {
            "generated_at": datetime.now().isoformat(),
            "query": query,
            "time_window": window,
            "confidence": report_bundle.get("confidence"),
            "files": STIConfig.OUTPUT_FILES,
            "sections": list(report_bundle.get("sections", {}).keys()),
            "title": report_bundle.get("title"),
            "highlights": report_bundle.get("highlights", []),
            "executive_summary": report_bundle.get("executive_summary", ""),
            "top_operator_moves": report_bundle.get("top_operator_moves", []),
            "statistics": {
                "word_count": len(markdown.split()),
                "signal_count": len(report_bundle.get("signals", [])),
                "source_count": len(report_bundle.get("sources", [])),
            },
            "read_time_minutes": report_bundle.get("read_time_minutes"),
            "length_label": f"~{report_bundle.get('read_time_minutes', STIConfig.TARGET_READ_TIME_MINUTES)} min read",
            "qa": report_bundle.get("qa", {}),
        }
        metadata.update(report_bundle.get("metadata", {}))
        if source_stats:
            metadata["source_stats"] = source_stats
        write_json(Path(report_dir) / "metadata.json", metadata)
        write_json(Path(report_dir) / "sources.json", report_bundle.get("sources", []))
        write_json(Path(report_dir) / "signals.json", report_bundle.get("signals", []))
        write_json(Path(report_dir) / "sections.json", report_bundle.get("sections", {}))
        write_json(Path(report_dir) / "quant.json", report_bundle.get("quant", {}))
        write_json(Path(report_dir) / "appendix_signals.json", report_bundle.get("appendix_signals", []))
        if source_stats:
            write_json(Path(report_dir) / "source_stats.json", source_stats)

        briefs = report_bundle.get("image_briefs")
        if briefs:
            images_dir = Path(report_dir) / "images"
            images_dir.mkdir(exist_ok=True, parents=True)
            write_json(images_dir / "briefs.json", briefs)
            self._maybe_generate_images(report_bundle, report_dir, briefs)

        rendered_files: List[str] = []
        renderer_queue = list(STIConfig.REPORT_RENDERERS)
        if generate_html and "legacy_html" not in renderer_queue:
            renderer_queue.append("legacy_html")
        for renderer_name in renderer_queue:
            try:
                renderer = get_renderer(renderer_name)
            except ValueError:
                logger.warning("Unknown renderer '%s' requested. Skipping.", renderer_name)
                continue
            try:
                rendered_files.extend(renderer.render(report_bundle, report_dir))
            except Exception as exc:
                logger.error("Renderer %s failed: %s", renderer_name, exc)

        if rendered_files:
            metadata_path = Path(report_dir) / "metadata.json"
            metadata_payload = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata_payload["renderers"] = renderer_queue
            metadata_payload["artifact_paths"] = rendered_files
            write_json(metadata_path, metadata_payload)

        self._log_summary(report_dir, metadata)
        return report_dir

    def _maybe_generate_images(self, bundle: Dict[str, Any], report_dir: str, briefs: Dict[str, Any]) -> None:
        if not STIConfig.ENABLE_IMAGE_GENERATION:
            logger.debug("Image generation disabled via config")
            return
        try:
            generator = ImageGenerator()
        except Exception as exc:
            logger.warning("ImageGenerator initialization failed: %s", exc)
            return
        if not getattr(generator, "client", None):
            logger.warning("Image generation skipped: OpenAI client not initialized (set OPENAI_API_KEY)")
            return
        query = bundle.get("query", "Operator Brief")
        exec_summary = bundle.get("executive_summary")
        confidence = (bundle.get("confidence") or {}).get("score")
        hero_brief = briefs.get("hero") if isinstance(briefs, dict) else None
        if isinstance(hero_brief, dict):
            try:
                generator.generate_hero_image(
                    query,
                    report_dir,
                    intent="market",
                    exec_summary=exec_summary,
                    anchor_coverage=confidence,
                    hero_brief=hero_brief,
                )
            except Exception as exc:
                logger.warning("Hero image generation failed: %s", exc)
        sections_payload = self._image_section_payload(bundle, briefs)
        if not sections_payload:
            return
        max_sections = getattr(STIConfig, "MAX_SECTION_IMAGES", 0)
        generated = 0
        for section_name, section_content, section_brief in sections_payload:
            if max_sections and generated >= max_sections:
                break
            try:
                result = generator.generate_section_image(
                    section_name,
                    section_content,
                    query,
                    "market",
                    report_dir,
                    anchor_coverage=confidence,
                    brief=section_brief,
                )
                if result:
                    generated += 1
            except Exception as exc:
                logger.warning("Section image '%s' failed: %s", section_name, exc)

    def _image_section_payload(self, bundle: Dict[str, Any], briefs: Dict[str, Any]) -> List[Tuple[str, str, Dict[str, Any]]]:
        payload: List[Tuple[str, str, Dict[str, Any]]] = []
        sections = bundle.get("sections", {}) or {}
        if isinstance(briefs, dict):
            signal_brief = briefs.get("signal_map")
            if isinstance(signal_brief, dict):
                content = sections.get("signal_map_notes") or self._flatten_brief(signal_brief)
                payload.append(("Signal Map", content, signal_brief))
            for idx, case_brief in enumerate(briefs.get("case_studies") or []):
                if not isinstance(case_brief, dict):
                    continue
                label = f"Case Study {idx + 1}"
                content = self._flatten_brief(case_brief)
                payload.append((label, content, case_brief))
        return payload

    def _flatten_brief(self, brief: Dict[str, Any]) -> str:
        if not isinstance(brief, dict):
            return str(brief)
        fragments: List[str] = []
        for key, value in brief.items():
            if not value:
                continue
            if isinstance(value, list):
                value = ", ".join(str(v) for v in value if v)
            elif isinstance(value, dict):
                value = ", ".join(f"{k}:{v}" for k, v in value.items())
            fragments.append(f"{key}: {value}")
        return " | ".join(fragments)

    def save_social_media_content(self, report_dir: str, social_content: Dict[str, Any]) -> None:
        try:
            write_text(Path(report_dir) / "social_media_post.md", social_content.get("long_form", ""))
            write_text(
                Path(report_dir) / "social_media_thread.txt",
                "\n".join(social_content.get("twitter_thread", [])),
            )
            write_text(
                Path(report_dir) / "social_media_linkedin.txt",
                social_content.get("linkedin_post", ""),
            )
            metadata_path = Path(report_dir) / "metadata.json"
            if metadata_path.exists():
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                metadata["social_media_content"] = social_content.get("metadata", {})
                write_json(metadata_path, metadata)
        except Exception as exc:
            logger.error(f"Error saving social media content: {exc}")

    def get_latest_report(self, agent_type: Optional[str] = None) -> Optional[str]:
        reports = self.list_all_reports(agent_type)
        return reports[0] if reports else None

    def list_all_reports(self, agent_type: Optional[str] = None) -> List[str]:
        base = Path(self.base_output_dir)
        if not base.exists():
            return []
        reports = []
        for entry in base.iterdir():
            if not entry.is_dir():
                continue
            if agent_type and f"_{agent_type}_" not in entry.name:
                continue
            reports.append(str(entry))
        reports.sort(key=os.path.getmtime, reverse=True)
        return reports

    def _log_summary(self, report_dir: str, metadata: Dict[str, Any]) -> None:
        logger.info("💾 Report saved to %s", report_dir)
        logger.info(
            "   -> %s sources | %s signals | confidence %.2f",
            metadata["statistics"]["source_count"],
            metadata["statistics"]["signal_count"],
            metadata.get("confidence", {}).get("score", 0.0),
        )


file_manager = STIFileManager()


def save_enhanced_report_auto(
    report_bundle: Dict[str, Any], generate_html: bool = True, report_dir: Optional[str] = None
) -> str:
    return file_manager.save_enhanced_report(report_bundle, generate_html=generate_html, report_dir=report_dir)

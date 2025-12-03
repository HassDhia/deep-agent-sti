"""Minimal Markdown → HTML conversion utilities."""

from __future__ import annotations

import html
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import markdown
from jinja2 import Environment, FileSystemLoader, select_autoescape

from config import STIConfig
from metrics import friendly_metric_name

logger = logging.getLogger(__name__)


class HTMLConverterAgent:
    """Render minimalist HTML articles from Markdown artifacts."""

    def __init__(self, template_path: str | None = None) -> None:
        self.article_template_path = Path(template_path or STIConfig.MARKDOWN_HTML_TEMPLATE)
        self._ensure_template(self.article_template_path)
        self.env = Environment(
            loader=FileSystemLoader([str(self.article_template_path.parent)]),
            autoescape=select_autoescape(["html"]),
        )
        self.article_template = self.env.get_template(self.article_template_path.name)
        self.last_visual_stats: Dict[str, Any] = {}

    def _ensure_template(self, path: Path) -> None:
        if not path.exists():
            raise FileNotFoundError(
                f"Template not found at {path}. Regenerate templates/ from archive if necessary."
            )

    def convert(self, report_bundle: Dict[str, Any], report_dir: str) -> str:
        """Render the primary intelligence Markdown into minimalist HTML."""

        base = Path(report_dir)
        markdown_path = base / "intelligence_report.md"
        markdown_text = report_bundle.get("markdown", "")
        if markdown_path.exists():
            markdown_text = markdown_path.read_text(encoding="utf-8")
        title = (
            report_bundle.get("title")
            or self._first_heading(markdown_text)
            or "Operator Briefing"
        )
        metadata = self._bundle_metadata(report_bundle)
        subtitle = report_bundle.get("query") or metadata.get("subtitle")
        image_context = self.build_image_context(report_dir, metadata)
        return self.convert_markdown_article(
            markdown_text,
            title=title,
            metadata=metadata,
            subtitle=subtitle,
            images=image_context,
        )

    def convert_markdown_article(
        self,
        markdown_text: str,
        *,
        title: str,
        metadata: Optional[Dict[str, Any]] = None,
        subtitle: Optional[str] = None,
        images: Optional[Dict[str, Any]] = None,
    ) -> str:
        metadata = metadata or {}
        cleaned_title = (title or metadata.get("title") or "Operator Briefing").strip()
        subtitle = subtitle or metadata.get("subtitle") or metadata.get("query") or ""
        article_body = markdown.markdown(
            markdown_text or "",
            extensions=["extra", "sane_lists", "toc", "tables"],
            output_format="html5",
        )
        article_body, visual_stats = self._inject_inline_images(article_body, images or {})
        meta_items = self._markdown_meta(metadata)
        updated_at = metadata.get("updated_at") or metadata.get("generated_at")
        if isinstance(updated_at, datetime):
            updated_display = updated_at.strftime("%b %d, %Y")
        else:
            updated_display = updated_at or datetime.now().strftime("%b %d, %Y")
        used_slots = set(visual_stats.get("anchors_with_images", []))
        remaining_sections = self._remaining_gallery_images(
            (images or {}).get("sections", []),
            used_slots,
        )
        visual_stats["gallery_size"] = len(remaining_sections)
        self.last_visual_stats = visual_stats
        self._log_visual_stats(visual_stats)
        context = {
            "article_title": cleaned_title or "Operator Briefing",
            "subtitle": subtitle.strip(),
            "meta": meta_items,
            "updated_at": updated_display,
            "article_body": article_body,
            "tagline": STIConfig.BRAND_TAGLINE,
            "hero_image": (images or {}).get("hero"),
            "section_images": remaining_sections,
        }
        return self.article_template.render(**context)

    def convert_markdown_file(
        self,
        path: Path,
        *,
        title: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        subtitle: Optional[str] = None,
        images: Optional[Dict[str, Any]] = None,
    ) -> str:
        text = Path(path).read_text(encoding="utf-8")
        derived_title = title or self._first_heading(text) or "Operator Brief"
        return self.convert_markdown_article(
            text,
            title=derived_title,
            metadata=metadata,
            subtitle=subtitle,
            images=images,
        )

    def render_markdown_gallery(
        self,
        report_dir: str | Path,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        context = self.build_image_context(report_dir, metadata)
        hero = context.get("hero")
        sections = context.get("sections", [])
        gallery_lines: List[str] = []
        if hero:
            alt = hero.get("alt") or "Operator illustration"
            src = hero.get("src")
            if src:
                gallery_lines.append("### Visual Hero")
                gallery_lines.append(f"![{alt}]({src})")
                caption = hero.get("caption")
                if caption:
                    gallery_lines.append(f"*{caption}*")
        if sections:
            section_lines: List[str] = []
            for entry in sections:
                src = entry.get("src")
                if not src:
                    continue
                alt = entry.get("alt") or "Operator visual"
                section_lines.append(f"![{alt}]({src})")
                description = entry.get("description") or ""
                label = entry.get("label")
                caption = description
                if label:
                    caption = f"{label}: {description}" if description else label
                if caption:
                    section_lines.append(f"*{caption.strip()}*")
            if section_lines:
                gallery_lines.append("### Visual Notes")
                gallery_lines.extend(section_lines)
        if not gallery_lines:
            return ""
        return "\n\n".join(["---", *gallery_lines, "---"]).strip()

    def _bundle_metadata(self, bundle: Dict[str, Any]) -> Dict[str, Any]:
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
        score = confidence.get("score")
        if not confidence_label and score is not None:
            confidence_label = f"Score {score:.2f}" if isinstance(score, (int, float)) else str(score)
        qa_scope = (bundle.get("qa") or {}).get("scope") or {}
        region = qa_scope.get("target_region") or bundle.get("region") or "US"
        metadata = {
            "window": window_label,
            "read_time": f"~{read_time} min read",
            "confidence": confidence_label,
            "region": region,
            "generated_at": bundle.get("generated_at"),
        }
        evidence_note = bundle.get("evidence_note")
        if evidence_note:
            metadata["evidence"] = evidence_note
        return metadata

    def _markdown_meta(self, metadata: Dict[str, Any]) -> List[Dict[str, str]]:
        items: List[Dict[str, str]] = []
        ordered = [
            ("Window", metadata.get("window")),
            ("Read time", metadata.get("read_time")),
            ("Confidence", metadata.get("confidence")),
            ("Region", metadata.get("region")),
            ("Evidence", metadata.get("evidence")),
        ]
        for label, value in ordered:
            if value:
                items.append({"label": label, "value": str(value)})
        for extra in metadata.get("extra_meta", []):
            label = extra.get("label")
            value = extra.get("value")
            if label and value:
                items.append({"label": str(label), "value": str(value)})
        if not items:
            default_label = metadata.get("report_label", "Report")
            items.append({"label": "Report", "value": str(default_label)})
        return items

    @staticmethod
    def _first_heading(markdown_text: str) -> Optional[str]:
        for line in (markdown_text or "").splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                return stripped.lstrip("#").strip()
        return None

    def build_image_context(
        self,
        report_dir: str | Path,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        base = Path(report_dir)
        manifest_path = base / "images" / "manifest.json"
        briefs_path = base / "images" / "briefs.json"
        manifest = self._load_json_list(manifest_path)
        briefs = self._load_json_dict(briefs_path)
        images: Dict[str, Any] = {"hero": None, "sections": []}
        if not manifest:
            return images
        hero_entry = next((entry for entry in manifest if entry.get("type") == "hero"), None)
        if hero_entry:
            hero_brief = briefs.get("hero") if isinstance(briefs.get("hero"), dict) else {}
            images["hero"] = self._hero_image_payload(hero_entry, hero_brief, metadata or {})
        for entry in manifest:
            if entry.get("type") != "section":
                continue
            payload = self._section_image_payload(entry, briefs)
            if payload:
                images["sections"].append(payload)
        return images

    def _hero_image_payload(
        self,
        entry: Dict[str, Any],
        brief: Dict[str, Any],
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        source = entry.get("image")
        if not source:
            return {}
        caption_parts = []
        for key in ("core_tension", "action", "mood"):
            value = brief.get(key)
            if value:
                caption_parts.append(str(value).strip())
        caption = " ".join(caption_parts)
        alt = brief.get("alt") or entry.get("alt") or self._prompt_alt(None)
        meta_items: List[Dict[str, str]] = []
        if metadata.get("window"):
            meta_items.append({"label": "Window", "value": metadata["window"]})
        if metadata.get("read_time"):
            meta_items.append({"label": "Read", "value": metadata["read_time"]})
        if metadata.get("confidence"):
            meta_items.append({"label": "Confidence", "value": metadata["confidence"]})
        return {
            "src": source,
            "alt": alt,
            "caption": caption,
            "meta": meta_items,
            "slot": self._normalize_slot_name("hero"),
            "anchor_section": brief.get("anchor_section"),
            "metric_focus": self._coerce_metric_focus(brief.get("metric_focus")),
        }

    def _section_image_payload(self, entry: Dict[str, Any], briefs: Dict[str, Any]) -> Optional[Dict[str, str]]:
        source = entry.get("image")
        if not source:
            return None
        label = entry.get("section") or entry.get("type", "Section")
        slot = self._normalize_slot_name(label or entry.get("type"))
        normalized = (label or "").lower()
        alt = None
        description = None
        anchor_source: Dict[str, Any] = {}
        brief_signal = briefs.get("signal_map") if isinstance(briefs.get("signal_map"), dict) else {}
        brief_cases = briefs.get("case_studies") if isinstance(briefs.get("case_studies"), list) else []
        if "signal" in normalized:
            anchor_source = brief_signal
            alt = brief_signal.get("alt")
            description = brief_signal.get("structure") or brief_signal.get("motion")
        elif "case" in normalized:
            idx = self._case_study_index(normalized)
            if idx is not None and 0 <= idx < len(brief_cases):
                anchor_source = brief_cases[idx] or {}
                alt = anchor_source.get("alt")
                description = anchor_source.get("scene") or anchor_source.get("moment")
        if not alt:
            alt = self._prompt_alt(None)
        if not description:
            description = "Signal visualization" if "signal" in normalized else "Operator vignette"
        return {
            "src": source,
            "alt": alt,
            "label": label,
            "description": description,
            "slot": slot,
            "anchor_section": anchor_source.get("anchor_section"),
            "metric_focus": self._coerce_metric_focus(anchor_source.get("metric_focus")),
        }

    @staticmethod
    def _case_study_index(label: str) -> Optional[int]:
        match = re.search(r"(\d+)", label)
        if not match:
            return None
        try:
            return int(match.group(1)) - 1
        except ValueError:
            return None

    @staticmethod
    def _prompt_alt(prompt: Optional[str]) -> str:
        if not prompt:
            return "Operator illustration"
        sentence = prompt.strip().split(".")[0]
        return sentence[:140].strip() or "Operator illustration"

    @staticmethod
    def _load_json_list(path: Path) -> List[Dict[str, Any]]:
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            logger.debug("Could not parse %s", path)
            return []

    @staticmethod
    def _load_json_dict(path: Path) -> Dict[str, Any]:
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            logger.debug("Could not parse %s", path)
            return {}

    def _inject_inline_images(self, article_html: str, images: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        stats: Dict[str, Any] = {
            "anchors_found": [],
            "anchors_with_images": [],
            "anchors_missing_images": [],
            "images_without_anchor": [],
        }
        if not article_html:
            return article_html, stats
        sections = (images or {}).get("sections") or []
        slot_map: Dict[str, Dict[str, Any]] = {}
        for entry in sections:
            slot = self._normalize_slot_name(entry.get("slot") or entry.get("label"))
            src = entry.get("src")
            if not slot or not src:
                continue
            slot_map[slot] = entry
        pattern = re.compile(r"<!--\s*image:([a-z0-9_\-]+)\s*-->", re.I)
        matches = list(pattern.finditer(article_html))
        anchors_found = [match.group(1).lower() for match in matches]
        stats["anchors_found"] = sorted(set(anchors_found))
        if not slot_map or not anchors_found:
            stats["images_without_anchor"] = sorted(set(slot_map.keys()) - set(anchors_found))
            return pattern.sub("", article_html), stats
        used: Set[str] = set()

        def replace(match: re.Match[str]) -> str:
            key = match.group(1).lower()
            image = slot_map.get(key)
            if not image:
                return ""
            figure_html = self._render_inline_figure(image)
            if not figure_html:
                return ""
            used.add(key)
            return figure_html

        updated = re.sub(pattern, replace, article_html)
        stats["anchors_with_images"] = sorted(used)
        stats["anchors_missing_images"] = sorted(set(anchors_found) - used)
        stats["images_without_anchor"] = sorted(set(slot_map.keys()) - set(anchors_found))
        return updated, stats

    def _render_inline_figure(self, image: Dict[str, Any]) -> str:
        src = image.get("src")
        if not src:
            return ""
        alt = html.escape(image.get("alt") or "Operator visual")
        fig_label = html.escape(image.get("label") or "")
        description = html.escape(image.get("description") or "")
        raw_metrics = [
            str(metric).strip()
            for metric in (image.get("metric_focus") or [])
            if str(metric).strip()
        ]
        friendly_metrics: List[str] = []
        for metric in raw_metrics:
            metric_label = friendly_metric_name(metric)
            if metric_label:
                friendly_metrics.append(metric_label)
        metrics = [html.escape(name) for name in friendly_metrics]
        metrics_html = ""
        if metrics:
            chips = "".join(f"<span>{metric}</span>" for metric in metrics)
            metrics_html = f'<div class="metrics">{chips}</div>'
        caption_parts: List[str] = []
        if fig_label:
            caption_parts.append(f'<div class="label">{fig_label}</div>')
        if description:
            caption_parts.append(f'<div class="description">{description}</div>')
        caption = "".join(caption_parts)
        if metrics_html:
            caption += metrics_html
        if friendly_metrics:
            caption += f'<div class="metrics-focus">Focus: {" · ".join(metrics)}</div>'
        return (
            '<figure class="inline-visual">'
            f'<img src="{html.escape(str(src))}" alt="{alt}" loading="lazy" />'
            f"<figcaption>{caption}</figcaption>"
            "</figure>"
        )

    def _remaining_gallery_images(
        self,
        sections: Optional[List[Dict[str, Any]]],
        used_slots: Set[str],
    ) -> List[Dict[str, Any]]:
        if not sections:
            return []
        remaining: List[Dict[str, Any]] = []
        for entry in sections:
            slot = self._normalize_slot_name(entry.get("slot") or entry.get("label"))
            if slot and slot in used_slots:
                continue
            remaining.append(entry)
        return remaining

    @staticmethod
    def _normalize_slot_name(value: Optional[str]) -> str:
        if not value:
            return ""
        slug = re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")
        return slug

    @staticmethod
    def _coerce_metric_focus(value: Any) -> List[str]:
        if not value:
            return []
        if isinstance(value, str):
            candidates = [value]
        elif isinstance(value, list):
            candidates = value
        else:
            candidates = [value]
        results: List[str] = []
        for item in candidates[:3]:
            text = str(item).strip()
            if text:
                results.append(text)
        return results

    def _log_visual_stats(self, stats: Dict[str, Any]) -> None:
        try:
            logger.info(
                "Visual stats: anchors=%s used=%s gallery=%s missing=%s",
                len(stats.get("anchors_found", [])),
                len(stats.get("anchors_with_images", [])),
                stats.get("gallery_size", 0),
                stats.get("anchors_missing_images"),
            )
        except Exception:
            logger.debug("Could not log visual stats", exc_info=True)

"""
Operator-focused Enhanced Agent

Collects sources, extracts signals, and composes the Brand Collab Lab report
without thesis routing or academic infrastructure.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import math
import os
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from analysis_contracts import lint_quant_blocks, lint_operator_specs
from operator_specs_normalization import normalize_operator_specs
from quant_normalization import normalize_quant_blocks_payload
from config import STIConfig
from confidence import ConfidenceBreakdown, headline as confidence_headline
from metrics import anchor_stage, friendly_metric_label, known_metric_ids, replace_metric_tokens
from servers.analysis_server import (
    generate_activation_kit,
    generate_brand_outcomes,
    generate_comparison_map,
    generate_deep_analysis,
    generate_future_outlook,
    generate_quant_blocks,
    generate_operator_specs,
    generate_image_briefs,
    generate_executive_letter,
    generate_pattern_matches,
    generate_risk_radar,
    generate_signal_map,
    write_executive_summary,
)

logger = logging.getLogger(__name__)
GRADE_ORDER = {"A": 0, "B": 1, "C": 2, "D": 3}


@dataclass
class SourceRecord:
    id: int
    title: str
    url: str
    publisher: str
    date: str
    snippet: str
    content: str
    credibility: float
    region: str = "US"
    domain: str = "general"
    source_type: str = "analysis"
    evidence: Dict[str, Any] = dataclasses.field(default_factory=dict)
    authority: float = 0.0
    recency: float = 0.0
    us_fit: float = 0.0
    quality: float = 0.0
    role: str = "support"
    source_grade: str = "C"
    tier: str = "core"


class EnhancedSTIAgent:
    """Single-path operator agent."""

    def __init__(
        self,
        openai_api_key: str,
        tavily_api_key: str = "",
        model_name: str = None,
        trace_mode: bool = False,
    ):
        self.openai_api_key = openai_api_key
        self.tavily_api_key = tavily_api_key
        self.model_name = model_name or STIConfig.DEFAULT_MODEL
        self.trace_mode = trace_mode

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def generate_report(self, query: str, days_back: int = STIConfig.DEFAULT_DAYS_BACK) -> Dict[str, Any]:
        self._trace("generate_report:start", {"query": query, "days_back": days_back})
        scope = self._build_scope(query, days_back)
        scope_json = json.dumps(scope, ensure_ascii=False)
        sources = self._collect_sources(query, days_back, scope)
        if not sources:
            raise RuntimeError("No sources found for query. Adjust the query or ensure search backend is running.")
        source_stats = self._source_statistics(sources)
        scope["thin_evidence"] = False

        sources_payload = json.dumps([asdict(src) for src in sources], ensure_ascii=False)
        signal_payload = self._tool_json(generate_signal_map(sources_payload, scope_json))
        raw_signals = signal_payload.get("signals", [])
        appendix = signal_payload.get("appendix", [])
        signals, demoted = self._enforce_signal_gates(raw_signals, sources)
        if demoted:
            appendix.extend(demoted)
        self._trace("signal_map:response", signal_payload)
        operator_job_story = self._sanitize_text(signal_payload.get("operator_job_story", ""))
        if operator_job_story:
            scope["operator_job_story"] = operator_job_story
        search_variants_raw = signal_payload.get("search_shaped_variants") or []
        search_variants: List[str] = []
        for variant in search_variants_raw:
            cleaned = self._sanitize_text(variant)
            if cleaned:
                search_variants.append(cleaned)
        if search_variants:
            scope["search_shaped_variants"] = search_variants
        scope_json = json.dumps(scope, ensure_ascii=False)
        support_coverage = self._signal_support_coverage(signals, sources)
        thresholds = source_stats.get("thresholds", {})
        thresholds["support_coverage"] = support_coverage >= STIConfig.SIGNAL_SUPPORT_COVERAGE_MIN
        source_stats["support_coverage"] = round(support_coverage, 3)
        source_stats["thresholds"] = thresholds
        regime = self._evidence_regime(source_stats)
        source_stats["regime"] = regime
        scope["evidence_regime"] = regime
        scope["thin_evidence"] = regime != "healthy"
        source_stats["thin_evidence"] = scope["thin_evidence"]
        if regime == "starved":
            raise RuntimeError("Evidence starved after harvest. Broaden the query or window.")
        evidence_note = self._evidence_note(source_stats)
        scope["evidence_note"] = evidence_note

        quant_payload = self._tool_json(
            generate_quant_blocks(
                sources_payload,
                json.dumps(signals, ensure_ascii=False),
                scope_json,
            )
        )
        quant_payload = normalize_quant_blocks_payload(quant_payload or {})
        quant_errors = lint_quant_blocks(quant_payload or {})
        if quant_errors:
            error_message = "; ".join(quant_errors)
            self._trace("quant_blocks:contract_error", error_message)
            raise ValueError(f"Quant blocks contract failed: {error_message}")

        sections = self._build_sections(
            sources_payload,
            signals,
            signal_payload.get("operator_notes", ""),
            quant_payload,
            scope_json,
        )
        exec_data = self._tool_json(
            write_executive_summary(
                sources_payload,
                json.dumps(sections, ensure_ascii=False),
                json.dumps(signals, ensure_ascii=False),
                json.dumps(quant_payload, ensure_ascii=False),
                scope_json,
            )
        )
        self._trace("executive_summary:response", exec_data)
        image_briefs = self._tool_json(
            generate_image_briefs(
                sources_payload,
                json.dumps(signals, ensure_ascii=False),
                json.dumps(sections, ensure_ascii=False),
                scope_json,
            )
        )
        image_briefs = image_briefs.get("image_briefs") if isinstance(image_briefs, dict) else image_briefs
        self._trace("image_briefs", image_briefs)
        image_prompt_bundle: List[Dict[str, Any]] = []

        top_moves_raw = exec_data.get("top_operator_moves") or self._derive_top_moves(signals)
        top_moves = [self._sanitize_text(move) for move in (top_moves_raw or []) if move]
        top_moves = top_moves[: STIConfig.TOP_OPERATOR_MOVE_COUNT]

        exec_summary = self._sanitize_text(exec_data.get("executive_summary", ""))
        highlights = [self._sanitize_text(text) for text in exec_data.get("highlights", [])]
        hook_line = self._sanitize_text(exec_data.get("hook_line"))
        play_summary = exec_data.get("play_summary") or []
        fast_path = exec_data.get("fast_path") or {
            "sections": ["executive_summary", "highlights", "top_operator_moves", "play_summary"],
        }
        fast_stack = exec_data.get("fast_stack") or {}
        time_window = self._time_window(days_back)
        generated_at = datetime.now()
        title = self._query_title(query)
        deep_sections = (sections.get("deep_analysis", {}) or {}).get("sections", [])
        spine = self._build_spine(signals, quant_payload, deep_sections or [], top_moves)

        spec_bundle = self._build_operator_specs(signals, quant_payload, sections, scope)
        spec_bundle = normalize_operator_specs(spec_bundle or {})
        spec_errors = lint_operator_specs(spec_bundle or {})
        if spec_errors:
            spec_error_msg = "; ".join(spec_errors)
            self._trace("operator_specs:contract_error", spec_error_msg)
            raise ValueError(f"Operator specs contract failed: {spec_error_msg}")
        self._apply_window_label(spec_bundle, scope.get("window_label") or time_window.get("label"))
        spec_bundle["version"] = "v1"
        pilot_spec = spec_bundle.get("pilot_spec") or {}
        metric_spec = spec_bundle.get("metric_spec") or {}
        role_actions = spec_bundle.get("role_actions") or {}
        coherence_issues = spec_bundle.get("coherence_issues") or []
        spec_notes = spec_bundle.get("spec_notes") or []
        spec_ok = spec_bundle.get("spec_ok", True)
        scope["pilot_spec"] = pilot_spec
        scope["metric_spec"] = metric_spec
        scope["role_actions"] = role_actions
        scope["pilot_spec_issues"] = coherence_issues
        scope["spec_version"] = spec_bundle.get("version")
        scope["spec_ok"] = spec_ok
        scope["spec_notes"] = spec_notes

        letter_data = None
        letter_markdown = ""
        letter_bullets = {"investable": [], "targets": []}
        letter_primary_cta = ""
        letter_email_subject = ""
        letter_subtitle = ""
        letter_tldr = ""
        letter_context = self._build_letter_context(
            exec_summary,
            quant_payload,
            sections,
            title,
            scope,
            pilot_spec,
            metric_spec,
            role_actions,
        )
        regime = scope.get("evidence_regime", "healthy")
        letter_status = "generated"
        if regime == "starved":
            self._trace(
                "executive_letter:skipped",
                {"reason": "starved", "source_stats": source_stats},
            )
            letter_status = "skipped_starved"
        elif letter_context:
            try:
                letter_response = self._tool_json(
                    generate_executive_letter(json.dumps(letter_context, ensure_ascii=False))
                )
                if isinstance(letter_response, dict) and self._validate_executive_letter(letter_response):
                    letter_data = letter_response
                    letter_bullets["investable"] = letter_response.get("bullets_investable") or []
                    letter_bullets["targets"] = letter_response.get("bullets_targets") or []
                    letter_primary_cta = letter_response.get("primary_cta") or ""
                    letter_email_subject = letter_response.get("email_subject") or ""
                    letter_subtitle = letter_response.get("subtitle") or ""
                    letter_tldr = letter_response.get("tldr") or ""
                else:
                    self._trace("executive_letter:error", "validation_failed")
            except Exception as exec_letter_error:
                self._trace("executive_letter:error", str(exec_letter_error))
                letter_status = "error"
        else:
            letter_status = "skipped_no_context"
        if letter_data:
            letter_markdown = self._render_executive_letter_markdown(letter_data)

        markdown = self._build_markdown(
            query,
            title,
            exec_summary,
            highlights,
            top_moves,
            play_summary,
            fast_path,
            fast_stack,
            spine,
            signals,
            sections,
            sources,
            quant_payload,
            appendix,
            pilot_spec,
            metric_spec,
            role_actions,
        )
        word_count = len(markdown.split())
        read_time_minutes = max(1, math.ceil(word_count / 200))
        qa_report = self._qa_report(signals, sections, top_moves, scope, quant_payload, appendix, read_time_minutes)
        confidence = self._compute_confidence(signals, qa_report, quant_payload)
        raw_confidence_score = confidence_headline(confidence)
        confidence_score = self._apply_source_caps(raw_confidence_score, source_stats)
        json_ld = self._build_json_ld(query, title, exec_summary, sources, signals, days_back, confidence_score)
        confidence_band, display_score, dials = self._confidence_meta(confidence_score, confidence, qa_report)
        confidence_note_parts: List[str] = []
        if evidence_note:
            confidence_note_parts.append(evidence_note)
        dominant_ratio = source_stats.get("dominant_ratio", 0.0)
        domain_counts = source_stats.get("domain_counts") or {}
        if dominant_ratio > (STIConfig.SOURCE_MAX_DOMAIN_RATIO * 0.9) and domain_counts:
            dominant_domain = max(domain_counts.items(), key=lambda item: item[1])[0]
            confidence_note_parts.append(
                f"Evidence dominated by {dominant_domain} ({dominant_ratio:.0%})."
            )
        if scope.get("thin_evidence"):
            confidence_band = "Directional"
        confidence_note = " ".join(part for part in confidence_note_parts if part).strip()
        report = {
            "query": query,
            "title": title,
            "hook_line": hook_line,
            "time_window": time_window,
            "operator_job_story": scope.get("operator_job_story", ""),
            "search_shaped_variants": scope.get("search_shaped_variants", []),
            "approach_hints": scope.get("approach_hints", []),
            "unified_target_pack": scope.get("unified_target_pack", {}),
            "executive_summary": exec_summary,
            "highlights": highlights,
            "top_operator_moves": top_moves,
            "play_summary": play_summary,
            "signals": signals,
            "appendix_signals": appendix,
            "sources": [asdict(src) for src in sources],
            "source_stats": source_stats,
            "sections": sections,
            "image_briefs": image_briefs,
            "quant": quant_payload,
            "comparison_map": sections.get("comparison_map", {}),
            "executive_letter": letter_data or {},
            "executive_letter_markdown": letter_markdown,
            "letter_status": letter_status,
            "letter_bullets": letter_bullets,
            "letter_primary_cta": letter_primary_cta,
            "letter_email_subject": letter_email_subject,
            "letter_subtitle": letter_subtitle,
            "letter_tldr": letter_tldr,
            "fast_path": fast_path,
            "fast_stack": fast_stack,
            "spine": spine,
            "qa": qa_report,
            "markdown": markdown,
            "json_ld": json_ld,
            "pilot_spec": pilot_spec,
            "metric_spec": metric_spec,
            "role_actions": role_actions,
            "pilot_coherence_issues": coherence_issues,
            "spec_version": spec_bundle.get("version"),
            "spec_notes": spec_notes,
            "spec_ok": spec_ok,
            "confidence": {
                "score": confidence_score,
                "display": display_score,
                "band": confidence_band,
                "dials": dials,
                "breakdown": dataclasses.asdict(confidence),
                "note": confidence_note,
            },
            "read_time_minutes": read_time_minutes,
            "word_count": word_count,
            "region": scope.get("target_region", "US"),
            "thin_evidence": scope.get("thin_evidence", False),
            "evidence_regime": scope.get("evidence_regime", "healthy"),
            "evidence_note": evidence_note,
            "metadata": {
                "agent": "EnhancedSTIAgent",
                "model": self.model_name,
                "generated_at": generated_at.isoformat(),
            },
        }
        try:
            prompt_response = self._tool_json(
                generate_image_prompt_bundle(json.dumps(report, ensure_ascii=False))
            )
            if isinstance(prompt_response, dict):
                image_prompt_bundle = prompt_response.get("images") or []
        except Exception as image_prompt_error:
            logger.debug(f"image_prompt_bundle failed: {image_prompt_error}")
        report["image_prompts"] = image_prompt_bundle
        self._trace("image_prompt_bundle", image_prompt_bundle)
        return report

    # ------------------------------------------------------------------
    # Source collection helpers
    # ------------------------------------------------------------------
    def _build_scope(self, query: str, days_back: int) -> Dict[str, Any]:
        window = self._time_window(days_back)
        window_label = window.get("label") or self._window_label(window)
        if window_label:
            window["label"] = window_label
        scope = {
            "topic": query,
            "time_window": window,
            "target_region": "US",
            "use_cases": ["brand↔brand", "brick&mortar↔brand"],
            "must_answer": [
                "When are the high-value windows",
                "What changes discounting math",
            ],
            "approach_hints": [
                "discount-heavy holiday",
                "collab-led holiday",
                "store-as-studio / media-led holiday",
            ],
            "unified_target_pack": {
                "foot_traffic_uplift": {"base": "10-15%", "stretch": "≥25%"},
                "early_window_share": {"current": "12-15%", "goal": "20-30%"},
                "event_cpa": {"ceiling": "≤0.80× baseline"},
                "qr_redemption": {"floor": "≥5% of footfall"},
                "paired_metric": "Track buyer activity share vs promo intensity side by side",
            },
        }
        if window_label:
            scope["window_label"] = window_label
        scope["topic_kind"] = self._classify_topic_kind(query)
        self._trace("scope", scope)
        return scope

    def _classify_topic_kind(self, query: str) -> str:
        text = (query or "").lower()
        if any(keyword in text for keyword in ["store-as-studio", "store as studio", "flagship", "in-store", "studio", "pop-up", "immersive store"]):
            return "store_as_studio"
        if any(keyword in text for keyword in ["price", "pricing", "margin", "elasticity", "discount", "markdown", "promotion", "cpa", "profit"]):
            return "pricing"
        if any(keyword in text for keyword in ["collab", "co-brand", "partnership", "partner", "joint drop"]):
            return "collaboration"
        return "general"

    def _collect_sources(self, query: str, days_back: int, scope: Dict[str, Any]) -> List[SourceRecord]:
        seen: set[str] = set()
        sources: List[SourceRecord] = []
        category_steps = STIConfig.SEARXNG_CATEGORY_STEPS or [["news"]]
        initial_time_range = self._time_range(days_back)

        topic_kind = scope.get("topic_kind")

        def harvest(range_label: str) -> None:
            window_days = self._window_days_for_range(days_back, range_label)
            for categories in category_steps:
                new_sources = self._harvest_axes(
                    query=query,
                    categories=categories,
                    time_range=range_label,
                    window_days=window_days,
                    scope=scope,
                    seen=seen,
                    requested_days=days_back,
                    topic_kind=topic_kind,
                )
                if new_sources:
                    sources.extend(new_sources)
                if len(sources) >= STIConfig.MAX_SOURCE_COUNT:
                    break
                if len(sources) >= STIConfig.SOURCE_SOFT_FLOOR:
                    break
            return

        harvest(initial_time_range)
        if len(sources) < STIConfig.SOURCE_SOFT_FLOOR:
            expanded_range = self._next_time_range(initial_time_range)
            if expanded_range != initial_time_range:
                harvest(expanded_range)
        if sources:
            preview_stats = self._source_statistics(sources)
            dominant_ratio = preview_stats.get("dominant_ratio", 0.0)
            domain_counts = preview_stats.get("domain_counts", {}) or {}
            core_sources = preview_stats.get("core", 0)
            data_heavy = preview_stats.get("data_heavy", 0)
            need_dominance_relief = (
                dominant_ratio > STIConfig.SOURCE_MAX_DOMAIN_RATIO * 0.85
                and len(sources) < STIConfig.MAX_SOURCE_COUNT
                and domain_counts
            )
            need_anchor_rescue = (
                (core_sources == 0 or data_heavy < max(1, STIConfig.SOURCE_MIN_DATA_HEAVY))
                and len(sources) < STIConfig.MAX_SOURCE_COUNT
            )
            if need_dominance_relief or need_anchor_rescue:
                blocked_domain = None
                if need_dominance_relief:
                    blocked_domain = max(domain_counts.items(), key=lambda item: item[1])[0]
                diversity_sources = self._diversity_pass(
                    query=query,
                    blocked_domain=blocked_domain,
                    seen=seen,
                    scope=scope,
                    requested_days=days_back,
                )
                if diversity_sources:
                    sources.extend(diversity_sources)
        sources = sources[: STIConfig.MAX_SOURCE_COUNT]
        for idx, source in enumerate(sources, start=1):
            source.id = idx
        self._trace(
            "sources:collected",
            {
                "count": len(sources),
                "time_range": initial_time_range,
                "soft_floor": STIConfig.SOURCE_SOFT_FLOOR,
                "max": STIConfig.MAX_SOURCE_COUNT,
                "publishers": list({src.publisher for src in sources}),
                "sample": [asdict(src) for src in sources[:3]],
            },
        )
        return sources

    def _harvest_axes(
        self,
        query: str,
        categories: List[str],
        time_range: str,
        window_days: int,
        scope: Dict[str, Any],
        seen: set[str],
        requested_days: int,
        topic_kind: Optional[str] = None,
    ) -> List[SourceRecord]:
        harvested: List[SourceRecord] = []
        axis_runs: List[str] = []
        axis_counts: List[int] = []
        axis_updates: Dict[str, Dict[str, int]] = {}

        primary_axes, fallback_axes = self._rank_axis_templates(topic_kind)

        def run_axes(axes: List[str]) -> None:
            for template in axes:
                axis_query = self._render_axis_query(template, query)
                axis_runs.append(axis_query)
                raw_results = self._search_searxng(axis_query, time_range, categories)
                new_sources = self._ingest_results(
                    raw_results, window_days, scope, seen, requested_days=requested_days
                )
                new_count = len(new_sources)
                if new_count:
                    harvested.extend(new_sources)
                axis_counts.append(new_count)
                stats = axis_updates.setdefault(template, {"runs": 0, "hits": 0})
                stats["runs"] += 1
                if new_count:
                    stats["hits"] += 1
                if len(harvested) >= STIConfig.MAX_SOURCE_COUNT:
                    break
            return

        run_axes(primary_axes)
        if len(harvested) < STIConfig.SOURCE_SOFT_FLOOR and fallback_axes and len(harvested) < STIConfig.MAX_SOURCE_COUNT:
            run_axes(fallback_axes)

        if axis_runs:
            self._trace(
                "sources:axis_pass",
                {
                    "query": query,
                    "topic_kind": topic_kind,
                    "axis_queries": axis_runs,
                    "axis_counts": axis_counts,
                    "categories": categories,
                    "time_range": time_range,
                    "harvested": len(harvested),
                },
            )
        if axis_updates:
            self._update_axis_health(axis_updates)
        return harvested

    def _diversity_pass(
        self,
        query: str,
        blocked_domain: Optional[str],
        seen: set[str],
        scope: Dict[str, Any],
        requested_days: int,
    ) -> List[SourceRecord]:
        blocked: Set[str] = set()
        if blocked_domain:
            blocked.add(blocked_domain.lower())
        harvested: List[SourceRecord] = []
        probes = STIConfig.DIVERSITY_PROBES or []
        if not probes:
            return harvested
        window_days = self._window_days_for_range(requested_days, self._time_range(requested_days))
        for template in probes:
            axis_query = template.format(query=query)
            raw_results = self._search_searxng(axis_query, self._time_range(requested_days), ["news", "general"])
            new_sources = self._ingest_results(
                raw_results,
                window_days,
                scope,
                seen,
                requested_days=requested_days,
                blocked_domains=blocked,
            )
            if new_sources:
                harvested.extend(new_sources)
            if len(harvested) + len(seen) >= STIConfig.MAX_SOURCE_COUNT:
                break
        if harvested:
            self._trace(
                "sources:diversity_pass",
                {
                    "blocked_domain": blocked_domain,
                    "harvested": len(harvested),
                    "probes": probes[:5],
                },
            )
        return harvested

    def _render_axis_query(self, template: str, query: str) -> str:
        cleaned = (template or "").strip()
        if "{query}" in cleaned:
            try:
                return cleaned.format(query=query)
            except Exception:
                pass
        return f"{query} {cleaned}".strip()

    def _rank_axis_templates(self, topic_kind: Optional[str] = None) -> Tuple[List[str], List[str]]:
        base_axes = STIConfig.SEARCH_QUERY_AXES or ["{query}"]
        kind_axes = STIConfig.SEARCH_QUERY_AXES_BY_KIND.get(topic_kind or "", []) if topic_kind else []
        templates: List[str] = []
        seen: set[str] = set()
        for axis in list(kind_axes) + list(base_axes):
            if axis and axis not in seen:
                templates.append(axis)
                seen.add(axis)
        if not templates:
            templates = ["{query}"]
        health = self._load_axis_health()
        scored: List[Tuple[float, int, str]] = []
        default_ratio = 0.5
        for template in templates:
            stats = health.get(template, {})
            runs = int(stats.get("runs") or 0)
            hits = int(stats.get("hits") or 0)
            ratio = hits / runs if runs else default_ratio
            scored.append((ratio, runs, template))
        scored.sort(key=lambda item: (-item[0], -item[1], item[2]))
        primary: List[str] = []
        fallback: List[str] = []
        for ratio, runs, template in scored:
            if runs >= 5 and ratio < STIConfig.AXIS_HEALTH_LOW_THRESHOLD:
                fallback.append(template)
            else:
                primary.append(template)
        if not primary:
            primary = [tpl for _, _, tpl in scored]
            fallback = []
        return primary or templates, fallback

    def _load_axis_health(self) -> Dict[str, Dict[str, int]]:
        path = Path(STIConfig.AXIS_HEALTH_PATH)
        try:
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            logger.debug("Failed to read axis health file at %s", path)
        return {}

    def _save_axis_health(self, payload: Dict[str, Dict[str, int]]) -> None:
        path = Path(STIConfig.AXIS_HEALTH_PATH)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:
            logger.debug("Failed to write axis health file: %s", exc)

    def _update_axis_health(self, updates: Dict[str, Dict[str, int]]) -> None:
        current = self._load_axis_health()
        current_changed = False
        for template, stats in updates.items():
            entry = current.setdefault(template, {"runs": 0, "hits": 0})
            entry["runs"] = int(entry.get("runs", 0)) + stats.get("runs", 0)
            entry["hits"] = int(entry.get("hits", 0)) + stats.get("hits", 0)
            current_changed = True
        if current_changed:
            self._save_axis_health(current)

    def _ingest_results(
        self,
        raw_results: Optional[List[Dict[str, Any]]],
        window_days: int,
        scope: Dict[str, Any],
        seen: set[str],
        requested_days: int,
        blocked_domains: Optional[Set[str]] = None,
    ) -> List[SourceRecord]:
        harvested: List[SourceRecord] = []
        if not raw_results:
            return harvested
        for result in raw_results:
            url = result.get("url")
            if not url or url in seen:
                continue
            seen.add(url)
            date = self._normalize_date(result.get("published"))
            if not self._within_window(date, window_days):
                continue
            content = result.get("content") or ""
            if len(content) < 400:
                fetched = self._fetch_content(url)
                if fetched:
                    content = fetched
            snippet = (result.get("content") or result.get("title") or "")[:280]
            publisher_raw = result.get("publisher") or self._publisher_from_url(url)
            publisher_normalized = (publisher_raw or "").lower()
            if blocked_domains and publisher_normalized in blocked_domains:
                continue
            credibility = self._score_publisher(url)
            tier = "core" if self._within_window(date, requested_days) else "context"
            source = SourceRecord(
                id=0,
                title=result.get("title") or "Untitled",
                url=url,
                publisher=publisher_raw,
                date=date,
                snippet=snippet,
                content=content[:4000],
                credibility=credibility,
                tier=tier,
            )
            self._annotate_source(source, scope)
            harvested.append(source)
            if len(harvested) >= STIConfig.MAX_SOURCE_COUNT:
                break
        return harvested

    def _window_days_for_range(self, requested_days: int, time_range: str) -> int:
        mapping = {"day": 2, "week": 7, "month": 31, "year": 365}
        target = mapping.get(time_range, requested_days)
        window = max(requested_days, target)
        return min(window, STIConfig.MAX_DAYS_BACK)

    def _next_time_range(self, current: str) -> str:
        order = ["day", "week", "month", "year"]
        if current not in order:
            return current
        idx = order.index(current)
        if idx >= len(order) - 1:
            return current
        return order[idx + 1]

    def _source_statistics(self, sources: List[SourceRecord]) -> Dict[str, Any]:
        domain_counts: Dict[str, int] = {}
        earliest: Optional[datetime] = None
        latest: Optional[datetime] = None
        data_heavy = 0
        core_sources = 0
        tier_counts = {"core": 0, "context": 0}
        for src in sources:
            domain_counts[src.publisher] = domain_counts.get(src.publisher, 0) + 1
            if src.role == "core":
                core_sources += 1
            evidence = src.evidence or {}
            if evidence.get("numeric") or evidence.get("sample_size"):
                data_heavy += 1
            tier_counts[src.tier] = tier_counts.get(src.tier, 0) + 1
            try:
                dt = datetime.strptime(src.date, "%Y-%m-%d")
            except Exception:
                continue
            earliest = dt if earliest is None or dt < earliest else earliest
            latest = dt if latest is None or dt > latest else latest
        total = len(sources)
        support_sources = total - core_sources
        unique_domains = len(domain_counts)
        dominant = max(domain_counts.values()) if domain_counts else 0
        dominant_ratio = (dominant / float(total)) if total else 0.0
        time_span = (latest - earliest).days if earliest and latest else 0
        thresholds = {
            "total": total >= STIConfig.SOURCE_MIN_TOTAL,
            "core": core_sources >= STIConfig.SOURCE_MIN_CORE,
            "domains": unique_domains >= STIConfig.SOURCE_MIN_UNIQUE_DOMAINS,
            "data": data_heavy >= STIConfig.SOURCE_MIN_DATA_HEAVY,
            "dominance": dominant_ratio <= STIConfig.SOURCE_MAX_DOMAIN_RATIO,
            "in_window": tier_counts.get("core", 0) >= STIConfig.SOURCE_MIN_IN_WINDOW,
            "background": tier_counts.get("context", 0) >= STIConfig.SOURCE_MIN_BACKGROUND,
        }
        stats = {
            "total": total,
            "core": core_sources,
            "support": support_sources,
            "unique_domains": unique_domains,
            "domain_counts": domain_counts,
            "data_heavy": data_heavy,
            "time_span_days": time_span,
            "tier_counts": tier_counts,
            "dominant_ratio": round(dominant_ratio, 3),
            "thin_evidence": not all(thresholds.values()),
            "thresholds": thresholds,
        }
        return stats

    def _search_searxng(
        self, query: str, time_range: str, categories: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        base = STIConfig.SEARXNG_BASE_URL.rstrip("/")
        url = f"{base}/search"
        params = {
            "q": query,
            "format": "json",
            "safesearch": 1,
            "time_range": time_range,
        }
        if categories:
            params["categories"] = ",".join(categories)
        self._trace("searxng:request", {"url": url, "params": params})
        try:
            resp = requests.get(url, params=params, timeout=STIConfig.HTTP_TIMEOUT_SECONDS)
            resp.raise_for_status()
            data = resp.json()
            results = (data.get("results", []) or [])[: STIConfig.MAX_RESULTS_PER_QUERY]
            self._trace(
                "searxng:response",
                {
                    "status": resp.status_code,
                    "result_count": len(results),
                    "sample": results[:3],
                },
            )
            if results:
                return results
            if categories:
                fallback_params = dict(params)
                fallback_params.pop("categories", None)
                self._trace("searxng:fallback_request", {"url": url, "params": fallback_params})
                fallback_resp = requests.get(url, params=fallback_params, timeout=STIConfig.HTTP_TIMEOUT_SECONDS)
                fallback_resp.raise_for_status()
                fallback_data = fallback_resp.json()
                fallback_results = (fallback_data.get("results", []) or [])[: STIConfig.MAX_RESULTS_PER_QUERY]
                self._trace(
                    "searxng:fallback_response",
                    {
                        "status": fallback_resp.status_code,
                        "result_count": len(fallback_results),
                        "sample": fallback_results[:3],
                    },
                )
                return fallback_results
            return []
        except Exception as exc:
            logger.error("SearXNG search failed: %s", exc)
            return []

    def _enforce_signal_gates(
        self, signals: List[Dict[str, Any]], sources: List[SourceRecord]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        if not signals:
            return [], []
        keep: List[Dict[str, Any]] = []
        demoted: List[Dict[str, Any]] = []
        source_map = {src.id: src for src in sources}
        for idx, signal in enumerate(signals, start=1):
            normalized = dict(signal)
            support = normalized.get("support") or normalized.get("citations") or []
            normalized["support"] = support
            normalized["citations"] = support
            strength = float(normalized.get("strength") or 0)
            if strength == 0:
                strength = self._infer_strength(support, source_map)
            us_fit = float(normalized.get("US_fit") or normalized.get("us_fit") or 0)
            if us_fit == 0:
                us_fit = self._infer_us_fit(support, source_map)
            operationality = float(normalized.get("operationality") or 0.7)
            on_spine = normalized.get("on_spine")
            if on_spine is None:
                on_spine = True
            support_records = [source_map.get(cid) for cid in support if source_map.get(cid)]
            quant_support = normalized.get("quant_support") or "light"
            source_grade = normalized.get("source_grade") or self._signal_source_grade(support, source_map)
            normalized["id"] = normalized.get("id") or f"S{idx}"
            normalized["strength"] = round(min(1.0, strength), 2)
            normalized["US_fit"] = round(min(1.0, us_fit), 2)
            normalized["operationality"] = round(min(1.0, operationality), 2)
            normalized.setdefault("name", normalized.get("title") or normalized.get("text", "Untitled signal"))
            normalized.setdefault("description", normalized.get("description") or normalized.get("text", ""))
            normalized.setdefault("category", normalized.get("category", "Market"))
            normalized["on_spine"] = bool(on_spine)
            normalized["quant_support"] = quant_support
            normalized["source_grade"] = source_grade
            if len(support_records) < STIConfig.SIGNAL_MIN_SUPPORT or (
                STIConfig.SIGNAL_REQUIRE_CORE_SUPPORT and not any(src and src.role == "core" for src in support_records)
            ):
                normalized.setdefault("bucket", "appendix")
                normalized.setdefault("demotion_reason", "insufficient_support")
                demoted.append(normalized)
                continue
            if (
                normalized["strength"] < max(STIConfig.SIGNAL_MIN_STRENGTH, 0.78)
                or normalized["US_fit"] < STIConfig.SIGNAL_MIN_US_FIT
                or not normalized["on_spine"]
                or GRADE_ORDER.get(source_grade, 2) > 1
            ):
                normalized.setdefault("bucket", "appendix")
                demoted.append(normalized)
                continue
            keep.append(normalized)
        max_signals = min(STIConfig.SIGNAL_TARGET_COUNT, STIConfig.SIGNAL_MAX_COUNT)
        if len(keep) > max_signals:
            extra = keep[max_signals:]
            keep = keep[:max_signals]
            for signal in extra:
                signal.setdefault("bucket", "appendix")
                demoted.append(signal)
        keep, quality_demoted = self._enforce_top_signal_quality(keep, source_map)
        if quality_demoted:
            demoted.extend(quality_demoted)
        return keep, demoted

    def _enforce_top_signal_quality(
        self, signals: List[Dict[str, Any]], source_map: Dict[int, SourceRecord]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        if not signals:
            return signals, []
        unique_domains = {
            (src.publisher or "").lower()
            for src in source_map.values()
            if getattr(src, "publisher", None)
        }
        demoted: List[Dict[str, Any]] = []
        if not unique_domains:
            return signals, demoted
        to_remove: set[Any] = set()
        ordered = sorted(signals, key=lambda sig: sig.get("strength", 0), reverse=True)
        check_count = min(len(ordered), STIConfig.TOP_SIGNAL_DOMAIN_CHECK_COUNT)
        for signal in ordered[:check_count]:
            support_ids = signal.get("support") or []
            support_sources = [source_map.get(cid) for cid in support_ids if source_map.get(cid)]
            support_domains = {
                (src.publisher or "").lower() for src in support_sources if getattr(src, "publisher", None)
            }
            has_quant = any((src.evidence or {}).get("numeric") or (src.evidence or {}).get("sample_size") for src in support_sources if src)
            demotion_reason = ""
            if len(unique_domains) > 1 and len(support_domains) <= 1:
                demotion_reason = "single_domain_support"
            elif STIConfig.SIGNAL_REQUIRE_DATA_HEAVY_TOP and not has_quant:
                demotion_reason = "no_quantitative_support"
            if demotion_reason:
                copy = dict(signal)
                copy.setdefault("bucket", "appendix")
                copy["demotion_reason"] = demotion_reason
                demoted.append(copy)
                to_remove.add(signal.get("id"))
        if not to_remove:
            return signals, demoted
        filtered = [sig for sig in signals if sig.get("id") not in to_remove]
        return filtered, demoted

    def _infer_strength(self, support: List[int], source_map: Dict[int, SourceRecord]) -> float:
        if not support:
            return 0.6
        scores = [source_map.get(cid).quality for cid in support if cid in source_map]
        if not scores:
            return 0.62
        return sum(scores) / len(scores)

    def _infer_us_fit(self, support: List[int], source_map: Dict[int, SourceRecord]) -> float:
        if not support:
            return 0.6
        scores = [source_map.get(cid).us_fit for cid in support if cid in source_map]
        if not scores:
            return 0.7
        return sum(scores) / len(scores)

    def _signal_source_grade(self, support: List[int], source_map: Dict[int, SourceRecord]) -> str:
        if not support:
            return STIConfig.SOURCE_GRADE_FALLBACK
        best_grade = "D"
        for cid in support:
            src = source_map.get(cid)
            if not src:
                continue
            grade = src.source_grade
            if GRADE_ORDER.get(grade, 3) < GRADE_ORDER.get(best_grade, 3):
                best_grade = grade
                if best_grade == "A":
                    break
        return best_grade

    def _time_range(self, days: int) -> str:
        if days <= 2:
            return "day"
        if days <= 7:
            return "week"
        if days <= 31:
            return "month"
        return "year"

    def _derive_top_moves(self, signals: List[Dict[str, Any]]) -> List[str]:
        ordered = sorted(signals, key=lambda sig: sig.get("strength", 0), reverse=True)
        moves = [sig.get("operator_move", "").strip() for sig in ordered if sig.get("operator_move")]
        filtered = [move for move in moves if move]
        if len(filtered) >= STIConfig.TOP_OPERATOR_MOVE_COUNT:
            return filtered[: STIConfig.TOP_OPERATOR_MOVE_COUNT]
        return filtered

    def _normalize_activation_play(self, play: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(play or {})
        display = payload.get("display") or {}
        ops = payload.get("ops") or {}
        if not display:
            display = {
                "pillar": payload.get("pillar"),
                "play_name": payload.get("play_name"),
                "card_title": payload.get("play_name"),
                "persona": payload.get("persona"),
                "best_fit": payload.get("best_fit"),
                "not_for": payload.get("not_for"),
                "thresholds_summary": payload.get("thresholds"),
                "why_now": payload.get("why_now") or payload.get("proof_point"),
                "proof_point": payload.get("proof_point"),
                "time_horizon": payload.get("timing"),
                "placement_options": payload.get("placement_options") or [],
            }
        if not ops:
            thresholds = payload.get("thresholds")
            ops = {
                "operator_owner": payload.get("operator_owner"),
                "collaborator": payload.get("collaborator"),
                "collab_type": payload.get("collab_type"),
                "thresholds": {"summary": thresholds} if isinstance(thresholds, str) else thresholds,
                "prerequisites": payload.get("prerequisites") or [],
                "target_map": payload.get("target_map") or [],
                "cadence": payload.get("cadence") or [],
                "zero_new_sku": payload.get("zero_new_sku"),
                "ops_drag": payload.get("ops_drag"),
            }
        display.setdefault("play_name", display.get("card_title"))
        display.setdefault("card_title", display.get("play_name"))
        display.setdefault("thresholds_summary", ops.get("thresholds", {}).get("summary") if isinstance(ops.get("thresholds"), dict) else ops.get("thresholds"))
        display.setdefault("placement_options", ops.get("placement_options") or [])
        ops.setdefault("cadence", [])
        ops.setdefault("target_map", [])
        ops.setdefault("prerequisites", [])
        normalized = {
            **payload,
            "display": display,
            "ops": ops,
            "play_name": display.get("play_name") or payload.get("play_name") or "Activation play",
            "pillar": display.get("pillar") or payload.get("pillar"),
        }
        legacy_fields = {
            "operator_owner",
            "collaborator",
            "collab_type",
            "proof_point",
            "timing",
            "thresholds",
            "persona",
            "target_map",
            "cadence",
            "prerequisites",
            "placement_options",
            "why_now",
            "best_fit",
            "not_for",
            "zero_new_sku",
            "ops_drag",
        }
        for field in legacy_fields:
            normalized.pop(field, None)
        return normalized

    def _activation_label(self, play: Dict[str, Any]) -> str:
        display = play.get("display") or {}
        return (
            (display.get("card_title") or display.get("play_name") or play.get("play_name") or "activation")
            .strip()
        )

    def _merge_display_blocks(self, base: Dict[str, Any], incoming: Dict[str, Any]) -> None:
        if not incoming:
            return
        for key in ["thresholds_summary", "proof_point", "why_now"]:
            if incoming.get(key) and incoming.get(key) not in (base.get(key) or ""):
                if base.get(key):
                    base[key] = " | ".join(filter(None, [base.get(key), incoming.get(key)]))
                else:
                    base[key] = incoming.get(key)
        if incoming.get("placement_options"):
            seen = set(opt.lower() for opt in base.get("placement_options", []))
            options = base.get("placement_options", [])
            for opt in incoming.get("placement_options", []):
                normalized = (opt or "").strip()
                if normalized and normalized.lower() not in seen:
                    options.append(normalized)
                    seen.add(normalized.lower())
            base["placement_options"] = options

    def _merge_ops_blocks(self, base: Dict[str, Any], incoming: Dict[str, Any]) -> None:
        if not incoming:
            return
        for key in ["target_map", "prerequisites"]:
            existing = base.get(key) or []
            incoming_items = incoming.get(key) or []
            base[key] = existing + incoming_items
        if incoming.get("cadence"):
            base.setdefault("cadence", [])
            base["cadence"].extend(incoming.get("cadence", []))
        if incoming.get("thresholds"):
            base_thresholds = base.get("thresholds") or {}
            incoming_thresholds = incoming.get("thresholds")
            if isinstance(base_thresholds, dict) and isinstance(incoming_thresholds, dict):
                base_thresholds.update({k: v for k, v in incoming_thresholds.items() if v})
                base["thresholds"] = base_thresholds

    def _sort_spine_sections(self, sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        def sort_key(section: Dict[str, Any]) -> Tuple[int, int, str]:
            order = {"what": 0, "so_what": 1, "now_what": 2}
            position = order.get(section.get("spine_position"), 3)
            priority = int(section.get("priority") or 3)
            return (position, priority, section.get("title", ""))

        return sorted(sections or [], key=sort_key)

    def _build_spine(
        self,
        signals: List[Dict[str, Any]],
        quant_payload: Dict[str, Any],
        deep_sections: List[Dict[str, Any]],
        top_moves: List[str],
    ) -> Dict[str, str]:
        what = next(
            (sec.get("scan_line") for sec in deep_sections if sec.get("spine_position") == "what"),
            None,
        )
        if not what and signals:
            what = signals[0].get("spine_hook") or signals[0].get("name")
        so_what = quant_payload.get("spine_hook") or next(
            (sec.get("scan_line") for sec in deep_sections if sec.get("spine_position") == "so_what"),
            None,
        )
        now_what = next(
            (sec.get("scan_line") for sec in deep_sections if sec.get("spine_position") == "now_what"),
            None,
        )
        if not now_what and top_moves:
            now_what = top_moves[0]
        return {
            "what": (what or "Signals compress the holiday window").strip(),
            "so_what": (so_what or "Success = guardrailed measurement").strip(),
            "now_what": (now_what or "Run the two-arm pilot now").strip(),
        }

    def _merge_activation_plays(self, plays: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized = [self._normalize_activation_play(play) for play in plays or []]
        merged: Dict[str, Dict[str, Any]] = {}
        for play in normalized:
            name = self._activation_label(play)
            key = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "activation"
            if key not in merged:
                merged[key] = play
                continue
            existing = merged[key]
            self._merge_display_blocks(existing.get("display", {}), play.get("display", {}))
            self._merge_ops_blocks(existing.get("ops", {}), play.get("ops", {}))
        limited = self._constrain_activation_plays(list(merged.values()))
        return self._ensure_activation_ctas(limited)

    def _constrain_activation_plays(self, plays: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Limit activation cards to MAX_ACTIVATION_PLAYS and roll extras into overflow notes."""
        if not plays:
            return []
        max_count = max(1, STIConfig.MAX_ACTIVATION_PLAYS)
        if len(plays) <= max_count:
            return plays
        keep = plays[:max_count]
        overflow = plays[max_count:]
        overflow_notes: List[str] = []
        for extra in overflow:
            display = extra.get("display", {})
            name = self._activation_label(extra)
            proof = display.get("proof_point") or ""
            timing = display.get("time_horizon") or ""
            synopsis = " | ".join(filter(None, [name, proof, timing]))
            overflow_notes.append(synopsis)
        keep[-1]["overflow_notes"] = overflow_notes
        return keep

    def _ensure_activation_ctas(self, plays: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        defaults = [
            "Send 1-page runbook to merchandising, store ops, and finance",
            "Book 30-minute readout with finance and ops to review guardrails",
            "Deliver scale/kill decision memo to executive sponsor",
        ]
        fallback_index = 0
        for play in plays or []:
            ops = play.get("ops") or {}
            cadence = ops.get("cadence") or []
            if not cadence:
                cadence = [{
                    "day": 0,
                    "subject": "Kickoff",
                    "narrative": "Share instrumentation plan",
                    "cta": defaults[fallback_index % len(defaults)],
                }]
                fallback_index += 1
            else:
                for step in cadence:
                    cta = (step.get("cta") or "").strip()
                    if not cta or "specify cta" in cta.lower():
                        step["cta"] = defaults[fallback_index % len(defaults)]
                        fallback_index += 1
            ops["cadence"] = cadence
            play["ops"] = ops
        return plays

    def _confidence_meta(
        self, score: float, breakdown: ConfidenceBreakdown, qa_report: Dict[str, Any]
    ) -> Tuple[str, float, Dict[str, str]]:
        band = "low"
        if score >= 0.75:
            band = "high"
        elif score >= 0.6:
            band = "medium"
        display = min(0.9, round(score, 2))

        def dial(value: float) -> str:
            if value >= 0.75:
                return "high"
            if value >= 0.55:
                return "medium"
            return "light"

        dials = {
            "strength": dial(breakdown.average_strength),
            "coverage": dial(breakdown.coverage),
            "quant_support": dial(breakdown.quant_support),
            "consistency": dial(breakdown.contradiction_penalty),
        }
        if band == "high":
            if (
                not qa_report.get("high_quality_signals")
                or qa_report.get("issues")
                or not qa_report.get("observed_quant")
                or not qa_report.get("tier1_market_signals")
            ):
                band = "medium"
        if band == "medium" and qa_report.get("issues") and breakdown.quant_support < 0.5:
            band = "low"
        band_label = band.title()
        return band_label, display, dials

    def _sanitize_text(self, text: Any) -> str:
        if text is None:
            return ""
        if isinstance(text, list):
            text = " ".join(
                str(part).strip()
                for part in text
                if part is not None and str(part).strip()
            )
        elif not isinstance(text, str):
            text = str(text)
        if not text:
            return ""
        cleaned = re.sub(r"\s+", " ", text).strip()
        if not cleaned:
            return ""
        tokens = cleaned.split(" ")
        months = {"jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec"}
        deduped: List[str] = []
        for token in tokens:
            token_clean = token.strip()
            if not token_clean:
                continue
            if deduped:
                prev = deduped[-1]
                if (
                    token_clean == prev
                    and (token_clean.isdigit() or token_clean.lower() in months)
                ):
                    continue
            deduped.append(token_clean)
        return " ".join(deduped)

    def _strip_headings(self, text: str) -> str:
        if not text:
            return ""
        lines: List[str] = []
        for raw_line in text.splitlines():
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            lines.append(stripped)
        flattened = "\n".join(lines).strip()
        return self._strip_internal_scaffolding(flattened)

    def _strip_internal_scaffolding(self, text: str) -> str:
        if not text:
            return ""
        cleaned = text
        cleaned = re.sub(r"\s*->\s*(tracks?|mandate)[^\n]*", " ", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s{2,}", " ", cleaned)
        return cleaned.strip()

    def _build_operator_specs(
        self,
        signals: List[Dict[str, Any]],
        quant_payload: Dict[str, Any],
        sections: Dict[str, Any],
        scope: Dict[str, Any],
    ) -> Dict[str, Any]:
        spec_payload: Dict[str, Any] = {}
        try:
            spec_payload = self._tool_json(
                generate_operator_specs(
                    json.dumps(signals, ensure_ascii=False),
                    json.dumps(quant_payload, ensure_ascii=False),
                    json.dumps(scope or {}, ensure_ascii=False),
                    json.dumps(sections or {}, ensure_ascii=False),
                )
            )
        except Exception as spec_error:
            self._trace("operator_specs:error", str(spec_error))
            spec_payload = {}
        metric_spec = self._normalize_metric_spec(
            spec_payload.get("metric_spec") or self._fallback_metric_spec(quant_payload, scope)
        )
        pilot_spec = self._normalize_pilot_spec(
            spec_payload.get("pilot_spec") or self._fallback_pilot_spec(scope, metric_spec),
            scope,
            metric_spec,
        )
        key_metrics = [metric for metric in pilot_spec.get("key_metrics", []) if metric in metric_spec]
        if not key_metrics:
            key_metrics = list(metric_spec.keys())[:3]
        pilot_spec["key_metrics"] = key_metrics
        role_actions = self._normalize_role_actions(
            spec_payload.get("role_actions") or self._fallback_role_actions(pilot_spec, metric_spec),
            pilot_spec,
            metric_spec,
        )
        coherence = self._pilot_spec_coherence(pilot_spec, metric_spec, role_actions)
        coherence.extend(self._instrument_metric_issues(sections, metric_spec))
        if not pilot_spec and not metric_spec:
            coherence.append("no_valid_spec")
        filtered = [issue for issue in coherence if issue and issue != "no_valid_spec"]
        serious_tokens = ("store_count", "duration_weeks", "key_metric", "role_action")
        spec_notes = [issue for issue in filtered if issue.startswith(serious_tokens)]
        return {
            "pilot_spec": pilot_spec,
            "metric_spec": metric_spec,
            "role_actions": role_actions,
            "coherence_issues": coherence,
            "spec_notes": spec_notes,
            "spec_ok": not spec_notes,
        }

    def _normalize_metric_spec(self, metric_spec_raw: Any) -> Dict[str, Dict[str, Any]]:
        normalized: Dict[str, Dict[str, Any]] = {}
        if isinstance(metric_spec_raw, dict):
            items = metric_spec_raw.items()
        elif isinstance(metric_spec_raw, list):
            items = enumerate(metric_spec_raw)
        else:
            items = []
        for key, entry in items:
            if not isinstance(entry, dict):
                continue
            metric_id = self._metric_slug(str(key)) if key is not None else ""
            label = self._sanitize_text(entry.get("label") or entry.get("name") or str(key) or "Metric")
            unit = self._sanitize_text(entry.get("unit") or entry.get("units") or "")
            target_range = self._parse_target_range(entry.get("target_range"), entry)
            target_text = self._sanitize_text(
                entry.get("target_text")
                or entry.get("expression")
                or entry.get("value")
                or entry.get("notes")
                or ""
            )
            stage = self._sanitize_text(entry.get("stage") or entry.get("status") or "target").lower() or "target"
            owner = self._sanitize_text(entry.get("owner") or entry.get("team") or "")
            notes = self._sanitize_text(entry.get("notes") or entry.get("why") or "")
            normalized_id = metric_id or self._metric_slug(label)
            if target_text:
                formatted_text = target_text
            else:
                formatted_text = self._format_metric_target(target_range, unit)
            normalized[normalized_id] = {
                "label": label or friendly_metric_label(normalized_id),
                "target_range": target_range,
                "unit": unit,
                "stage": stage or "target",
                "owner": owner,
                "target_text": formatted_text,
                "notes": notes,
            }
        return normalized

    def _parse_target_range(self, range_value: Any, entry: Dict[str, Any]) -> List[float]:
        numeric = self._coerce_numeric_range(range_value)
        if numeric:
            return numeric
        fallback_fields = [
            entry.get("target_text"),
            entry.get("expression"),
            entry.get("value"),
            entry.get("notes"),
        ]
        for field in fallback_fields:
            numeric = self._coerce_numeric_range(field)
            if numeric:
                return numeric
            numeric = self._numeric_range_from_text(field)
            if numeric:
                return numeric
        return []

    def _coerce_numeric_range(self, value: Any) -> List[float]:
        if isinstance(value, (list, tuple)) and len(value) == 2:
            low = self._coerce_numeric_value(value[0])
            high = self._coerce_numeric_value(value[1])
            if low is not None and high is not None:
                return [low, high]
            if low is not None:
                return [low, low]
            if high is not None:
                return [high, high]
            return []
        if isinstance(value, dict):
            low = self._coerce_numeric_value(value.get("low"))
            high = self._coerce_numeric_value(value.get("high"))
            if low is not None and high is not None:
                return [low, high]
            if low is not None:
                return [low, low]
            if high is not None:
                return [high, high]
            return []
        if isinstance(value, (int, float)):
            num = float(value)
            return [num, num]
        if isinstance(value, str):
            return self._numeric_range_from_text(value)
        return []

    def _numeric_range_from_text(self, text: Any) -> List[float]:
        if not isinstance(text, str):
            return []
        cleaned = text.replace(",", "").replace("–", "-")
        matches = re.findall(r"-?\d+(?:\.\d+)?", cleaned)
        nums: List[float] = []
        for token in matches[:2]:
            try:
                nums.append(float(token))
            except ValueError:
                continue
        if len(nums) == 2:
            return nums
        if len(nums) == 1:
            return [nums[0], nums[0]]
        return []

    def _coerce_numeric_value(self, value: Any) -> Optional[float]:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            cleaned = value.replace(",", "")
            cleaned = cleaned.replace("–", "-")
            match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
            if match:
                try:
                    return float(match.group())
                except ValueError:
                    return None
        return None

    def _format_metric_target(self, target_range: List[Any], unit: str) -> str:
        if not target_range:
            return ""
        low = self._format_range_number(target_range[0])
        high = self._format_range_number(target_range[1])
        if low and high:
            if low == high:
                value_text = low
            else:
                value_text = f"{low}–{high}"
        else:
            value_text = ""
        unit_text = f" {unit.strip()}" if unit else ""
        return f"{value_text}{unit_text}".strip()

    def _format_range_number(self, value: Any) -> str:
        if value is None:
            return ""
        try:
            number = float(value)
        except (TypeError, ValueError):
            return ""
        if number.is_integer():
            return str(int(number))
        return f"{number:.2f}".rstrip("0").rstrip(".")

    def _fallback_metric_spec(self, quant_payload: Dict[str, Any], scope: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        spec: Dict[str, Dict[str, Any]] = {}
        anchors = quant_payload.get("anchors") or []
        for idx, anchor in enumerate(anchors):
            label = anchor.get("headline") or anchor.get("label") or anchor.get("metric") or f"Metric {idx + 1}"
            metric_id = self._metric_slug(anchor.get("metric") or label or f"metric_{idx + 1}")
            unit = self._sanitize_text(anchor.get("unit") or "")
            low = anchor.get("value_low")
            high = anchor.get("value_high")
            target_range: List[Any] = []
            if isinstance(low, (int, float)) and isinstance(high, (int, float)):
                target_range = [float(low), float(high)]
            elif isinstance(low, (int, float)):
                target_range = [float(low), float(low)]
            elif isinstance(high, (int, float)):
                target_range = [float(high), float(high)]
            target_text = self._sanitize_text(anchor.get("expression") or anchor.get("value") or "")
            stage = anchor_stage(label).lower()
            owner = self._sanitize_text(anchor.get("owner") or "")
            spec[metric_id] = {
                "label": friendly_metric_label(label),
                "target_range": target_range,
                "unit": unit,
                "stage": stage or "target",
                "owner": owner,
                "target_text": target_text or self._format_metric_target(target_range, unit),
                "notes": self._sanitize_text(anchor.get("band") or "anchor"),
            }
        if spec:
            return spec
        pack = scope.get("unified_target_pack") or {}
        for metric_id, target in pack.items():
            label = friendly_metric_label(metric_id)
            text = ""
            if isinstance(target, dict):
                text = target.get("goal") or target.get("base") or target.get("stretch") or ""
            else:
                text = str(target)
            slug = self._metric_slug(metric_id)
            spec[slug] = {
                "label": label,
                "target_range": [],
                "unit": "",
                "stage": "target",
                "owner": "Owner TBD",
                "target_text": self._sanitize_text(text) or "Target TBD",
                "notes": "unified_target_pack",
            }
        return spec

    def _metric_slug(self, text: str, fallback: str = "metric") -> str:
        cleaned = self._sanitize_text(text)
        if not cleaned:
            return fallback
        slug = re.sub(r"[^a-z0-9]+", "_", cleaned.lower()).strip("_")
        return slug or fallback

    def _normalize_pilot_spec(
        self,
        pilot_spec_raw: Any,
        scope: Dict[str, Any],
        metric_spec: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        if not isinstance(pilot_spec_raw, dict):
            pilot_spec_raw = {}
        scenario = self._metric_slug(pilot_spec_raw.get("scenario") or scope.get("topic_kind") or "pilot", "pilot")
        store_count = pilot_spec_raw.get("store_count") or 1
        try:
            store_count = max(1, int(store_count))
        except (TypeError, ValueError):
            store_count = 1
        store_type = self._sanitize_text(pilot_spec_raw.get("store_type") or "flagship")
        duration_weeks = pilot_spec_raw.get("duration_weeks") or 4
        try:
            duration_weeks = max(1, int(duration_weeks))
        except (TypeError, ValueError):
            duration_weeks = 4
        window = self._sanitize_text(pilot_spec_raw.get("window")) or self._scope_window_label(scope)
        primary_move = self._sanitize_text(pilot_spec_raw.get("primary_move") or scope.get("operator_job_story") or "Run the pilot")
        owner_roles = [self._sanitize_text(role) for role in pilot_spec_raw.get("owner_roles", []) if self._sanitize_text(role)]
        if not owner_roles:
            owner_roles = ["Head of Retail", "Head of Partnerships", "Head of Marketing", "Finance"]
        if "Finance" not in owner_roles:
            owner_roles.append("Finance")
        location_radius = pilot_spec_raw.get("location_radius_miles") or 5
        try:
            location_radius = max(0, int(location_radius))
        except (TypeError, ValueError):
            location_radius = 5
        key_metrics = [metric for metric in (pilot_spec_raw.get("key_metrics") or []) if metric in metric_spec]
        if not key_metrics:
            key_metrics = list(metric_spec.keys())[:3]
        return {
            "scenario": scenario,
            "store_count": store_count,
            "store_type": store_type or "flagship",
            "duration_weeks": duration_weeks,
            "window": window,
            "primary_move": primary_move,
            "owner_roles": owner_roles,
            "location_radius_miles": location_radius,
            "key_metrics": key_metrics,
        }

    def _scope_window_label(self, scope: Dict[str, Any]) -> str:
        window = scope.get("time_window") or {}
        start = window.get("start")
        end = window.get("end")
        if start and end:
            return f"{start} → {end}"
        if start or end:
            return start or end
        return "Pilot window"

    def _fallback_pilot_spec(
        self,
        scope: Dict[str, Any],
        metric_spec: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        topic_kind = scope.get("topic_kind", "pilot")
        store_type = "flagship" if "store" in topic_kind else "multi-market"
        store_count = 1 if store_type == "flagship" else 3
        duration = 4
        primary_move = scope.get("operator_job_story") or "Run a measured pilot"
        return {
            "scenario": f"{topic_kind}_pilot",
            "store_count": store_count,
            "store_type": store_type,
            "duration_weeks": duration,
            "window": self._scope_window_label(scope),
            "primary_move": self._sanitize_text(primary_move),
            "owner_roles": ["Head of Retail", "Head of Partnerships", "Head of Marketing", "Finance"],
            "location_radius_miles": 5,
            "key_metrics": list(metric_spec.keys())[:3],
        }

    def _normalize_role_actions(
        self,
        role_actions_raw: Any,
        pilot_spec: Dict[str, Any],
        metric_spec: Dict[str, Dict[str, Any]],
    ) -> Dict[str, str]:
        normalized: Dict[str, str] = {}
        if isinstance(role_actions_raw, dict):
            for role, action in role_actions_raw.items():
                clean_role = self._sanitize_text(role)
                clean_action = self._sanitize_text(action)
                if clean_role and clean_action:
                    normalized[clean_role] = clean_action
        fallback_actions = self._fallback_role_actions(pilot_spec, metric_spec)
        for role, action in fallback_actions.items():
            if role not in normalized and action:
                normalized[role] = action
        return normalized

    def _fallback_role_actions(
        self,
        pilot_spec: Dict[str, Any],
        metric_spec: Dict[str, Dict[str, Any]],
    ) -> Dict[str, str]:
        duration = pilot_spec.get("duration_weeks", 4)
        store_type = pilot_spec.get("store_type", "flagship")
        store_count = pilot_spec.get("store_count", 1)
        move = pilot_spec.get("primary_move", "run the pilot")
        radius = pilot_spec.get("location_radius_miles") or 0
        key_metrics = pilot_spec.get("key_metrics") or list(metric_spec.keys())
        metric_lines = [self._metric_guardrail_line(metric_id, metric_spec) for metric_id in key_metrics]
        metric_lines = [line for line in metric_lines if line][:2]
        finance_line = "; ".join(metric_lines)
        if radius:
            radius_text = f"within {radius} miles"
        else:
            radius_text = "inside the flagship trade area"
        actions = {
            "Head of Retail": f"Stand up the {duration}-week {store_type} pilot across {store_count} site(s) and keep daily reads on the guardrails.",
            "Head of Partnerships": f"Lock the partner/creator roster {radius_text} and script {move} so every visit flows through one owned channel.",
            "Finance": f"Guardrail {finance_line or 'margin per buyer vs baseline'} before scaling.".strip(),
        }
        if not finance_line:
            actions["Finance"] = "Guardrail margin per buyer and event CPA before scaling."
        return actions

    def _metric_guardrail_line(self, metric_id: str, metric_spec: Dict[str, Dict[str, Any]]) -> str:
        entry = metric_spec.get(metric_id)
        if not entry:
            return ""
        label = entry.get("label") or friendly_metric_label(metric_id)
        target = entry.get("target_text") or self._format_metric_target(entry.get("target_range") or [], entry.get("unit") or "")
        owner = entry.get("owner")
        if owner:
            return f"{label} at {target} ({owner})".strip()
        return f"{label} at {target}".strip()

    def _pilot_spec_coherence(
        self,
        pilot_spec: Dict[str, Any],
        metric_spec: Dict[str, Dict[str, Any]],
        role_actions: Dict[str, str],
    ) -> List[str]:
        issues: List[str] = []
        if pilot_spec.get("store_count", 0) < 1:
            issues.append("store_count must be >= 1")
        if pilot_spec.get("duration_weeks", 0) < 1:
            issues.append("duration_weeks must be >= 1")
        metric_keys = set(metric_spec.keys())
        for metric in pilot_spec.get("key_metrics", []):
            if metric not in metric_keys:
                issues.append(f"key_metric {metric} missing from metric_spec")
        owner_roles = set(pilot_spec.get("owner_roles", []))
        owner_roles.add("Finance")
        for role in role_actions.keys():
            if role not in owner_roles:
                issues.append(f"role_action {role} missing from owner_roles")
        return issues

    def _instrument_metric_issues(
        self,
        sections: Dict[str, Any],
        metric_spec: Dict[str, Dict[str, Any]],
    ) -> List[str]:
        if not sections:
            return []
        issues: List[str] = []
        valid_metrics = set(metric_spec.keys())
        known = known_metric_ids()
        pattern = re.compile(r"\b([a-z][a-z0-9_]+)\b")
        deep_sections = (sections.get("deep_analysis") or {}).get("sections") or []
        for block in deep_sections:
            raw = block.get("instrument_next") or ""
            if not raw:
                continue
            for match in pattern.findall(str(raw)):
                token = match.lower()
                if "_" not in token:
                    continue
                if token in valid_metrics:
                    continue
                if token in known:
                    issues.append(f"instrument_metric {token} missing from metric_spec")
                    break
        return issues

    def _metric_targets_from_spec(self, metric_spec: Dict[str, Dict[str, Any]]) -> List[str]:
        targets: List[str] = []
        for entry in metric_spec.values():
            label = entry.get("label") or "Metric"
            target_text = entry.get("target_text") or self._format_metric_target(entry.get("target_range") or [], entry.get("unit") or "")
            details: List[str] = []
            stage = self._sanitize_text(entry.get("stage") or "")
            owner = self._sanitize_text(entry.get("owner") or "")
            if stage:
                details.append(stage)
            if owner:
                details.append(owner)
            detail_text = f" ({', '.join(details)})" if details else ""
            line = f"{label}: {target_text or 'Target TBD'}{detail_text}"
            targets.append(line.strip())
            if len(targets) >= 6:
                break
        return targets

    def _render_executive_letter_markdown(self, letter: Dict[str, Any]) -> str:
        """Render the executive letter JSON into markdown for Market-Path outputs."""
        if not letter:
            return ""

        lines: List[str] = []
        title = self._sanitize_text(letter.get("title") or "")
        subtitle = self._sanitize_text(letter.get("subtitle") or "")
        tldr = self._sanitize_text(letter.get("tldr") or "")

        if title:
            lines.append(f"# {title}")
        if subtitle:
            lines.append(f"_{subtitle}_")
            lines.append("")
        if tldr:
            lines.append(f"> {tldr}")
            lines.append("")

        for section in letter.get("sections") or []:
            name = self._sanitize_text(section.get("name") or "")
            body = self._sanitize_text(section.get("body") or "")
            if not body:
                continue
            if name:
                lines.append(f"## {name}")
            lines.append(body)
            lines.append("")

        bullets_investable = letter.get("bullets_investable") or []
        if bullets_investable:
            lines.append("### Why this window matters")
            for item in bullets_investable:
                clean_item = self._sanitize_text(item)
                if clean_item:
                    lines.append(f"- {clean_item}")
            lines.append("")

        bullets_targets = letter.get("bullets_targets") or []
        if bullets_targets:
            lines.append("### Targets for this pilot")
            for item in bullets_targets:
                clean_item = self._sanitize_text(item)
                if clean_item:
                    lines.append(f"- {clean_item}")
            lines.append("")

        primary_cta = self._sanitize_text(letter.get("primary_cta") or "")
        if primary_cta:
            lines.append("### Decision requested")
            lines.append(primary_cta)
            lines.append("")

        email_subject = self._sanitize_text(letter.get("email_subject") or "")
        if email_subject:
            lines.append(f"_Forward with subject: {email_subject}_")
            lines.append("")

        return "\n".join(lines).strip()

    def _build_letter_context(
        self,
        exec_summary: str,
        quant_payload: Dict[str, Any],
        sections: Dict[str, Any],
        title: str,
        scope: Optional[Dict[str, Any]] = None,
        pilot_spec: Optional[Dict[str, Any]] = None,
        metric_spec: Optional[Dict[str, Any]] = None,
        role_actions: Optional[Dict[str, str]] = None,
    ) -> Optional[Dict[str, Any]]:
        cleaned_summary = self._strip_headings(exec_summary)
        if not cleaned_summary:
            return None
        measurement_plan = quant_payload.get("measurement_plan") or []
        targets: List[str] = []
        if metric_spec:
            targets = self._metric_targets_from_spec(metric_spec) or []
        if not targets:
            for row in measurement_plan:
                metric = self._sanitize_text(row.get("metric", ""))
                expression = self._sanitize_text(row.get("expression", ""))
                timeframe = self._sanitize_text(row.get("timeframe", ""))
                if not metric:
                    continue
                pieces = [metric]
                if expression:
                    pieces.append(expression)
                if timeframe:
                    pieces.append(f"Window {timeframe}")
                targets.append(" — ".join(piece for piece in pieces if piece))
        if not targets:
            anchors = quant_payload.get("anchors") or []
            for anchor in anchors:
                topic = self._sanitize_text(anchor.get("topic") or anchor.get("label") or "")
                value = self._sanitize_text(
                    anchor.get("expression") or anchor.get("value") or anchor.get("unit") or ""
                )
                if topic:
                    targets.append(f"{topic}: {value}".strip(": "))
        activation = sections.get("activation_kit") or []
        activation_snippets = []
        for play in activation:
            display = play.get("display", {})
            title_snippet = self._sanitize_text(
                display.get("card_title")
                or display.get("play_name")
                or play.get("play_name")
                or play.get("pillar")
                or ""
            )
            summary = self._sanitize_text(display.get("proof_point") or "")
            if title_snippet:
                activation_snippets.append({"title": title_snippet, "summary": summary})
        risk_headlines = [
            self._sanitize_text(risk.get("risk_name", ""))
            for risk in sections.get("risk_radar") or []
            if risk.get("risk_name")
        ]
        operator_job_story = ""
        approach_names: List[str] = []
        search_variants: List[str] = []
        unified_pack: Dict[str, Any] = {}
        evidence_note = ""
        evidence_regime = "healthy"
        if scope:
            operator_job_story = self._sanitize_text(scope.get("operator_job_story", ""))
            approach_names = [
                self._sanitize_text(name)
                for name in scope.get("approach_hints", [])
                if self._sanitize_text(name)
            ]
            search_variants = [
                self._sanitize_text(variant)
                for variant in scope.get("search_shaped_variants", [])
                if self._sanitize_text(variant)
            ]
            unified_pack = scope.get("unified_target_pack", {}) or {}
            evidence_note = self._sanitize_text(scope.get("evidence_note", ""))
            evidence_regime = scope.get("evidence_regime", "healthy")
        return {
            "report_title": title,
            "exec_summary": cleaned_summary,
            "quant_targets": targets[:6],
            "activation_snippets": activation_snippets[:5],
            "risk_headlines": risk_headlines[:6],
            "tone_hint": "slightly impatient but constructive",
            "operator_job_story": operator_job_story,
            "approach_names": approach_names,
            "search_shaped_variants": search_variants,
            "unified_target_pack": unified_pack,
            "evidence_note": evidence_note,
            "evidence_regime": evidence_regime,
            "pilot_spec": pilot_spec or {},
            "metric_spec": metric_spec or {},
            "role_actions": role_actions or {},
        }

    def _validate_executive_letter(self, letter: Dict[str, Any]) -> bool:
        sections = letter.get("sections")
        if not isinstance(sections, list) or len(sections) != 5:
            return False
        total_words = 0
        for block in sections:
            body = (block.get("body") or "").strip()
            if not body:
                return False
            sentence_count = len(re.findall(r"[.!?]", body))
            if sentence_count < 2 or sentence_count > 4:
                return False
            total_words += len(body.split())
        if total_words > 600 or total_words < 300:
            return False
        investable = letter.get("bullets_investable") or []
        targets = letter.get("bullets_targets") or []
        if len(investable) != 3 or len(targets) != 3:
            return False
        for bullet in targets:
            if not re.search(r"\d", bullet or ""):
                return False
        return True

    def _qa_report(
        self,
        signals: List[Dict[str, Any]],
        sections: Dict[str, Any],
        top_moves: List[str],
        scope: Dict[str, Any],
        quant_payload: Dict[str, Any],
        appendix: List[Dict[str, Any]],
        read_time_minutes: int,
    ) -> Dict[str, Any]:
        issues: List[str] = []
        if scope.get("thin_evidence"):
            issues.append("Source coverage under minimum thresholds")

        def _sentence_count(text: str) -> int:
            if not text:
                return 0
            return len(re.findall(r"[.!?](?:\s|$)", text))
        if len(signals) < 5 or len(signals) > STIConfig.SIGNAL_MAX_COUNT:
            issues.append("Signal count outside required band")
        if len(top_moves) != STIConfig.TOP_OPERATOR_MOVE_COUNT:
            issues.append("Top operator moves not equal to 3")
        high_quality_signals = True
        market_signals = 0
        market_tier1 = True
        for signal in signals:
            if signal.get("US_fit", 0) < STIConfig.SIGNAL_MIN_US_FIT:
                issues.append(f"Signal {signal.get('id')} under US-fit threshold")
            grade = signal.get("source_grade", "C")
            if GRADE_ORDER.get(grade, 2) > 1:
                high_quality_signals = False
            category = (signal.get("category") or "").lower()
            if category.startswith("market"):
                market_signals += 1
                if grade != "A":
                    market_tier1 = False
            if not (signal.get("operator_move") or "").strip():
                issues.append(f"Signal {signal.get('id')} missing operator move")
        quant_anchors = quant_payload.get("anchors", [])
        measurement_plan = quant_payload.get("measurement_plan", [])
        if len(quant_anchors) < 2:
            issues.append("Quantifier returned fewer than two anchors")
        if len(quant_anchors) > 4:
            issues.append("Too many quant anchors")
        if len(measurement_plan) > 4:
            issues.append("Measurement plan exceeds 4 items")
        coverage = min(1.0, len(signals) / float(STIConfig.SIGNAL_TARGET_COUNT))
        quant_support = min(
            1.0,
            len(
                [
                    a
                    for a in quant_anchors
                    if a.get("value")
                    or a.get("value_high")
                    or a.get("value_low")
                    or a.get("expression")
                ]
            )
            / 3.0,
        )
        contradiction_penalty = max(0.0, 1.0 - 0.1 * len(issues))
        deep_section_entries = sections.get("deep_analysis", {}).get("sections", [])
        deep_sections = len(deep_section_entries)
        if deep_sections > 4:
            issues.append("Deep analysis exceeds 4 sections")
        for block in deep_section_entries:
            insight = block.get("insight", "")
            if insight and _sentence_count(insight) > 4:
                issues.append(f"Deep analysis paragraph exceeds sentence cap ({block.get('title')})")
        summary_text = sections.get("deep_analysis", {}).get("summary", "")
        if summary_text and _sentence_count(summary_text) > 4:
            issues.append("Deep analysis summary exceeds sentence cap")
        brand_outcomes = len(sections.get("brand_outcomes", []))
        if brand_outcomes > 4:
            issues.append("Brand outcomes exceed 4")
        activation = sections.get("activation_kit", [])
        activation_len = len(activation)
        if activation_len > STIConfig.MAX_ACTIVATION_PLAYS:
            issues.append("Activation kit exceeds allowed play count")
        for play in activation:
            ops = play.get("ops") or {}
            cadence = ops.get("cadence") or []
            for touch in cadence:
                cta = (touch.get("cta") or "").strip()
                if not cta:
                    issues.append(f"Cadence missing CTA for {self._activation_label(play)}")
                elif "specify cta" in cta.lower():
                    issues.append(f"Cadence placeholder CTA for {self._activation_label(play)}")
            if ops.get("zero_new_sku") is None or ops.get("ops_drag") is None:
                issues.append(f"Play {self._activation_label(play)} missing zero_new_sku or ops_drag tags")
        risk_len = len(sections.get("risk_radar", []))
        if risk_len > 4:
            issues.append("Risk radar exceeds 4")
        outlook_len = len(sections.get("future_outlook", []))
        if outlook_len > 2:
            issues.append("Future outlook should only include 6- and 12-month horizons unless special case")
        if read_time_minutes > STIConfig.TARGET_READ_TIME_MINUTES:
            issues.append("Read time exceeds target")
        observed_anchor = any(
            str(anchor.get("status", "")).lower() == "observed" for anchor in quant_anchors
        )
        if market_signals == 0:
            market_tier1 = True
        qa = {
            "issues": issues,
            "coverage": round(coverage, 3),
            "quant_support": round(quant_support, 3),
            "contradiction_penalty": round(contradiction_penalty, 3),
            "appendix_count": len(appendix),
            "scope": scope,
            "read_time": read_time_minutes,
            "high_quality_signals": high_quality_signals,
            "observed_quant": observed_anchor,
            "tier1_market_signals": market_tier1,
        }
        return qa

    def _compute_confidence(
        self,
        signals: List[Dict[str, Any]],
        qa_report: Dict[str, Any],
        quant_payload: Dict[str, Any],
    ) -> ConfidenceBreakdown:
        avg_strength = 0.0
        if signals:
            avg_strength = sum(sig.get("strength", 0.0) for sig in signals) / len(signals)
        coverage = qa_report.get("coverage", 0.5)
        quant_support = qa_report.get("quant_support", quant_payload.get("coverage", 0.5))
        contradiction_penalty = qa_report.get("contradiction_penalty", 0.8)
        return ConfidenceBreakdown(
            average_strength=avg_strength,
            coverage=coverage,
            quant_support=quant_support,
            contradiction_penalty=contradiction_penalty,
        )

    def _apply_source_caps(self, score: float, source_stats: Dict[str, Any]) -> float:
        if not source_stats:
            return score
        capped = float(score)
        if (
            source_stats.get("total", 0) < STIConfig.SOURCE_MIN_TOTAL
            or source_stats.get("unique_domains", 0) < STIConfig.SOURCE_MIN_UNIQUE_DOMAINS
        ):
            capped = min(capped, 0.65)
        if source_stats.get("core", 0) < STIConfig.SOURCE_MIN_CORE:
            capped = min(capped, 0.6)
        tier_counts = source_stats.get("tier_counts") or {}
        if tier_counts.get("context", 0) < STIConfig.SOURCE_MIN_BACKGROUND:
            capped = min(capped, 0.62)
        if source_stats.get("thin_evidence"):
            capped = min(capped, 0.6)
        return round(max(0.0, capped), 3)

    def _signal_support_coverage(self, signals: List[Dict[str, Any]], sources: List[SourceRecord]) -> float:
        if not signals or not sources:
            return 0.0
        used: set[int] = set()
        for signal in signals:
            if not signal.get("on_spine", True):
                continue
            for sid in signal.get("support") or []:
                if isinstance(sid, int):
                    used.add(sid)
        if not used:
            return 0.0
        return min(1.0, len(used) / float(len(sources)))

    def _metric_text(self, text: Any) -> str:
        if not text:
            return ""
        return replace_metric_tokens(str(text))

    def _evidence_regime(self, stats: Dict[str, Any]) -> str:
        total = stats.get("total", 0)
        if total <= 0:
            return "starved"
        core_sources = stats.get("core", 0)
        tier_counts = stats.get("tier_counts", {}) or {}
        in_window = tier_counts.get("core", 0)
        background = tier_counts.get("context", 0)
        thresholds = stats.get("thresholds", {}) or {}
        hard_fail = (
            total < STIConfig.SOURCE_HARD_FLOOR
            or in_window == 0
            or (background == 0 and total < STIConfig.SOURCE_MIN_TOTAL)
        )
        if hard_fail:
            return "starved"
        if core_sources == 0 or not all(thresholds.values()):
            return "directional"
        return "healthy"

    def _evidence_note(self, stats: Dict[str, Any]) -> str:
        total = stats.get("total", 0)
        unique = stats.get("unique_domains", 0)
        tier_counts = stats.get("tier_counts") or {}
        in_window = tier_counts.get("core", 0)
        background = tier_counts.get("context", 0)
        regime = stats.get("regime") or ("directional" if stats.get("thin_evidence") else "healthy")
        prefix = "Evidence base"
        if regime == "directional":
            prefix = "Directional evidence"
        if regime == "starved" or total <= 0:
            return f"{prefix}: too thin"
        summary = (
            f"{prefix}: {total} sources • {unique} domains • "
            f"{in_window} in-window / {background} background"
        )
        support_cov = stats.get("support_coverage")
        if support_cov is not None:
            summary += f" • support coverage {support_cov:.0%}"
        return summary

    def _normalize_date(self, value: Optional[str]) -> str:
        if not value:
            return datetime.utcnow().strftime("%Y-%m-%d")
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d")
        except Exception:
            return datetime.utcnow().strftime("%Y-%m-%d")

    def _within_window(self, date_str: str, days_back: int) -> bool:
        try:
            date_val = datetime.strptime(date_str, "%Y-%m-%d")
        except Exception:
            return True
        min_date = datetime.utcnow() - timedelta(days=days_back)
        return date_val >= min_date

    def _publisher_from_url(self, url: str) -> str:
        try:
            return urlparse(url).netloc.replace("www.", "")
        except Exception:
            return "unknown"

    def _annotate_source(self, source: SourceRecord, scope: Dict[str, Any]) -> None:
        host = self._publisher_from_url(source.url)
        snippet = f"{source.title} {source.snippet} {source.content[:400]}"
        grade = self._domain_grade(host)
        us_fit = self._score_us_fit(snippet)
        recency = self._recency_score(source.date, scope)
        evidence_depth = 0.85 if self._has_quantitative_data(snippet) else 0.45
        if "survey" in snippet.lower():
            evidence_depth = max(evidence_depth, 0.65)

        authority = source.credibility
        source_type = self._infer_source_type(host, snippet)
        if host in STIConfig.SOURCE_BLOCKLIST or source_type == "aggregator":
            authority = min(authority, 0.45)
            source_type = "aggregator"
            grade = "D"

        source.domain = self._classify_domain(host, snippet)
        source.region = "US" if us_fit >= 0.75 else "context"
        source.source_type = source_type
        source.authority = authority
        source.recency = recency
        source.us_fit = us_fit
        source.evidence = {
            "numeric": evidence_depth >= 0.75,
            "depth": round(evidence_depth, 2),
            "sample_size": self._extract_sample_size(snippet),
        }
        quality = 0.45 * authority + 0.25 * recency + 0.20 * us_fit + 0.10 * evidence_depth
        source.quality = round(min(1.0, quality), 3)
        source.source_grade = grade
        core_grade = GRADE_ORDER.get(grade, 2) <= 1
        source.role = "core" if source.quality >= STIConfig.QUALITY_THRESHOLD and us_fit >= STIConfig.SIGNAL_MIN_US_FIT and core_grade else "support"

    def _classify_domain(self, host: str, text: str) -> str:
        text_lower = text.lower()
        if any(keyword in text_lower for keyword in ["foot traffic", "placer.ai", "visa", "safegraph"]):
            return "foot_traffic"
        if any(keyword in text_lower for keyword in ["pricing", "discount", "promotion", "coupon"]):
            return "pricing_promo"
        if any(keyword in text_lower for keyword in ["ai", "automation", "agentic"]):
            return "ops_ai"
        if any(keyword in text_lower for keyword in ["family", "cultural", "holiday", "festival"]):
            return "cultural_events"
        if any(keyword in host for keyword in ["retail", "commerce"]):
            return "retail_ecom"
        return "general"

    def _infer_source_type(self, host: str, text: str) -> str:
        host = host.lower()
        if any(tag in host for tag in ["prnewswire", "businesswire", "globenewswire"]):
            return "pr"
        if "blog" in host or "substack" in host:
            return "analysis"
        if "gov" in host or "census" in host:
            return "primary"
        if "placer.ai" in text.lower() or "nrf" in text.lower():
            return "primary"
        return "analysis"

    def _domain_grade(self, host: str) -> str:
        host = (host or "").lower()
        if not host:
            return STIConfig.SOURCE_GRADE_FALLBACK
        for grade, domains in STIConfig.SOURCE_DOMAIN_GRADES.items():
            if host in domains:
                return grade
        if host in STIConfig.SOURCE_BLOCKLIST or "msn.com" in host:
            return "D"
        if host.endswith(".yahoo.com") or host.endswith(".news"):
            return "D"
        return STIConfig.SOURCE_GRADE_FALLBACK

    def _score_us_fit(self, text: str) -> float:
        text_lower = (text or "").lower()
        matches = sum(1 for keyword in STIConfig.US_REGION_HINTS if keyword in text_lower)
        foreign_hints = sum(1 for keyword in ["uk", "london", "manila", "philippines", "singapore"] if keyword in text_lower)
        base = min(1.0, matches / 3.0)
        if foreign_hints:
            base -= 0.2 * foreign_hints
        return max(0.0, min(1.0, base + 0.3 if "us" in text_lower else base))

    def _has_quantitative_data(self, text: str) -> bool:
        return bool(re.search(r"\d{2,}%|\d{4}", text))

    def _extract_sample_size(self, text: str) -> str:
        match = re.search(r"(\d{2,},?\d{0,3})\s+(stores|shoppers|respondents)", text.lower())
        return match.group(0) if match else ""

    def _recency_score(self, date_str: str, scope: Dict[str, Any]) -> float:
        try:
            date_val = datetime.strptime(date_str, "%Y-%m-%d")
            window_days = max(1, scope.get("time_window", {}).get("days", STIConfig.DEFAULT_DAYS_BACK))
            delta = (datetime.utcnow() - date_val).days
            return max(0.0, min(1.0, 1 - (delta / float(window_days))))
        except Exception:
            return 0.5

    def _fetch_content(self, url: str) -> str:
        try:
            resp = requests.get(url, timeout=STIConfig.HTTP_TIMEOUT_SECONDS)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            text = soup.get_text(separator=" ", strip=True)
            text = re.sub(r"\s+", " ", text)
            return text[:6000]
        except Exception:
            return ""

    def _score_publisher(self, url: str) -> float:
        host = self._publisher_from_url(url)
        return STIConfig.SOURCE_DOMAIN_WEIGHTS.get(host, STIConfig.DEFAULT_SOURCE_WEIGHT)

    # ------------------------------------------------------------------
    # Section + confidence helpers
    # ------------------------------------------------------------------
    def _tool_json(self, payload: str) -> Dict[str, Any]:
        try:
            return json.loads(payload) if payload else {}
        except Exception:
            return {}

    def _build_sections(
        self,
        sources_payload: str,
        signals: List[Dict[str, Any]],
        operator_notes: str,
        quant_payload: Dict[str, Any],
        scope_json: str,
    ) -> Dict[str, Any]:
        signals_json = json.dumps(signals, ensure_ascii=False)
        quant_json = json.dumps(quant_payload, ensure_ascii=False)

        deep = self._tool_json(
            generate_deep_analysis(sources_payload, signals_json, quant_json, scope_json)
        ).get("deep_analysis", {})
        if isinstance(deep, dict):
            deep_sections = deep.get("sections", []) or []
            deep["sections"] = self._sort_spine_sections(deep_sections)
        patterns = self._tool_json(
            generate_pattern_matches(sources_payload, signals_json, quant_json, scope_json)
        ).get("pattern_matches", [])
        outcomes = self._tool_json(
            generate_brand_outcomes(sources_payload, signals_json, quant_json, scope_json)
        ).get("brand_outcomes", [])

        sections_seed = {
            "deep_analysis": deep,
            "pattern_matches": patterns,
            "brand_outcomes": outcomes,
            "operator_notes": operator_notes,
            "quant": quant_payload,
        }
        sections_json = json.dumps(sections_seed, ensure_ascii=False)

        activation = self._tool_json(
            generate_activation_kit(signals_json, sections_json, quant_json)
        ).get("activation_kit", [])
        activation = self._merge_activation_plays(activation)
        if len(activation) > STIConfig.MAX_ACTIVATION_PLAYS:
            activation = activation[: STIConfig.MAX_ACTIVATION_PLAYS]
        risks = self._tool_json(generate_risk_radar(signals_json, sections_json)).get("risk_radar", [])
        outlook = self._tool_json(generate_future_outlook(signals_json, sections_json, scope_json)).get(
            "future_outlook", []
        )
        comparison_sections = {
            **sections_seed,
            "activation_kit": activation,
            "risk_radar": risks,
            "future_outlook": outlook,
        }
        comparison_map = self._tool_json(
            generate_comparison_map(
                signals_json,
                json.dumps(comparison_sections, ensure_ascii=False),
                scope_json,
            )
        ) or {}

        sections = {
            **sections_seed,
            "activation_kit": activation,
            "risk_radar": risks,
            "future_outlook": outlook,
            "comparison_map": comparison_map,
            "signal_map_notes": operator_notes,
        }
        self._trace(
            "sections:summary",
            {
                "deep_analysis_sections": len(deep.get("sections", [])),
                "pattern_matches": len(patterns),
                "brand_outcomes": len(outcomes),
                "activation_kit": len(activation),
                "risk_radar": len(risks),
                "future_outlook": len(outlook),
                "approach_map_entries": len((comparison_map or {}).get("approach_map", [])),
                "buyer_guide_entries": len((comparison_map or {}).get("buyer_guide", [])),
            },
        )
        return sections

    def _build_markdown(
        self,
        query: str,
        title: str,
        exec_summary: str,
        highlights: List[str],
        top_moves: List[str],
        play_summary: List[Dict[str, Any]],
        fast_path: Dict[str, Any],
        fast_stack: Dict[str, Any],
        spine: Dict[str, str],
        signals: List[Dict[str, Any]],
        sections: Dict[str, Any],
        sources: List[SourceRecord],
        quant_payload: Dict[str, Any],
        appendix: List[Dict[str, Any]],
        pilot_spec: Optional[Dict[str, Any]] = None,
        metric_spec: Optional[Dict[str, Any]] = None,
        role_actions: Optional[Dict[str, str]] = None,
    ) -> str:
        fast_sections = (fast_path or {}).get("sections") or [
            "executive_summary",
            "highlights",
            "top_operator_moves",
            "play_summary",
        ]
        lines = [f"# {title}", f"_Query_: {query}", ""]
        if fast_stack:
            lines.append("### Fast Stack")
            if fast_stack.get("headline"):
                lines.append(f"- **Headline:** {fast_stack['headline']}")
            if fast_stack.get("why_now"):
                lines.append(f"- **Why now:** {fast_stack['why_now']}")
            if fast_stack.get("next_30_days"):
                lines.append(f"- **Next 30 days:** {fast_stack['next_30_days']}")
            lines.append("")
        lines.append("## Fast Path")
        for section_name in fast_sections:
            if section_name == "executive_summary":
                lines.append("### Executive Take")
                lines.append(exec_summary)
            elif section_name == "highlights" and highlights:
                lines.append("### Highlights")
                for bullet in highlights:
                    lines.append(f"- {bullet}")
            elif section_name == "top_operator_moves" and top_moves:
                lines.append("### Top Operator Moves")
                for move in top_moves:
                    lines.append(f"- {move}")
            elif section_name == "play_summary" and play_summary:
                lines.append("### Plays")
                for play in play_summary:
                    lines.append(f"- **{play.get('label')}** — {play.get('success')}")
            lines.append("")
        lines.extend(["---", "", "## For operators and collab leads", ""])
        if spine:
            spine_bits: List[str] = []
            if spine.get("what"):
                spine_bits.append(f"What: {spine['what']}")
            if spine.get("so_what"):
                spine_bits.append(f"Proof: {spine['so_what']}")
            if spine.get("now_what"):
                spine_bits.append(f"Move: {spine['now_what']}")
            lines.append(f"_Spine:_ {' | '.join(spine_bits)}")
            lines.append("")
        lines.append("## Signal Map")
        for signal in signals:
            cites = "".join(f"[^{cid}]" for cid in signal.get("citations", []))
            horizon = signal.get("time_horizon") or "now"
            lines.append(f"- **{signal.get('category')} — {signal.get('name')}** ({horizon})")
            if signal.get("spine_hook"):
                lines.append(f"  _Spine hook_: {signal['spine_hook']}")
            lines.append(f"  {signal.get('description', '')}")
            if signal.get("operator_scan"):
                lines.append(f"  _Operator scan_: {signal['operator_scan']}")
            lines.append(f"  _Operator move_: {signal.get('operator_move', '')} {cites}")
        use_spec_anchors = isinstance(metric_spec, dict) and bool(metric_spec)
        anchors = metric_spec if use_spec_anchors else quant_payload.get("anchors", [])
        measurements = quant_payload.get("measurement_plan", [])
        if anchors or measurements:
            lines.extend(["", "## Measurement Spine"])
        if anchors:
            lines.append("### Anchors")
            if use_spec_anchors:
                for metric_id, entry in anchors.items():
                    label = entry.get("label") or friendly_metric_label(metric_id)
                    stage = (entry.get("stage") or "target").lower()
                    if stage == "stretch":
                        display_label = f"Stretch {label}"
                    elif stage == "guardrail":
                        display_label = f"{label} guardrail"
                    elif stage == "observed":
                        display_label = f"Observed {label}"
                    else:
                        display_label = label
                    value_text = entry.get("target_text") or self._format_metric_target(
                        entry.get("target_range") or [],
                        entry.get("unit") or "",
                    )
                    owner = entry.get("owner") or "Owner"
                    notes = entry.get("notes") or ""
                    note_text = f" ({notes})" if notes else ""
                    lines.append(f"- **{display_label}:** {value_text or 'Target TBD'} ({owner}){note_text}")
            else:
                for anchor in anchors:
                    raw_label = anchor.get("headline") or anchor.get("label") or anchor.get("metric") or "Anchor"
                    topic = anchor.get("topic") or anchor.get("metric") or raw_label
                    display_label = friendly_metric_label(topic)
                    stage = anchor_stage(raw_label)
                    if stage == "stretch":
                        display_label = f"Stretch {display_label}"
                    elif stage == "guardrail":
                        display_label = f"{display_label} guardrail"
                    elif stage == "observed":
                        display_label = f"Observed {display_label}"
                    status = (anchor.get("status") or "target").title()
                    band = (anchor.get("band") or "base").title()
                    value_text = anchor.get("expression") or anchor.get("value") or "n/a"
                    if anchor.get("value_low") is not None and anchor.get("value_high") is not None:
                        unit = anchor.get("unit") or ""
                        value_text = f"{anchor['value_low']}–{anchor['value_high']} {unit}".strip()
                    value_text = self._metric_text(value_text)
                    cites = "".join(f"[^{cid}]" for cid in anchor.get("source_ids", []))
                    owner = anchor.get("owner") or "Owner"
                    applies = ", ".join(anchor.get("applies_to_signals", []) or ["Signals"])
                    lines.append(f"- **{display_label}** ({status}/{band}): {value_text} {cites}")
                    lines.append(f"  Owner: {owner}; Applies to: {applies}")
        if measurements:
            lines.append("### Measurement Plan")
            for item in measurements:
                owner = item.get("owner") or "Owner"
                timeframe = item.get("timeframe") or "Window"
                metric = friendly_metric_label(item.get("metric") or "Metric")
                expression = self._metric_text(item.get("expression") or "Target TBD")
                lines.append(f"- **{metric}** ({owner}, {timeframe}) — {expression}")
                if item.get("why_it_matters"):
                    lines.append(f"  Why it matters: {self._metric_text(item['why_it_matters'])}")
            lines.append(
                "  Note: Buyer activity share in the early window is tracked separately from SKU promo share to protect margin while growing participation."
            )
        deep = sections.get("deep_analysis", {})
        if deep:
            lines.extend(["", "## Deep Analysis"])
            for section in deep.get("sections", []):
                scan_line = section.get("scan_line")
                heading = section.get("title") or "Insight"
                heading_line = f"### {heading}"
                if scan_line:
                    heading_line = f"{heading_line}: {self._metric_text(scan_line)}"
                lines.append(heading_line)
                lines.append(self._metric_text(section.get("insight", "")))
                if section.get("operator_note"):
                    lines.append(f"*Operator note:* {self._metric_text(section['operator_note'])}")
                if section.get("instrument_next"):
                    lines.append(f"*Instrument next:* {self._metric_text(section['instrument_next'])}")
        patterns = sections.get("pattern_matches", [])
        if patterns:
            lines.extend(["", "## Pattern Matches"])
            for match in patterns:
                lines.append(f"- **{match.get('label')}**")
                lines.append(f"  Then: {match.get('then')}")
                lines.append(f"  Now: {match.get('now')}")
                lines.append(f"  Operator leap: {match.get('operator_leap')}")
        outcomes = sections.get("brand_outcomes", [])
        if outcomes:
            lines.extend(["", "## Brand & Operator Outcomes"])
            for outcome in outcomes:
                lines.append(
                    f"- **{outcome.get('title')}** ({outcome.get('owner')} · {outcome.get('time_horizon')}): {outcome.get('description')} (Impact: {outcome.get('impact')})"
                )
        kit = sections.get("activation_kit", [])
        if kit:
            lines.extend(["", "## Activation Kit"])
            for play in kit:
                display = play.get("display", {})
                ops = play.get("ops", {})
                title_line = display.get("card_title") or display.get("play_name") or "Activation play"
                lines.append(f"### {title_line}")
                pillar = display.get("pillar") or "Pillar"
                persona = display.get("persona") or "Operator lead"
                horizon = display.get("time_horizon") or "immediate"
                lines.append(f"*Pillar:* {pillar} · *Persona:* {persona} · *Time horizon:* {horizon}")
                if display.get("why_now"):
                    lines.append(f"**Why now:** {display['why_now']}")
                if display.get("thresholds_summary"):
                    lines.append(f"**Thresholds:** {display['thresholds_summary']}")
                lines.append(
                    f"**Fit:** Best for {display.get('best_fit') or 'operators ready to instrument'}; Not for {display.get('not_for') or 'teams without guardrails'}."
                )
                if display.get("proof_point"):
                    lines.append(f"Proof: {display['proof_point']}")
                placements = display.get("placement_options") or []
                if placements:
                    lines.append(f"Placement options: {', '.join(placements)}")
                targets = ops.get("target_map") or []
                if targets:
                    lines.append("Target map:")
                    for entry in targets:
                        lines.append(
                            f"  - {entry.get('role')} ({entry.get('org_type')}): {entry.get('why_now')}"
                        )
                cadence = ops.get("cadence") or []
                if cadence:
                    lines.append("Cadence:")
                    for touch in cadence:
                        lines.append(
                            f"  - Day {touch.get('day')}: {touch.get('subject')} — {touch.get('narrative')} (CTA: {touch.get('cta')})"
                        )
                lines.append(
                    f"Ops tags: owner {ops.get('operator_owner') or 'TBD'} x {ops.get('collaborator') or 'collaborator'} | Collab type {ops.get('collab_type') or 'brand↔operator'} | Zero new SKUs: {'Yes' if ops.get('zero_new_sku') else 'No'} | Ops drag: {ops.get('ops_drag') or 'medium'}"
                )
            lines.append(
                "\n_The Brand Collab Lab turns these plays into named concepts, deck spines, and outreach ready for partner teams._"
            )
        risks = sections.get("risk_radar", [])
        if risks:
            lines.extend(["", "## Risk Radar"])
            for risk in risks:
                severity = risk.get("severity", 2)
                likelihood = risk.get("likelihood", 2)
                label = risk.get("scan_line") or risk.get("risk_name") or "Risk"
                lines.append(f"- **{label}** (Severity {severity}, Likelihood {likelihood})")
                lines.append(f"  Trigger: {risk.get('trigger', 'Unclear trigger')}")
                lines.append(f"  Detection: {risk.get('detection', 'Instrument leading indicators')}")
                lines.append(f"  Mitigation: {risk.get('mitigation', 'Throttle exposure')}")
        outlook = sections.get("future_outlook", [])
        if outlook:
            lines.extend(["", "## Future Outlook"])
            for horizon in outlook:
                lines.append(
                    f"- **{horizon.get('horizon')}** {horizon.get('headline')}: {horizon.get('scan_line')} (confidence {horizon.get('confidence', 0.7):.2f})"
                )
                lines.append(f"  {horizon.get('description')}")
                lines.append(f"  Watch {horizon.get('operator_watch')} for {horizon.get('collaboration_upside')}")
        lines.extend(["", "## Sources"])
        for source in sources:
            lines.append(
                f"[^{source.id}]: {source.title} — {source.publisher}, {source.date}. (cred: {source.credibility:.2f}) — {source.url}"
            )
        if appendix:
            lines.extend(["", "## Appendix Signals"])
            for signal in appendix:
                cites = "".join(f"[^{cid}]" for cid in signal.get("citations", []))
                lines.append(
                    f"- {signal.get('name', signal.get('id'))}: held for later window (strength {signal.get('strength', 0):.2f}) {cites}"
                )
        return "\n".join(line for line in lines if line is not None)

    def _build_json_ld(
        self,
        query: str,
        title: str,
        executive_summary: str,
        sources: List[SourceRecord],
        signals: List[Dict[str, Any]],
        days_back: int,
        confidence: float,
    ) -> Dict[str, Any]:
        end = datetime.utcnow()
        start = end - timedelta(days=days_back)
        has_part = []
        for signal in signals:
            citations = [sources[cid - 1].url for cid in signal.get("citations", []) if 0 < cid <= len(sources)]
            has_part.append(
                {
                    "@type": "AnalysisNewsArticle",
                    "headline": signal.get("text"),
                    "citation": citations,
                    "about": signal.get("category"),
                }
            )
        return {
            "@context": "https://schema.org",
            "@type": "Report",
            "name": title,
            "about": query,
            "abstract": executive_summary,
            "datePublished": datetime.utcnow().isoformat(),
            "temporalCoverage": f"{start.strftime('%Y-%m-%d')}/{end.strftime('%Y-%m-%d')}",
            "hasPart": has_part,
            "aggregateRating": {"@type": "AggregateRating", "ratingValue": confidence},
        }

    def _time_window(self, days_back: int) -> Dict[str, Any]:
        end = datetime.utcnow()
        start = end - timedelta(days=days_back)
        label = self._format_window_label(start, end)
        return {
            "start": start.strftime("%Y-%m-%d"),
            "end": end.strftime("%Y-%m-%d"),
            "days": days_back,
            "label": label,
        }

    def _window_label(self, window: Dict[str, Any]) -> str:
        if not window:
            return ""
        start_raw = window.get("start")
        end_raw = window.get("end")
        if not start_raw or not end_raw:
            return ""
        try:
            start_dt = datetime.strptime(start_raw, "%Y-%m-%d")
            end_dt = datetime.strptime(end_raw, "%Y-%m-%d")
        except ValueError:
            return f"{start_raw} – {end_raw}"
        return self._format_window_label(start_dt, end_dt)

    def _format_window_label(self, start_dt: datetime, end_dt: datetime) -> str:
        if start_dt.year == end_dt.year:
            if start_dt.month == end_dt.month:
                return f"{start_dt.strftime('%b %d')} – {end_dt.strftime('%d, %Y')}"
            return f"{start_dt.strftime('%b %d')} – {end_dt.strftime('%b %d, %Y')}"
        return f"{start_dt.strftime('%b %d, %Y')} – {end_dt.strftime('%b %d, %Y')}"

    def _apply_window_label(self, spec_bundle: Dict[str, Any], window_label: str) -> None:
        if not spec_bundle or not window_label:
            return
        pilot_spec = spec_bundle.get("pilot_spec")
        if isinstance(pilot_spec, dict):
            pilot_spec["window"] = window_label
            pilot_spec.setdefault("window_label", window_label)

    def _query_title(self, query: str) -> str:
        cleaned = re.sub(r"\s+", " ", (query or "STI Brief").strip())
        return cleaned or "STI Brief"

    def _trace(self, label: str, payload: Any = None) -> None:
        emit = self.trace_mode or logger.isEnabledFor(logging.DEBUG)
        if not emit:
            return
        target = logger.info if self.trace_mode else logger.debug
        if payload is None:
            target("[TRACE] %s", label)
            return
        try:
            serialized = json.dumps(payload, ensure_ascii=False, indent=2)
        except Exception:
            serialized = str(payload)
        max_len = 4000
        if len(serialized) > max_len:
            serialized = serialized[: max_len - 3] + "..."
        target("[TRACE] %s: %s", label, serialized)

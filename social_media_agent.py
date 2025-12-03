"""Lightweight social content generator with operator-friendly provenance."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


def _truncate_at_sentence(text: str, limit: int) -> str:
    snippet = text.strip()
    if len(snippet) <= limit:
        return snippet
    truncated = snippet[:limit]
    period = truncated.rfind(". ")
    if period != -1:
        truncated = truncated[: period + 1]
    return truncated


class SocialMediaAgent:
    """Generate shareable snippets with provenance disclosures."""

    def __init__(self, api_key: str, model_name: str):
        self.api_key = api_key
        self.model_name = model_name

    def generate_all_formats(
        self, report: str, context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        context = context or {}
        confidence = self._resolve_confidence(context.get("confidence", 0.7))
        title = context.get("title") or context.get("query") or "STI Brief"
        signals = context.get("signals") or []
        sources = context.get("sources") or []

        claim = self._headline_claim(signals) or self._fallback_claim(report)
        provenance_tail = self._provenance_tail(signals, sources)
        teaser_mode = confidence < 0.65

        linkedin_post = self._linkedin_post(title, claim, teaser_mode, provenance_tail)
        thread = self._twitter_thread(title, claim, teaser_mode, provenance_tail)
        long_form = self._long_form_update(title, claim, teaser_mode, provenance_tail)

        return {
            "linkedin_post": linkedin_post.strip(),
            "twitter_thread": thread,
            "long_form": long_form.strip(),
            "metadata": {
                "confidence": confidence,
                "teaser_mode": teaser_mode,
                "sources_used": provenance_tail.strip(" ()"),
            },
        }

    def _resolve_confidence(self, value: Any) -> float:
        fallback = 0.7
        if isinstance(value, dict):
            for key in ("display", "score", "value"):
                potential = value.get(key)
                if potential is None:
                    continue
                try:
                    return float(potential)
                except (TypeError, ValueError):
                    continue
            return fallback
        try:
            return float(value)
        except (TypeError, ValueError):
            return fallback

    def _linkedin_post(self, title: str, claim: str, teaser: bool, provenance: str) -> str:
        if teaser:
            body = f"What we're testing next from '{title}': {claim}"
            call_to_action = (
                "Looking for operators willing to validate instrumentation. DM if you're tracking it."
            )
        else:
            body = f"'{title}' drops today. Key takeaway: {claim}"
            call_to_action = "Full brief, activation kit, and operator notes inside."
        return f"{body}{provenance}\n\n{call_to_action}"

    def _twitter_thread(self, title: str, claim: str, teaser: bool, provenance: str) -> List[str]:
        opening = f"STI brief: {title}" if not teaser else f"What we're instrumenting next: {title}"
        second = claim + provenance
        closing = (
            "More in the full report → sti.ai"
            if not teaser
            else "Thread will update as we validate studio partners."
        )
        return [opening, second, closing]

    def _long_form_update(self, title: str, claim: str, teaser: bool, provenance: str) -> str:
        header = f"### {title}\n\n"
        body = f"- Primary claim: {claim}{provenance}\n"
        tail = "- Status: in validation (signal density growing)" if teaser else "- Status: publish-ready"
        return header + body + tail

    def _headline_claim(self, signals: List[Dict[str, Any]]) -> Optional[str]:
        if not signals:
            return None
        text = signals[0].get("text", "")
        return _truncate_at_sentence(text, 240)

    def _fallback_claim(self, report: str) -> str:
        first_line = report.strip().split("\n", 1)[0]
        return _truncate_at_sentence(first_line, 240)

    def _provenance_tail(self, signals: List[Dict[str, Any]], sources: List[Dict[str, Any]]) -> str:
        cluster = self._build_cluster(signals, sources)
        return f" ({' | '.join(cluster)})" if cluster else ""

    def _build_cluster(self, signals: List[Dict[str, Any]], sources: List[Dict[str, Any]]) -> List[str]:
        if not signals or not sources:
            return []
        source_map = {int(s.get("id")): s for s in sources if s.get("id") is not None}
        cluster: List[str] = []
        for signal in signals:
            for cid in signal.get("citations", []):
                src = source_map.get(int(cid))
                if not src:
                    continue
                publisher = src.get("publisher") or ""
                year = self._extract_year(src.get("date", ""))
                label = f"{publisher} '{year[-2:]}" if year else publisher
                label = label.strip()
                if label and label not in cluster:
                    cluster.append(label)
                if len(cluster) == 3:
                    return cluster
        return cluster

    def _extract_year(self, text: str) -> str:
        if not text:
            return ""
        match = re.search(r"(20\\d{2}|19\\d{2})", text)
        return match.group(1) if match else ""

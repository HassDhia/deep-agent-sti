"""Lightweight social content generator with gating logic."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


class SocialMediaAgent:
    """Generate shareable snippets with provenance disclosures."""

    def __init__(self, api_key: str, model_name: str):
        self.api_key = api_key
        self.model_name = model_name

    def generate_all_formats(self, report: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        context = context or {}
        confidence = float(context.get("confidence", 0.7) or 0.7)
        title = context.get("title") or context.get("query") or "STI Brief"
        ledger = context.get("ledger") or {}
        sources = context.get("sources") or []

        cluster = self._provenance_cluster(ledger, sources)
        cluster_text = " | ".join(cluster) if cluster else ""
        provenance_tail = f" (anchors: {cluster_text})" if cluster_text else ""

        headline_claim = self._headline_claim(ledger) or self._fallback_claim(report)
        teaser_mode = confidence < 0.65

        linkedin_post = self._linkedin_post(title, headline_claim, teaser_mode, provenance_tail)
        thread = self._twitter_thread(title, headline_claim, teaser_mode, provenance_tail)
        long_form = self._long_form_update(title, headline_claim, teaser_mode, provenance_tail)

        return {
            "linkedin_post": linkedin_post.strip(),
            "twitter_thread": thread,
            "long_form": long_form.strip(),
            "metadata": {
                "confidence": confidence,
                "anchors": cluster,
                "teaser_mode": teaser_mode,
            },
        }

    def _linkedin_post(self, title: str, claim: str, teaser: bool, provenance: str) -> str:
        if teaser:
            body = f"What we're testing next from '{title}': {claim}"
            call_to_action = "Looking for operators willing to validate instrumentation. DM if you're tracking it."
        else:
            body = f"'{title}' drops today. Key takeaway: {claim}"
            call_to_action = "Full brief, expanded lenses, and quantitative guardrails inside."
        return f"{body}{provenance}\n\n{call_to_action}"

    def _twitter_thread(self, title: str, claim: str, teaser: bool, provenance: str) -> List[str]:
        opening = f"STI brief: {title}" if not teaser else f"What we're instrumenting next: {title}"
        second = claim + provenance
        closing = "More in the full report → sti.ai" if not teaser else "Thread will update as we validate anchors."
        return [opening, second, closing]

    def _long_form_update(self, title: str, claim: str, teaser: bool, provenance: str) -> str:
        header = f"### {title}\n\n"
        body = f"- Primary claim: {claim}{provenance}\n"
        tail = "- Status: in validation (anchors thin)" if teaser else "- Status: publish-ready"
        return header + body + tail

    def _headline_claim(self, ledger: Dict[str, Any]) -> Optional[str]:
        if not ledger:
            return None
        claims = ledger.get('claims') or []
        if not claims:
            return None
        top = claims[0]
        text = top.get('claim_text') or top.get('text') or ''
        return text.strip()[:240]

    def _fallback_claim(self, report: str) -> str:
        first_line = report.strip().split('\n', 1)[0]
        return first_line[:240]

    def _provenance_cluster(self, ledger: Dict[str, Any], sources: List[Dict[str, Any]]) -> List[str]:
        if not ledger or not sources:
            return []
        source_map = {str(s.get('id')): s for s in sources}
        cluster: List[str] = []
        for claim in ledger.get('claims', []):
            for span in claim.get('support_spans', []):
                src = source_map.get(str(span.get('source_id')))
                if not src:
                    continue
                publisher = src.get('publisher') or src.get('publisher_date', '').split(',')[0]
                publisher = publisher.strip()
                year = self._extract_year(src.get('publisher_date', ''))
                label = f"{publisher} '{year[-2:]}" if year else publisher
                if label and label not in cluster:
                    cluster.append(label)
                if len(cluster) == 3:
                    return cluster
        return cluster

    def _extract_year(self, text: str) -> str:
        if not text:
            return ""
        match = re.search(r"(20\d{2}|19\d{2})", text)
        return match.group(1) if match else ""

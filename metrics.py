"""Shared helpers for labeling measurement metrics."""

from __future__ import annotations

import re
from typing import Dict, Set

METRIC_LABELS: Dict[str, str] = {
    "footfall_lift": "Foot-traffic uplift",
    "foot_traffic_uplift": "Foot traffic",
    "foot_traffic": "Foot traffic",
    "early_window_share": "Early-window share",
    "buyer_activity_share": "Early share of purchases",
    "event_cpa": "Event CPA",
    "qr_redemption": "QR redemption",
    "dwell_time": "Dwell time",
    "partner_value": "Partner value",
    "conversion_rate": "Conversion rate",
    "blended_margin": "Blended margin",
    "repeat_rate": "Repeat rate",
    "traffic_share": "Traffic share",
    "category_lift": "Category sales lift",
}


def friendly_metric_name(key: str) -> str:
    normalized = (key or "").strip().lower()
    if not normalized:
        return ""
    label = METRIC_LABELS.get(normalized)
    if label:
        return label
    return normalized.replace("_", " ").title()


def friendly_metric_label(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return "Metric"
    normalized = text.lower()
    label = METRIC_LABELS.get(normalized)
    if label:
        return label
    friendly = friendly_metric_name(text)
    friendly = friendly or text.replace("_", " ")
    friendly = friendly.strip()
    return friendly[:1].upper() + friendly[1:] if friendly else "Metric"


def anchor_stage(label: str) -> str:
    value = (label or "").lower()
    if "stretch" in value:
        return "stretch"
    if "guardrail" in value:
        return "guardrail"
    if "observed" in value:
        return "observed"
    if "target" in value:
        return "target"
    return ""


def replace_metric_tokens(text: str) -> str:
    if not text:
        return ""
    updated = str(text)
    for raw, label in METRIC_LABELS.items():
        if "_" not in raw:
            continue
        pattern = re.compile(rf"\b{re.escape(raw)}\b", re.IGNORECASE)
        updated = pattern.sub(label, updated)
    return updated


def known_metric_ids() -> Set[str]:
    return set(METRIC_LABELS.keys())


__all__ = [
    "friendly_metric_name",
    "friendly_metric_label",
    "anchor_stage",
    "replace_metric_tokens",
    "known_metric_ids",
]

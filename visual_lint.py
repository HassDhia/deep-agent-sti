"""Helpers to validate visual anchor usage."""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Set

ANCHOR_SECTIONS: Dict[str, str] = {
    "header": "header",
    "signal_map": "signals_and_thesis",
    "measurement_spine": "measurement_spine",
    "case_study_1": "mini_case_story",
    "case_study_2": "deep_analysis",
    "case_study_3": "deep_analysis",
    "future_outlook": "future_outlook",
}
KNOWN_ANCHORS: Set[str] = set(ANCHOR_SECTIONS.keys())
REQUIRED_ANCHORS: Set[str] = {"signal_map"}


def lint_visual_stats(
    stats: Dict[str, List[str] | int],
    required_anchors: Optional[Iterable[str]] = None,
) -> List[str]:
    """Return severity-tagged issues detected from visual rendering stats."""

    issues: List[str] = []
    required = set(required_anchors) if required_anchors else set(REQUIRED_ANCHORS)
    used = set(stats.get("anchors_with_images") or [])
    missing_required = required - used
    if missing_required:
        issues.append(f"ERROR: Missing required visuals for {sorted(missing_required)}")
    extra = set(stats.get("anchors_found") or []) - KNOWN_ANCHORS
    if extra:
        issues.append(f"ERROR: Unknown anchor markers detected: {sorted(extra)}")
    gallery_size = stats.get("gallery_size", 0) or 0
    if gallery_size > 0:
        issues.append(f"WARN: {gallery_size} visuals fell back to gallery recap")
    return issues


__all__ = ["lint_visual_stats", "REQUIRED_ANCHORS", "ANCHOR_SECTIONS", "KNOWN_ANCHORS"]

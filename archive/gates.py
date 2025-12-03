"""Premium model gating policies."""

from __future__ import annotations

from typing import Dict, List


def value_of_information(metrics: Dict[str, float], path: str) -> List[str]:
    tasks: List[str] = []

    if metrics.get("anchor_coverage", 0.0) < 0.70:
        tasks.append("evidence_alignment")

    if metrics.get("quant_flags", 0.0) > 0:
        tasks.append("math_guard")

    if metrics.get("confidence", 0.0) < 0.75 or path == "theory":
        tasks.append("adversarial_review")

    if path == "theory":
        tasks.append("decision_playbooks")

    return tasks


def should_render_images(report_type: str, anchor_coverage: float, threshold: float = 0.70) -> bool:
    """
    Determine if images should be rendered based on report type and anchor coverage.
    
    Args:
        report_type: Report type ("theory", "thesis", "market", etc.)
        anchor_coverage: Anchor coverage score (0.0 to 1.0)
        threshold: Minimum anchor coverage threshold (default: 0.70) - no longer used
    
    Returns:
        True - images are always enabled for all reports
    """
    # Images are always enabled for all reports regardless of anchor coverage
    return True


def should_emit_social(report_type: str, anchor_coverage: float, threshold: float = 0.70) -> bool:
    """
    Determine if social media content should be generated based on report type and anchor coverage.
    
    Args:
        report_type: Report type ("theory", "thesis", "market", etc.)
        anchor_coverage: Anchor coverage score (0.0 to 1.0)
        threshold: Minimum anchor coverage threshold (default: 0.70) - no longer used
    
    Returns:
        True - social content is always enabled for all reports
    """
    # Social content is always enabled for all reports regardless of anchor coverage
    return True



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



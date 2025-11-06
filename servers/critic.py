"""Adversarial reviewer support for STI pipeline."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


def adversarial_review(
    report_sections: Dict[str, str],
    llm: Optional[Callable[[str, int], str]] = None,
    max_tokens: int = 900,
) -> Dict[str, List[str]]:
    """Return objections, boundary conditions, and falsification tests."""

    if llm is None:
        return _fallback_review()

    preview = {key: value[:800] for key, value in report_sections.items()}
    prompt = (
        "You are acting as the harshest reviewer. Given the report sections provided, "
        "return JSON with keys objections, boundary_conditions, falsification_tests. "
        "Objections should be steelman critiques. Boundary conditions describe where the thesis fails. "
        "Falsification tests list experiments or measurements to disprove the thesis.\n\n"
        f"Sections:\n{json.dumps(preview, indent=2)}"
    )

    try:
        raw = llm(prompt, max_tokens)
        match = re.search(r"\{.*\}", raw, flags=re.S)
        if not match:
            logger.warning("Adversarial review returned non-JSON payload, using fallback")
            return _fallback_review()
        return json.loads(match.group(0))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Adversarial review failed: %s", exc)
        return _fallback_review()


def decision_playbooks() -> List[Dict[str, Any]]:
    return [
        {
            "kpi": "MTTA_p95",
            "threshold": "<= 10 min",
            "action": "Automate detection and pre-authorize counter messaging",
            "expected_delta_risk": "Decrease cascade risk",
            "monitoring_lag": "near-real-time",
        },
        {
            "kpi": "PPV(min)",
            "threshold": ">= 0.85",
            "action": "Raise decision threshold; require dual-sensor corroboration",
            "expected_delta_risk": "Decrease false-trigger kinetic",
            "monitoring_lag": "per alert",
        },
        {
            "kpi": "t_half(persistence)",
            "threshold": "<= 7 days",
            "action": "Throttling + labeling + counter-speech",
            "expected_delta_risk": "Shorten long-tail belief",
            "monitoring_lag": "daily",
        },
        {
            "kpi": "Amplification Gain (G)",
            "threshold": "<= 1.2x",
            "action": "Ranking demotion for low-trust narratives",
            "expected_delta_risk": "Limit reach",
            "monitoring_lag": "weekly",
        },
    ]


def _fallback_review() -> Dict[str, List[str]]:
    return {
        "objections": [
            "Causality not proven; industrial scale may merely correlate with reach.",
            "External validity risk: platform findings may not generalize to broadcast environments.",
            "Classifier vignette ignores base-rate sensitivity.",
            "Institutional mediation could dominate industrial capacity in pluralistic media.",
            "Measurement opacity remains; MTTA lacks public datasets for verification.",
        ],
        "boundary_conditions": [
            "High press freedom coupled with professional editorial standards.",
            "Distribution systems with high channel diversity and low single points of failure.",
            "Verification costs subsidized through default attestation workflows.",
        ],
        "falsification_tests": [
            "Natural experiments around ranking/labeling policy changes with survival analysis.",
            "Red-team drills measuring MTTA p50/p95 before/after instrumentation.",
            "Holdout experiments estimating amplification gain versus random baseline feeds.",
        ],
    }



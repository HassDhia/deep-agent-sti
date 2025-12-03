"""Deterministic confidence scoring utilities for operator reports."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ConfidenceBreakdown:
    """Container for transparent confidence math displayed in every report."""

    average_strength: float
    coverage: float
    quant_support: float
    contradiction_penalty: float

    def clamp(self) -> "ConfidenceBreakdown":
        def _c(val: float) -> float:
            return max(0.0, min(1.0, float(val)))

        return ConfidenceBreakdown(
            average_strength=_c(self.average_strength),
            coverage=_c(self.coverage),
            quant_support=_c(self.quant_support),
            contradiction_penalty=_c(self.contradiction_penalty),
        )


def headline(breakdown: ConfidenceBreakdown) -> float:
    b = breakdown.clamp()
    score = (
        0.4 * b.average_strength
        + 0.3 * b.coverage
        + 0.2 * b.quant_support
        + 0.1 * b.contradiction_penalty
    )
    return round(score, 3)

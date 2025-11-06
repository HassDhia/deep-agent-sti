"""Deterministic confidence scoring utilities."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ConfidenceBreakdown:
    source_diversity: float
    anchor_coverage: float
    method_transparency: float
    replication_readiness: float

    def clamp(self) -> "ConfidenceBreakdown":
        def _c(val: float) -> float:
            return max(0.0, min(1.0, float(val)))

        return ConfidenceBreakdown(
            source_diversity=_c(self.source_diversity),
            anchor_coverage=_c(self.anchor_coverage),
            method_transparency=_c(self.method_transparency),
            replication_readiness=_c(self.replication_readiness),
        )


def headline(breakdown: ConfidenceBreakdown) -> float:
    b = breakdown.clamp()
    score = (
        0.30 * b.source_diversity
        + 0.25 * b.anchor_coverage
        + 0.25 * b.method_transparency
        + 0.20 * b.replication_readiness
    )
    return round(score, 3)



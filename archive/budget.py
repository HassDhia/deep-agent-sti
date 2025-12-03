"""Token budget utilities for premium model usage."""

from __future__ import annotations


class BudgetManager:
    """Manage reserved tokens for premium model usage."""

    def __init__(self, total_tokens: int = 0, pct: float = 0.25):
        pct = max(0.0, min(1.0, pct))
        self.reserved = max(0, int(total_tokens * pct))
        self.remaining = self.reserved

    def take(self, weight: float) -> int:
        weight = max(0.0, min(1.0, weight))
        allocation = min(int(self.reserved * weight), self.remaining)
        self.remaining -= allocation
        return allocation

    def slice(self, weight: float) -> int:
        return self.take(weight)

    def left(self) -> int:
        return self.remaining



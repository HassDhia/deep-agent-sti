"""Base classes for multi-format report renderers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List


class BaseRenderer(ABC):
    """Shared interface for any report renderer."""

    name: str = "base"

    @abstractmethod
    def render(self, report_bundle: Dict[str, Any], report_dir: str) -> List[str]:
        """Render the bundle into artifacts and return the written file paths."""

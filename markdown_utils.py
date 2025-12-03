"""Utilities for preparing Markdown artifacts before rendering."""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def insert_image_anchors(markdown: str, sections: Optional[Dict[str, Any]] = None) -> str:
    """Ensure Markdown contains stable HTML comment anchors for image placement."""

    if not markdown:
        return markdown

    updated = markdown
    updated = _ensure_anchor_after_heading(updated, "signal_map", r"^##\s+Signal Map\b")
    updated = _ensure_anchor_after_heading(updated, "future_outlook", r"^##\s+Future Outlook\b")

    activation_titles = _activation_titles(sections)
    for idx, title in enumerate(activation_titles):
        anchor = f"case_study_{idx + 1}"
        updated = _ensure_anchor_after_heading(
            updated,
            anchor,
            rf"^###\s+{re.escape(title)}\b",
        )

    return updated


def _anchor_exists(markdown: str, name: str) -> bool:
    token = f"<!-- image:{name}"
    return token in markdown


def _ensure_anchor_after_heading(markdown: str, anchor: str, heading_pattern: str) -> str:
    if _anchor_exists(markdown, anchor):
        return markdown
    match = re.search(heading_pattern, markdown, flags=re.MULTILINE | re.IGNORECASE)
    if not match:
        logger.warning("Image anchor '%s' not inserted; heading pattern '%s' missing.", anchor, heading_pattern)
        return markdown
    insert_at = match.end()
    insertion = f"\n\n<!-- image:{anchor} -->"
    return markdown[:insert_at] + insertion + markdown[insert_at:]


def _activation_titles(sections: Optional[Dict[str, Any]]) -> List[str]:
    if not isinstance(sections, dict):
        return []
    activation = sections.get("activation_kit")
    if not isinstance(activation, list):
        return []
    titles: List[str] = []
    for item in activation:
        if not isinstance(item, dict):
            continue
        display = item.get("display") or {}
        if isinstance(display, dict):
            title = (display.get("card_title") or display.get("play_name") or "").strip()
            if title:
                titles.append(title)
    return titles


__all__ = ["insert_image_anchors"]

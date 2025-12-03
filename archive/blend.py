"""
Blend: Merge market and thesis reports into unified output

Handles borderline cases where both market snapshot and theory capsule are valuable.
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


def merge_market_and_thesis(market: dict, thesis: dict, rationale: dict) -> dict:
    """
    Merge two single-source payloads into a unified 'Report' JSON.
    
    Assumes both `market` and `thesis` are valid dicts matching Report schema.
    Prefers the higher confidence as base; adds the other as a section.
    
    Args:
        market: Market report dict
        thesis: Thesis report dict
        rationale: Route rationale dict
        
    Returns:
        Merged report dict with path="blend"
    """
    # Prefer the higher confidence as base
    market_conf = market.get("confidence", {}).get("score", 0.0)
    if isinstance(market_conf, dict):
        market_conf = market_conf.get("score", 0.0)
    
    thesis_conf = thesis.get("confidence", {}).get("score", 0.0)
    if isinstance(thesis_conf, dict):
        thesis_conf = thesis_conf.get("score", 0.0)
    
    base = market if market_conf >= thesis_conf else thesis
    extra = thesis if base is market else market
    
    # Extract sections
    base_sections = list(base.get("sections", []))
    extra_sections = extra.get("sections", [])
    
    # Get executive summaries
    base_exec = base.get("exec_summary_md", "") or base.get("executive_summary", "")
    extra_exec = extra.get("exec_summary_md", "") or extra.get("executive_summary", "")
    
    # Create theory capsule or market snapshot section
    if base is market:
        # Add theory capsule after exec summary
        theory_content = extra_exec
        if extra_sections:
            # Add first section from thesis
            first_section = extra_sections[0]
            if isinstance(first_section, dict):
                theory_content += "\n\n" + first_section.get("md", "")
            else:
                theory_content += "\n\n" + str(first_section)
        
        capsule_section = {
            "id": "theory-capsule",
            "title": "Theory Capsule",
            "md": theory_content
        }
        # Insert after exec summary (index 0) or at index 1
        if base_sections:
            base_sections.insert(1, capsule_section)
        else:
            base_sections.append(capsule_section)
    else:
        # Add market snapshot after exec summary
        market_content = extra_exec
        if extra_sections:
            first_section = extra_sections[0]
            if isinstance(first_section, dict):
                market_content += "\n\n" + first_section.get("md", "")
            else:
                market_content += "\n\n" + str(first_section)
        
        snapshot_section = {
            "id": "market-snapshot",
            "title": "Market Snapshot",
            "md": market_content
        }
        if base_sections:
            base_sections.insert(1, snapshot_section)
        else:
            base_sections.append(snapshot_section)
    
    # Merge metadata
    base_metadata = base.get("metadata", {})
    extra_metadata = extra.get("metadata", {})
    merged_metadata = {**base_metadata, **rationale, **extra_metadata}
    
    # Merge sources (deduplicate by URL)
    base_sources = base.get("sources", [])
    extra_sources = extra.get("sources", [])
    seen_urls = set()
    merged_sources = []
    
    for src in base_sources + extra_sources:
        url = src.get("url") if isinstance(src, dict) else getattr(src, "url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            merged_sources.append(src)
    
    # Build merged report
    merged = dict(base)
    merged["path"] = "blend"
    merged["sections"] = base_sections
    merged["metadata"] = merged_metadata
    merged["sources"] = merged_sources
    
    # Merge confidence (use average or max)
    base_conf = market_conf if base is market else thesis_conf
    extra_conf = thesis_conf if base is market else market_conf
    merged_confidence = {
        "score": (base_conf + extra_conf) / 2.0,
        "breakdown": base.get("confidence", {}).get("breakdown", {})
    }
    merged["confidence"] = merged_confidence
    
    return merged


def _pull_first_section_md(payload: dict) -> str:
    """Extract markdown from first section of payload"""
    secs = payload.get("sections") or []
    if not secs:
        return ""
    
    first = secs[0]
    if isinstance(first, dict):
        return first.get("md", "")
    return str(first)


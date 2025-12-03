"""
Router: Explicit routing logic for Market vs Thesis vs Blend

Provides deterministic, testable routing while keeping CLI dead simple.
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

from config import STIConfig

logger = logging.getLogger(__name__)

# --- parameters (tune in config) ---
MARKET_OK = 0.70
THESIS_OK = 0.58  # anything below goes to thesis
FRESHNESS_DAYS = 7
WIRE_DOMAINS = {
    "reuters.com", "apnews.com", "bbc.com", "ft.com", 
    "wsj.com", "theguardian.com", "bloomberg.com"
}


@dataclass
class MarketProbe:
    """Lightweight market probe results"""
    fresh: int
    total: int
    unique_domains: int
    anchors: int
    domain_counts: Dict[str, int]


@dataclass
class ThesisProbe:
    """Lightweight thesis probe results"""
    canonical: int
    has_classics: bool


def _domain(u: str) -> str:
    """Extract domain from URL"""
    try:
        return urlparse(u).netloc.replace("www.", "").lower()
    except Exception:
        return ""


def market_probe(query: str, days: int, agent) -> MarketProbe:
    """
    Lightweight market fetch; no LLM needed.
    
    Args:
        query: Search query
        days: Days to look back
        agent: EnhancedSTIAgent instance for searching
        
    Returns:
        MarketProbe with market signal metrics
    """
    try:
        # Use agent's existing search method but limit results
        refined_query = agent._refine_query_for_title(query)
        results = agent._search_with_time_filtering(refined_query, days)
        
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        
        fresh = []
        counts = {}
        anchors = 0
        
        for r in results or []:
            try:
                # Parse date from source
                date_str = getattr(r, 'date', None) or getattr(r, 'published_at', None)
                if not date_str:
                    continue
                    
                # Try to parse date
                try:
                    if isinstance(date_str, str):
                        # Try ISO format first
                        if 'T' in date_str:
                            ts = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                        else:
                            ts = datetime.strptime(date_str, "%Y-%m-%d")
                            # Make timezone-aware by adding UTC timezone
                            if ts.tzinfo is None:
                                ts = ts.replace(tzinfo=timezone.utc)
                    else:
                        ts = date_str
                        # Ensure datetime is timezone-aware
                        if isinstance(ts, datetime) and ts.tzinfo is None:
                            ts = ts.replace(tzinfo=timezone.utc)
                except Exception:
                    # Fallback: check if source is marked as in_window
                    if getattr(r, 'is_in_window', False):
                        ts = datetime.now(timezone.utc)
                    else:
                        continue
                
                # Ensure both datetimes are timezone-aware before comparison
                if isinstance(ts, datetime) and ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                
                if ts >= cutoff:
                    fresh.append(r)
                    d = _domain(getattr(r, 'url', ''))
                    if d:
                        counts[d] = counts.get(d, 0) + 1
                        if d in WIRE_DOMAINS:
                            anchors += 1
            except Exception as e:
                logger.debug(f"Error processing source in market_probe: {e}")
                continue
        
        return MarketProbe(
            fresh=len(fresh),
            total=len(results or []),
            unique_domains=len(counts),
            anchors=anchors,
            domain_counts=counts
        )
    except Exception as e:
        logger.warning(f"Market probe failed: {e}")
        return MarketProbe(fresh=0, total=0, unique_domains=0, anchors=0, domain_counts={})


def thesis_probe(query: str, agent) -> ThesisProbe:
    """
    Lightweight thesis fetch; checks for canonical anchors.
    
    Args:
        query: Search query
        agent: EnhancedSTIAgent instance
        
    Returns:
        ThesisProbe with canonical anchor metrics
    """
    try:
        # Try to find canonical sources using agent's methods
        # This is a lightweight check - we don't need full synthesis
        concepts = agent._decompose_theory_query(query) if hasattr(agent, '_decompose_theory_query') else [query]
        
        # Search for foundational sources (lightweight)
        foundational_days = getattr(STIConfig, 'THEORY_FOUNDATIONAL_DAYS_BACK', 365)
        foundational_sources = []
        
        if hasattr(agent, '_search_foundational_sources'):
            foundational_sources = agent._search_foundational_sources(
                concepts, foundational_days
            )
        
        # Check for canonical domains
        canonical_domains = getattr(STIConfig, 'THESIS_ANCHOR_DOMAINS', [
            'ieeexplore.ieee.org', 'dl.acm.org', 'link.springer.com', 
            'sciencedirect.com', 'jstor.org', 'arxiv.org'
        ])
        
        canonical_count = 0
        has_classics = False
        
        for source in foundational_sources[:8]:
            url = getattr(source, 'url', '')
            title = getattr(source, 'title', '').lower()
            
            # Check if from canonical domain
            domain = _domain(url)
            if any(cd in domain for cd in canonical_domains):
                canonical_count += 1
            
            # Check for classic papers
            classic_indicators = ['shannon', 'granovetter', 'vapnik', 'turing', 
                                'von neumann', 'nash', 'bayes']
            if any(indicator in title for indicator in classic_indicators):
                has_classics = True
        
        return ThesisProbe(
            canonical=canonical_count,
            has_classics=has_classics
        )
    except Exception as e:
        logger.warning(f"Thesis probe failed: {e}")
        return ThesisProbe(canonical=0, has_classics=False)


def score_market(mp: MarketProbe) -> float:
    """
    Score market probe on 0-1 scale.
    
    Factors:
    - Fresh ratio (50%): How many sources are in the time window
    - Domain independence (30%): How many unique domains
    - Anchor presence (20%): Presence of wire service anchors
    """
    if mp.total == 0:
        return 0.0
    
    # Fresh ratio
    fresh_ratio = mp.fresh / mp.total if mp.total > 0 else 0.0
    
    # Domain independence (normalize by fresh count)
    domain_ind = mp.unique_domains / max(1, mp.fresh)
    
    # Anchor fraction
    anchor_frac = mp.anchors / max(1, mp.fresh)
    
    # Blend with pragmatic weights
    score = 0.5 * fresh_ratio + 0.3 * domain_ind + 0.2 * anchor_frac
    
    return round(min(max(score, 0.0), 1.0), 3)


def decide_route_with_band(
    query: str, 
    days: int, 
    agent,
    force: str = "auto", 
    band: float = 0.12
) -> Tuple[str, dict]:
    """
    Decide route (market/thesis/blend) with explicit rationale.
    
    Args:
        query: Search query
        days: Days to look back
        agent: EnhancedSTIAgent instance
        force: Force route ("market", "thesis", or "auto")
        band: Ambiguity band for blend mode (default 0.12 = 12%)
        
    Returns:
        Tuple of (route, rationale_dict)
    """
    if force in {"market", "thesis"}:
        return force, {
            "reason": "forced",
            "band": band,
            "route": force
        }
    
    # Run probes
    mp = market_probe(query, days, agent)
    tp = thesis_probe(query, agent)
    mscore = score_market(mp)
    
    high = MARKET_OK
    low = THESIS_OK
    
    # Movable "band" keeps UX implicit but handles ambiguity
    if (low < mscore < high) and ((high - mscore) <= band or (mscore - low) <= band):
        route = "blend"
    elif mscore >= high:
        route = "market"
    else:
        route = "thesis"
    
    rationale = {
        "route": route,
        "market_score": mscore,
        "fresh": mp.fresh,
        "total": mp.total,
        "unique_domains": mp.unique_domains,
        "anchors": mp.anchors,
        "domain_counts": mp.domain_counts,
        "canonical": tp.canonical,
        "classics": tp.has_classics,
        "band": band,
        "thresholds": {"high": high, "low": low}
    }
    
    return route, rationale


def run_market(query: str, days: int, rationale: dict, agent, shallow: bool = False) -> dict:
    """
    Execute market report generation.
    
    Args:
        query: Search query
        days: Days to look back
        rationale: Route rationale dict
        agent: EnhancedSTIAgent instance
        shallow: If True, generate lightweight version for blend
        
    Returns:
        Report dict (compatible with Report model)
    """
    # Force market-path by passing force_intent="market"
    # This ensures market-path is used even if market sources don't pass adequacy check
    markdown_report, json_ld_artifact, run_summary = agent.search(
        query=query,
        days_back=days,
        seed=42,
        budget_advanced=0,
        force_intent="market"
    )
    
    # Convert to report dict format
    from final_analyst_agent import _parse_markdown_sections, _extract_sources_from_jsonld
    
    sections = _parse_markdown_sections(markdown_report)
    exec_summary = sections[0].get("md", "")[:500] if sections else ""
    
    confidence_score = run_summary.get("metrics", {}).get("confidence", 0.0)
    if not confidence_score:
        confidence_score = json_ld_artifact.get("aggregateRating", {}).get("ratingValue", 0.0)
    
    return {
        "query": query,
        "path": "market",
        "exec_summary_md": exec_summary,
        "sections": sections,
        "confidence": {
            "score": float(confidence_score) if confidence_score else 0.0,
            "breakdown": run_summary.get("confidence_breakdown", {})
        },
        "sources": _extract_sources_from_jsonld(json_ld_artifact),
        "metadata": {
            **rationale,
            "intent": "market",
            "days_back": days,
            "run_summary": run_summary
        }
    }


def run_thesis(query: str, rationale: dict, agent, shallow: bool = False) -> dict:
    """
    Execute thesis report generation.
    
    Args:
        query: Search query
        rationale: Route rationale dict
        agent: EnhancedSTIAgent instance
        shallow: If True, generate lightweight version for blend
        
    Returns:
        Report dict (compatible with Report model)
    """
    # For thesis, use longer days_back to allow foundational sources
    days_back = 90 if not shallow else 30
    
    # Call agent.search() which will route to thesis path
    markdown_report, json_ld_artifact, run_summary = agent.search(
        query=query,
        days_back=days_back,
        seed=42,
        budget_advanced=10000 if not shallow else 0
    )
    
    # Convert to report dict format
    from final_analyst_agent import _parse_markdown_sections, _extract_sources_from_jsonld
    
    sections = _parse_markdown_sections(markdown_report)
    exec_summary = sections[0].get("md", "")[:500] if sections else ""
    
    confidence_score = run_summary.get("metrics", {}).get("confidence", 0.0)
    if not confidence_score:
        confidence_score = json_ld_artifact.get("aggregateRating", {}).get("ratingValue", 0.0)
    
    return {
        "query": query,
        "path": "thesis",
        "exec_summary_md": exec_summary,
        "sections": sections,
        "confidence": {
            "score": float(confidence_score) if confidence_score else 0.0,
            "breakdown": run_summary.get("confidence_breakdown", {})
        },
        "sources": _extract_sources_from_jsonld(json_ld_artifact),
        "metadata": {
            **rationale,
            "intent": "theory",
            "days_back": days_back,
            "run_summary": run_summary
        }
    }


def compose_blend(market: dict, thesis: dict, rationale: dict) -> dict:
    """
    Compose blend report from market and thesis components.
    
    Args:
        market: Market report dict
        thesis: Thesis report dict
        rationale: Route rationale dict
        
    Returns:
        Merged report dict
    """
    from blend import merge_market_and_thesis
    return merge_market_and_thesis(market, thesis, rationale)


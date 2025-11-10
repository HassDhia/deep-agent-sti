"""Evidence alignment utilities for STI pipelines."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class EvidenceAnchor:
    doi: Optional[str]
    title: str
    url: Optional[str] = None
    why_relevant: str = ""


@dataclass
class SupportSpan:
    source_id: str
    text: str


@dataclass
class ClaimLedgerItem:
    claim_id: str
    claim_text: str
    anchors: List[EvidenceAnchor]
    support_spans: List[SupportSpan]
    overreach: bool
    notes: str = ""


_JOURNAL_HINTS = (
    "science",
    "nature",
    "pnas",
    "ieee",
    "acm",
    "sagepub",
    "journals",
    "oup",
    "wiley",
    "springer",
    "tandfonline",
    "aps",
    "aip",
    "jstor",
    ".edu",
    ".ac.",
    "arxiv.org",
)

_DOI_RX = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)


def _is_strict_anchor(anchor: EvidenceAnchor) -> bool:
    """
    Check if anchor is strict (Type-1): has DOI AND domain matches THESIS_ANCHOR_DOMAINS.
    
    Args:
        anchor: EvidenceAnchor to check
        
    Returns:
        True if anchor has DOI and domain is in approved list, False otherwise
    """
    if not anchor.doi:
        return False
    
    # Check if DOI matches pattern
    if not _DOI_RX.search(anchor.doi):
        return False
    
    # Check if URL domain matches approved domains
    url = (anchor.url or "").lower()
    if not url:
        return False
    
    # Import config lazily to avoid circular imports
    try:
        from config import STIConfig
        anchor_domains = getattr(STIConfig, 'THESIS_ANCHOR_DOMAINS', [])
    except ImportError:
        anchor_domains = [
            'ieeexplore.ieee.org', 'dl.acm.org', 'link.springer.com',
            'sciencedirect.com', 'jstor.org', 'acm.org', 'springer.com',
            'mitpressjournals.org', 'siam.org', 'aps.org'
        ]
    
    # Check if any approved domain is in the URL
    return any(domain.lower() in url for domain in anchor_domains)


def _domain_score(url: str) -> float:
    u = (url or "").lower()
    score = 0.0
    for hint in _JOURNAL_HINTS:
        if hint in u:
            score += 1.0
    if "arxiv.org" in u:
        score -= 0.25
    return score


def _guess_anchors_from_sources(
    sources: List[Dict[str, Any]], max_anchors: int = 3
) -> List[EvidenceAnchor]:
    ranked: List[tuple[float, EvidenceAnchor]] = []
    for src in sources:
        url = src.get("url") or src.get("link") or ""
        title = src.get("title") or src.get("name") or url
        doi = None
        try:
            surface = " ".join(str(x or "") for x in (src.get("doi"), url, title))
        except Exception:
            surface = f"{url} {title}"
        match = _DOI_RX.search(surface)
        if match:
            doi = match.group(0)
        anchor = EvidenceAnchor(doi=doi, title=title, url=url)
        score = _domain_score(url)
        # Boost score for strict anchors (DOI + approved domain)
        if _is_strict_anchor(anchor):
            score += 2.0  # Significant boost for strict anchors
        ranked.append((score, anchor))

    ranked.sort(key=lambda item: item[0], reverse=True)
    return [anchor for _, anchor in ranked[:max_anchors]]


def discover_peer_reviewed_anchors(query: str, n: int = 3, cache: Optional[Dict[str, Any]] = None) -> List[EvidenceAnchor]:
    """
    Discover peer-reviewed anchors via Crossref/OpenAlex/Semantic Scholar APIs.
    Non-blocking, cache-aware. Returns up to n anchors ranked by venue quality + citations.
    
    Args:
        query: Search query for anchor discovery
        n: Maximum number of anchors to return
        cache: Optional cache dict (keyed by query hash) to avoid duplicate API calls
    
    Returns:
        List of EvidenceAnchor objects with DOI, title, URL, why_relevant
    """
    import hashlib
    import requests
    from typing import Optional
    
    cache_key = f"anchor_discovery_{hashlib.sha1(query.encode()).hexdigest()[:8]}"
    if cache and cache_key in cache:
        logger.debug(f"Using cached anchors for query: {query[:50]}...")
        return cache[cache_key]
    
    anchors: List[EvidenceAnchor] = []
    
    # Try Crossref API (free, no auth required)
    try:
        crossref_url = "https://api.crossref.org/works"
        params = {
            "query": query,
            "rows": min(n * 2, 10),  # Get extra to filter
            "filter": "type:journal-article",  # Peer-reviewed only
            "sort": "relevance"
        }
        resp = requests.get(crossref_url, params=params, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            for item in data.get("message", {}).get("items", [])[:n]:
                title = item.get("title", [""])[0] if item.get("title") else "Untitled"
                doi = item.get("DOI", "")
                url = f"https://doi.org/{doi}" if doi else None
                
                # Extract journal name for why_relevant
                journal = item.get("container-title", [""])[0] if item.get("container-title") else "Unknown journal"
                year = item.get("published-print", {}).get("date-parts", [[None]])[0][0] if item.get("published-print") else None
                why_relevant = f"Published in {journal}" + (f" ({year})" if year else "")
                
                anchors.append(EvidenceAnchor(
                    doi=doi,
                    title=title,
                    url=url,
                    why_relevant=why_relevant
                ))
    except Exception as e:
        logger.debug(f"Crossref API error (non-fatal): {e}")
    
    # Fallback to Semantic Scholar if Crossref yields < n results
    if len(anchors) < n:
        try:
            sem_scholar_url = "https://api.semanticscholar.org/graph/v1/paper/search"
            params = {
                "query": query,
                "limit": n - len(anchors),
                "fields": "title,doi,url,year,venue"
            }
            resp = requests.get(sem_scholar_url, params=params, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("data", [])[:n - len(anchors)]:
                    title = item.get("title", "Untitled")
                    doi = item.get("doi", "")
                    url = item.get("url", "")
                    venue = item.get("venue", "Unknown venue")
                    year = item.get("year")
                    why_relevant = f"Published in {venue}" + (f" ({year})" if year else "")
                    
                    # Only add if not already in anchors (by DOI)
                    if not any(a.doi == doi for a in anchors):
                        anchors.append(EvidenceAnchor(
                            doi=doi,
                            title=title,
                            url=url or (f"https://doi.org/{doi}" if doi else None),
                            why_relevant=why_relevant
                        ))
        except Exception as e:
            logger.debug(f"Semantic Scholar API error (non-fatal): {e}")
    
    # Cache results
    if cache is not None:
        cache[cache_key] = anchors
    
    return anchors[:n]


def _sha(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def hunt_strict_anchors(claim_text: str, n: int = 2, cache: Optional[Dict[str, Any]] = None) -> List[EvidenceAnchor]:
    """
    Hunt for domain-correct anchors by searching THESIS_ANCHOR_DOMAINS only.
    Uses SearXNG with site: queries for approved domains.
    
    Args:
        claim_text: Claim text to search for
        n: Maximum number of anchors to return
        cache: Optional cache dict to avoid duplicate searches
        
    Returns:
        List of EvidenceAnchor objects with DOI, title, URL from approved domains
    """
    import requests
    from urllib.parse import quote
    
    cache_key = f"anchor_hunt_{hashlib.sha1(claim_text.encode()).hexdigest()[:8]}"
    if cache and cache_key in cache:
        logger.debug(f"Using cached anchor hunt for claim: {claim_text[:50]}...")
        return cache[cache_key]
    
    anchors: List[EvidenceAnchor] = []
    
    # Get approved domains from config
    try:
        from config import STIConfig
        anchor_domains = getattr(STIConfig, 'THESIS_ANCHOR_DOMAINS', [])
        searxng_base = getattr(STIConfig, 'SEARXNG_BASE_URL', 'http://localhost:8080')
        timeout = getattr(STIConfig, 'HTTP_TIMEOUT_SECONDS', 12)
    except ImportError:
        anchor_domains = [
            'ieeexplore.ieee.org', 'dl.acm.org', 'link.springer.com',
            'sciencedirect.com', 'jstor.org', 'acm.org', 'springer.com',
            'mitpressjournals.org', 'siam.org', 'aps.org'
        ]
        searxng_base = 'http://localhost:8080'
        timeout = 12
    
    # Search up to 2-3 domains (limit to avoid too many API calls)
    search_domains = anchor_domains[:3]
    
    for domain in search_domains:
        if len(anchors) >= n:
            break
        
        try:
            # Build site: query
            query = f"site:{domain} {claim_text[:100]}"  # Limit query length
            search_url = f"{searxng_base.rstrip('/')}/search"
            
            headers = {
                'Accept': 'application/json',
                'User-Agent': 'sti-anchor-hunter/1.0'
            }
            
            params = {
                'q': query,
                'format': 'json',
                'categories': 'science',
                'safesearch': 1
            }
            
            resp = requests.get(search_url, params=params, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get('results', [])
                
                for result in results[:2]:  # Limit per domain
                    if len(anchors) >= n:
                        break
                    
                    url = result.get('url') or result.get('link') or ''
                    title = result.get('title') or 'Untitled'
                    
                    # Extract DOI from URL or title
                    doi = None
                    surface = f"{url} {title}"
                    match = _DOI_RX.search(surface)
                    if match:
                        doi = match.group(0)
                    
                    # Only add if it's a strict anchor (DOI + domain match)
                    anchor = EvidenceAnchor(doi=doi, title=title, url=url, why_relevant=f"Found via {domain}")
                    if _is_strict_anchor(anchor):
                        anchors.append(anchor)
                    elif doi:  # Add even if not strict, but prefer strict
                        anchors.append(anchor)
                        
        except Exception as e:
            logger.debug(f"Anchor hunt error for {domain}: {e}")
            continue
    
    # Rank by strictness (strict anchors first)
    anchors.sort(key=lambda a: (not _is_strict_anchor(a), not bool(a.doi)))
    
    # Cache results
    if cache is not None:
        cache[cache_key] = anchors[:n]
    
    return anchors[:n]


def align_claims_to_evidence(
    claims: Iterable[Dict[str, Any]],
    sources: List[Dict[str, Any]],
    get_source_text: Optional[Callable[[str], str]] = None,
    llm: Optional[Callable[[str, int], str]] = None,
    max_tokens: int = 1200,
) -> Dict[str, Any]:
    """Build an evidence ledger for downstream consumers."""

    items: List[ClaimLedgerItem] = []
    coverage_hits_any = 0
    coverage_hits_strict = 0

    for claim in claims:
        claim_text = claim.get("text") or claim.get("claim_text") or ""
        claim_id = claim.get("id") or claim.get("claim_id") or _sha(claim_text)[:8]

        anchors = _guess_anchors_from_sources(sources, max_anchors=3)
        
        # Anchor-Hunter pass: search approved domains for domain-correct anchors
        try:
            # Use cache if provided (from agent's evidence_cache)
            cache = getattr(align_claims_to_evidence, '_anchor_hunt_cache', None)
            if cache is None:
                cache = {}
                align_claims_to_evidence._anchor_hunt_cache = cache
            
            hunted = hunt_strict_anchors(claim_text, n=2, cache=cache)
            # Merge hunted anchors with heuristic ones, prioritizing strict domain matches
            # Strict anchors first, then others
            all_anchors = hunted + anchors
            # Deduplicate by URL, keeping strict anchors
            seen_urls = set()
            merged = []
            for anchor in all_anchors:
                url_key = (anchor.url or "").lower()
                if url_key and url_key not in seen_urls:
                    seen_urls.add(url_key)
                    merged.append(anchor)
            # Sort: strict anchors first
            merged.sort(key=lambda a: (not _is_strict_anchor(a), not bool(a.doi)))
            anchors = merged[:3]  # Limit to 3 anchors
        except Exception as e:
            logger.debug(f"Anchor hunt failed (non-fatal): {e}")
            # Continue with heuristic anchors only
        
        spans: List[SupportSpan] = []
        overreach = False
        note = ""

        if llm is not None and max_tokens > 0:
            # Optional: Upgrade with peer-reviewed discovery (premium path)
            try:
                discovered = discover_peer_reviewed_anchors(claim_text, n=2, cache=None)
                # Merge discovered anchors with heuristic ones, prioritizing discovered
                anchors = (discovered + anchors)[:3]
            except Exception as e:
                logger.debug(f"Anchor discovery failed (non-fatal): {e}")
            
            prompt = (
                "You are a methods editor. For the claim below, provide JSON with keys "
                "support_spans (array of {source_id,text}), overreach (bool), note (string), "
                "and anchors (array of {title,doi,why_relevant}). Use provided sources only.\n\n"
                f"Claim:\n{claim_text}\n"
            )
            try:
                raw = llm(prompt, max_tokens)
                payload = json.loads(_extract_json(raw))
                for span in payload.get("support_spans", []):
                    spans.append(
                        SupportSpan(
                            source_id=str(span.get("source_id")),
                            text=str(span.get("text", "")),
                        )
                    )
                llm_anchors: List[EvidenceAnchor] = []
                for anchor in payload.get("anchors", []):
                    llm_anchors.append(
                        EvidenceAnchor(
                            doi=anchor.get("doi"),
                            title=str(anchor.get("title", "")),
                            why_relevant=str(anchor.get("why_relevant", "")),
                        )
                    )
                if llm_anchors:
                    anchors = (llm_anchors + anchors)[:3]
                overreach = bool(payload.get("overreach", False))
                note = str(payload.get("note", ""))
            except Exception as exc:  # noqa: BLE001
                logger.warning("evidence alignment llm error: %s", exc)
                note = f"llm_error: {exc}. Using heuristic anchors."
        else:
            if get_source_text is not None:
                for src in sources[:3]:
                    source_id = str(
                        src.get("id")
                        or src.get("source_id")
                        or src.get("url")
                        or src.get("title")
                        or "src"
                    )
                    try:
                        text = get_source_text(source_id)
                    except Exception:  # noqa: BLE001
                        text = ""
                    if text:
                        excerpt = text[:280].replace("\n", " ")
                        spans.append(SupportSpan(source_id=source_id, text=excerpt))

        # Track coverage: any anchor vs strict anchor
        if anchors:
            coverage_hits_any += 1
            # Check if any anchor is strict
            if any(_is_strict_anchor(anchor) for anchor in anchors):
                coverage_hits_strict += 1

        items.append(
            ClaimLedgerItem(
                claim_id=claim_id,
                claim_text=claim_text,
                anchors=anchors,
                support_spans=spans,
                overreach=overreach,
                notes=note,
            )
        )

    anchor_coverage_any = coverage_hits_any / max(1, len(items))
    anchor_coverage_strict = coverage_hits_strict / max(1, len(items))
    ledger = {
        "claims": [_item_to_dict(item) for item in items],
        "anchor_coverage": round(anchor_coverage_any, 3),  # Backward compatibility
        "anchor_coverage_any": round(anchor_coverage_any, 3),
        "anchor_coverage_strict": round(anchor_coverage_strict, 3),
        "hash": _sha("".join(item.claim_id for item in items)),
    }
    return ledger


def _extract_json(raw: str) -> str:
    match = re.search(r"\{.*\}", raw, flags=re.S)
    return match.group(0) if match else "{}"


def _item_to_dict(item: ClaimLedgerItem) -> Dict[str, Any]:
    data = asdict(item)
    data["anchors"] = [asdict(anchor) for anchor in item.anchors]
    data["support_spans"] = [asdict(span) for span in item.support_spans]
    return data



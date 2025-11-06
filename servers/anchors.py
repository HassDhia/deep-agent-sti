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
        ranked.append((
            _domain_score(url),
            EvidenceAnchor(doi=doi, title=title, url=url),
        ))

    ranked.sort(key=lambda item: item[0], reverse=True)
    return [anchor for _, anchor in ranked[:max_anchors]]


def _sha(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def align_claims_to_evidence(
    claims: Iterable[Dict[str, Any]],
    sources: List[Dict[str, Any]],
    get_source_text: Optional[Callable[[str], str]] = None,
    llm: Optional[Callable[[str, int], str]] = None,
    max_tokens: int = 1200,
) -> Dict[str, Any]:
    """Build an evidence ledger for downstream consumers."""

    items: List[ClaimLedgerItem] = []
    coverage_hits = 0

    for claim in claims:
        claim_text = claim.get("text") or claim.get("claim_text") or ""
        claim_id = claim.get("id") or claim.get("claim_id") or _sha(claim_text)[:8]

        anchors = _guess_anchors_from_sources(sources, max_anchors=3)
        spans: List[SupportSpan] = []
        overreach = False
        note = ""

        if llm is not None and max_tokens > 0:
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

        if anchors:
            coverage_hits += 1

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

    anchor_coverage = coverage_hits / max(1, len(items))
    ledger = {
        "claims": [_item_to_dict(item) for item in items],
        "anchor_coverage": round(anchor_coverage, 3),
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



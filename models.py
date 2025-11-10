from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator


class SourceModel(BaseModel):
    id: int
    title: str
    url: str
    publisher: str
    date: str  # YYYY-MM-DD
    credibility: float

    @field_validator("date")
    def validate_date_format(cls, v: str) -> str:
        datetime.strptime(v, "%Y-%m-%d")
        return v
    
    @field_validator("url")
    def validate_url(cls, v: str) -> str:
        """Strict URL validation - reject empty, placeholder, or malformed URLs"""
        if not v:
            raise ValueError("URL cannot be empty")
        
        if v == "#" or "placeholder" in v.lower():
            raise ValueError(f"Placeholder URL not allowed: {v}")
        
        if len(v) < 10:
            raise ValueError(f"URL too short (likely invalid): {v}")
        
        if not (v.startswith('http://') or v.startswith('https://')):
            raise ValueError(f"URL must start with http:// or https://: {v}")
        
        # Validate URL structure
        try:
            from urllib.parse import urlparse
            parsed = urlparse(v)
            if not parsed.netloc:
                raise ValueError(f"URL missing domain: {v}")
        except Exception as e:
            raise ValueError(f"Malformed URL: {v} - {str(e)}")
        
        return v


class SignalModel(BaseModel):
    claim: str
    strength: float = Field(ge=0.0, le=1.0)
    impact: str
    direction: str
    citations: List[int] = Field(default_factory=list)


class ActionModel(BaseModel):
    title: str
    owner: str
    due: str  # YYYY-MM-DD

    @field_validator("due")
    def validate_due_format(cls, v: str) -> str:
        datetime.strptime(v, "%Y-%m-%d")
        return v


class ReportModel(BaseModel):
    title: str
    query: str
    start_date: str  # YYYY-MM-DD
    end_date: str    # YYYY-MM-DD
    confidence: float = Field(ge=0.0, le=1.0)
    sources: List[SourceModel] = Field(default_factory=list)
    signals: List[SignalModel] = Field(default_factory=list)
    actions: List[ActionModel] = Field(default_factory=list)
    word_count: Optional[int] = None
    sources_count: Optional[int] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("start_date", "end_date")
    def validate_dates(cls, v: str) -> str:
        datetime.strptime(v, "%Y-%m-%d")
        return v

    @model_validator(mode="after")
    def validate_window_and_counts(self) -> "ReportModel":
        start = datetime.strptime(self.start_date, "%Y-%m-%d")
        end = datetime.strptime(self.end_date, "%Y-%m-%d")
        for src in self.sources:
            d = datetime.strptime(src.date, "%Y-%m-%d")
            if not (start <= d <= end):
                # Allow out-of-window foundational academic sources for theory intent
                allow_foundational = bool(self.metadata.get('allow_foundational_out_of_window', False))
                intent = self.metadata.get('intent')
                canonical_hosts = set(self.metadata.get('canonical_hosts', []))
                foundational_urls = set(self.metadata.get('foundational_urls', []))
                if allow_foundational and intent == 'theory':
                    from urllib.parse import urlparse
                    host = urlparse(src.url).netloc
                    if src.url in foundational_urls or host in canonical_hosts:
                        continue
                raise ValueError(f"Source '{src.title}' outside window: {src.date}")

        # Ensure counts reflect actual values
        self.sources_count = len(self.sources)
        return self


class SourceRelevanceScore(BaseModel):
    """Pydantic model for structured source relevance scoring output"""
    source_id: int
    relevance_score: float = Field(ge=0.0, le=1.0, description="Relevance score between 0.0 and 1.0")
    relevance_reason: str = Field(description="Brief explanation of why this source is or isn't relevant to the title")
    is_relevant: bool = Field(description="Whether the source meets the relevance threshold")


class TitleRefinement(BaseModel):
    """Pydantic model for structured title refinement output"""
    refined_title: str = Field(description="The refined title based on actual content found")
    alignment_score: float = Field(ge=0.0, le=1.0, description="How well the refined title aligns with original query")
    refinement_reason: str = Field(description="Explanation of why the title was refined")
    should_update: bool = Field(description="Whether the title should be updated based on content")


class QueryIntent(BaseModel):
    """Pydantic model for query intent classification"""
    intent: str = Field(description="Classified intent: 'theory' or 'market'")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in the classification")
    reasoning: str = Field(description="Brief explanation of why this intent was chosen")


class QueryDomain(BaseModel):
    """Pydantic model for query domain extraction"""
    primary_domain: str = Field(description="Primary domain/field (e.g., 'technology/artificial intelligence', 'healthcare/medicine', 'finance/economics')")
    domain_keywords: List[str] = Field(description="Key terms that indicate this domain")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in domain identification")


class SearchQueries(BaseModel):
    """Pydantic model for LLM-generated search queries"""
    queries: List[str] = Field(description="List of diverse search queries optimized for academic source discovery")


class RerankScore(BaseModel):
    source_id: int
    score: float = Field(ge=0.0, le=1.0)
    rationale: str

class ConceptList(BaseModel):
    concepts: List[str]

class AnchorList(BaseModel):
    anchors: List[str]

class RetrievedSource(BaseModel):
    id: int
    url: str
    title: str
    publisher: str
    date: str
    source_class: str = Field(description="FOUNDATIONAL or RECENT")

class ThesisOutline(BaseModel):
    sections: List[str]
    claims_by_section: Dict[str, List[str]] = Field(default_factory=dict)

class ThesisDraft(BaseModel):
    markdown: str
    cited_source_ids: List[int] = Field(default_factory=list)

class ThesisCritique(BaseModel):
    alignment: float = Field(ge=0.0, le=1.0)
    theory_depth: float = Field(ge=0.0, le=1.0)
    clarity: float = Field(ge=0.0, le=1.0)
    repair_action: Optional[str] = Field(description="none|expand_anchors|adjust_outline", default="none")

class SourceType(str, Enum):
    """Source type classification for thesis reports"""
    PEER_REVIEWED = "P"  # Peer-reviewed journals, standards, textbooks
    DOCTRINE = "D"       # Official doctrine, standards bodies
    ARXIV = "A"          # arXiv preprints, conference preprints
    OFFICIAL = "O"       # Official data, gov/standards bodies, audited filings
    GREY = "G"           # Industry whitepapers, reputable blogs, grey literature


class CEMRow(BaseModel):
    """Single row in Claim-Evidence-Method grid"""
    claim: str = Field(description="Theoretical claim (e.g., 'Consensus time ∝ 1/λ₂')")
    evidence: str = Field(description="Evidence supporting claim (source citations with type tags)")
    method: str = Field(description="Method for validation (proof/sim/empirical)")
    status: str = Field(description="Status: 'E cited; M pending' or similar")
    risk: str = Field(description="What fails if the claim is wrong", default="")
    test_id: str = Field(description="Cross-link to tests in Methods section", default="")

class CEMGrid(BaseModel):
    """Claim-Evidence-Method grid for thesis reports"""
    rows: List[CEMRow] = Field(description="List of CEM rows mapping claims to evidence")

class PublicationRubric(BaseModel):
    """Comprehensive rubric for thesis-path publication quality"""
    scope_clarity: float = Field(ge=0.0, le=10.0, description="Scope & Problem Clarity (10)")
    novelty: float = Field(ge=0.0, le=10.0, description="Novelty / Original Framing (10)")
    evidence_strength: float = Field(ge=0.0, le=20.0, description="Evidence Base Strength (20)")
    method_rigor: float = Field(ge=0.0, le=10.0, description="Method Rigor & Formalism (10)")
    reproducibility: float = Field(ge=0.0, le=10.0, description="Reproducibility & Transparency (10)")
    cross_domain: float = Field(ge=0.0, le=5.0, description="Cross-Domain Mapping (5)")
    falsifiability: float = Field(ge=0.0, le=10.0, description="Falsifiability & Predictions (10)")
    risks_limitations: float = Field(ge=0.0, le=5.0, description="Risks / Limitations (5)")
    writing_clarity: float = Field(ge=0.0, le=10.0, description="Writing Clarity & Structure (10)")
    publication_hygiene: float = Field(ge=0.0, le=10.0, description="Publication Hygiene (10)")
    
    @property
    def total_score(self) -> float:
        """Calculate total rubric score out of 100"""
        return (self.scope_clarity + self.novelty + self.evidence_strength + 
                self.method_rigor + self.reproducibility + self.cross_domain +
                self.falsifiability + self.risks_limitations + self.writing_clarity +
                self.publication_hygiene)


class AssumptionsLedgerRow(BaseModel):
    """Single row in Assumptions Ledger table"""
    assumption: str = Field(description="The assumption being made")
    rationale: str = Field(description="Why this assumption is reasonable")
    observable: str = Field(description="How to observe if assumption holds")
    trigger: str = Field(description="What triggers checking this assumption")
    fallback_delegation: str = Field(description="Fallback if assumption fails")
    scope: str = Field(description="Scope/limits of assumption")


class ThesisMetadata(BaseModel):
    """Front-matter metadata structure for thesis reports"""
    title: str
    date_range: str  # ISO start–ISO end format
    sources_count: int
    anchor_status: str = Field(description="Anchored|Anchor-Sparse|Anchor-Absent")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score using playbook formula")
    badges: Dict[str, float] = Field(default_factory=dict, description="alignment, theory_depth, clarity (0-10 scale)")
    rubric_score: float = Field(ge=0.0, le=100.0, description="Total rubric score out of 100")
    disclaimer: str = Field(default="Theory-first synthesis with CEM grid; see assumptions & validation plan.")


class AbstractionLayers(BaseModel):
    """Pydantic model for conceptual abstraction layers"""
    layers: Dict[str, List[str]] = Field(description="Dictionary mapping layer names (e.g., 'Layer 1: Specific', 'Layer 2: Domain') to lists of concepts/keywords")


class CanonicalPapers(BaseModel):
    """Pydantic model for canonical papers at each abstraction layer"""
    papers: Dict[str, List[str]] = Field(description="Dictionary mapping layer names to lists of canonical paper titles/authors")



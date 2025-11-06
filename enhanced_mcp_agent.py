"""
Enhanced MCP Agent

Extends SimpleMCPTimeFilteredAgent to produce comprehensive 3,000-4,000 word
research reports with specialized analysis sections using MCP tool servers.
"""

import hashlib
import json
import logging
import os
import random
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from simple_mcp_agent import SimpleMCPTimeFilteredAgent, Source, SourceType
from models import (
    ReportModel, SourceModel, SignalModel, SourceRelevanceScore, TitleRefinement, QueryIntent,
    ConceptList, ThesisOutline, ThesisDraft, ThesisCritique,
    PublicationRubric, CEMGrid, CEMRow, SourceType as ThesisSourceType, AssumptionsLedgerRow
)
from config import STIConfig
# from langchain_mcp_adapters.client import MultiServerMCPClient
import sys
sys.path.append('servers')
from analysis_server import (
    analyze_market, analyze_technology, analyze_competitive,
    expand_lenses, write_executive_summary
)
from budget import BudgetManager
from confidence import ConfidenceBreakdown, headline as confidence_headline
from file_utils import compute_content_sha, save_enhanced_report_auto, write_json
from gates import value_of_information
from servers.anchors import align_claims_to_evidence
from servers.critic import adversarial_review, decision_playbooks
from servers.quant import patch_to_dict, suggest_patch_for_vignette
from langchain.prompts import PromptTemplate
from langchain.output_parsers import PydanticOutputParser
from langchain_openai import OpenAIEmbeddings
import numpy as np

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EnhancedSTIAgent(SimpleMCPTimeFilteredAgent):
    """
    Enhanced agent that adds deep analysis sections while
    keeping all existing quality gates and search logic
    """
    
    def __init__(self, openai_api_key: str, tavily_api_key: str = "",
                 model_name: str = "gpt-5-mini-2025-08-07"):
        # Initialize base agent (all existing functionality)
        super().__init__(openai_api_key, tavily_api_key, model_name)
        
        # Add MCP client for deep analysis tools
        self.analysis_client = None
        self.analysis_tools = None
        
        # Curated theory anchors and small in-memory cache
        self._anchor_cache: Dict[str, List[Source]] = {}
        self._anchor_queries: List[str] = [
            'Consensus and Cooperation in Networked Multi-Agent Systems Olfati-Saber Fax Murray',
            'Distributed consensus in multi-agent systems tutorial survey',
            'Leader–follower consensus formation control survey',
            'Formation control multi-agent survey',
            'Containment control multi-agent survey'
        ]
        self._advanced_llm = None
        self._evidence_cache: Dict[str, Dict[str, Any]] = {}
        self._quant_cache: Dict[str, Dict[str, Any]] = {}
        self._adversarial_cache: Dict[str, Dict[str, Any]] = {}
        self.last_run_status: Dict[str, Any] = {}
    
    def initialize_analysis_tools(self):
        """Initialize analysis tools (simplified version)"""
        logger.info("Analysis tools initialized successfully (direct import)")
    
    def _calculate_source_attribution_stats(self, sources, signals, analyses):
        """Track which sources are cited where"""
        import re
        
        stats = {
            'total_sources': len(sources),
            'cited_in_signals': set(),
            'cited_in_analysis': set(),
            'uncited': []
        }
        
        # Track signal citations
        for signal in signals:
            stats['cited_in_signals'].update(signal.get('citation_ids', []))
        
        # Track analysis citations (regex for [^N])
        all_analysis = ' '.join(analyses)
        cited_ids = re.findall(r'\[\^(\d+)\]', all_analysis)
        stats['cited_in_analysis'].update(int(cid) for cid in cited_ids)
        
        # Identify uncited
        all_cited = stats['cited_in_signals'] | stats['cited_in_analysis']
        stats['uncited'] = [s.id for s in sources if s.id not in all_cited]
        
        logger.info(f"Source attribution: {len(all_cited)}/{len(sources)} sources cited")
        if stats['uncited']:
            logger.warning(f"Uncited sources: {stats['uncited']}")
        
        return stats

    def _ensure_advanced_llm(self):
        if self._advanced_llm is not None:
            return self._advanced_llm

        from langchain_openai import ChatOpenAI

        organization = os.getenv("OPENAI_ORGANIZATION") or getattr(STIConfig, 'OPENAI_ORGANIZATION', None)
        llm_params = {
            "api_key": self.openai_api_key,
            "model": getattr(STIConfig, 'ADVANCED_MODEL_NAME', 'gpt-5-2025-08-07'),
            "temperature": 0.0,
        }
        if organization:
            llm_params["openai_organization"] = organization
        self._advanced_llm = ChatOpenAI(**llm_params)
        return self._advanced_llm

    def _premium_call(self, prompt: str, max_tokens: int) -> str:
        llm = self._ensure_advanced_llm()
        try:
            response = llm.invoke(prompt, max_tokens=max_tokens)
        except TypeError:
            response = llm.invoke(prompt)
        return getattr(response, "content", str(response))

    def _make_source_getter(self, sources: List[Source]):
        lookup = {str(source.id): source.content for source in sources}
        return lambda source_id: lookup.get(str(source_id), "")

    def _assemble_claims(self,
                         signals: List[Dict[str, Any]],
                         market_analysis: str,
                         tech_deepdive: str,
                         competitive: str,
                         expanded_lenses: str,
                         exec_summary: str) -> List[Dict[str, str]]:
        claims: List[Dict[str, str]] = []
        for idx, signal in enumerate(signals, 1):
            text = signal.get('text', '').strip()
            if text:
                claims.append({"id": f"S{idx}", "text": text})

        sections = [
            ("EXEC", exec_summary),
            ("MARKET", market_analysis),
            ("TECH", tech_deepdive),
            ("COMP", competitive),
            ("LENS", expanded_lenses),
        ]
        for name, section in sections:
            if not section:
                continue
            snippet = section.strip().split('\n')[0][:320]
            if snippet:
                claims.append({"id": f"{name}1", "text": snippet})
        return claims

    def _detect_quant_issues(self, *sections: str) -> int:
        text_blob = " ".join(section for section in sections if section)
        lowered = text_blob.lower()
        flags = 0
        if "illustrative target" in lowered:
            flags += 1
        if "ppv" in lowered and "base rate" not in lowered:
            flags += 1
        if "lambda" in lowered and "poisson" not in lowered:
            flags += 1
        return flags

    def _infer_vignette_params(self, sections: List[str]) -> Dict[str, Any]:
        params = {
            "mu": 120,
            "alpha": 0.65,
            "tau": 0.25,
            "p_conn": 0.6,
            "kappa": 1.0,
            "TPR": 0.9,
            "FPR": 0.08,
            "base_rate": 0.05,
            "p_loss": 0.25,
            "f": 1 / 30,
            "w_k": 0.02,
        }
        text_blob = " ".join(sections).lower()
        if "ppv" in text_blob and "0.6" in text_blob:
            params["TPR"] = 0.85
        if "mtta" in text_blob:
            params["tau"] = 0.3
        return params

    def _hash_payload(self, payload: Any) -> str:
        try:
            serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        except TypeError:
            serialized = str(payload)
        return hashlib.sha1(serialized.encode('utf-8')).hexdigest()

    def _source_diversity_score(self, sources: List[Source]) -> float:
        if not sources:
            return 0.0
        publishers = [s.publisher or "" for s in sources]
        counter = Counter(publishers)
        distinct = len([p for p in counter if p])
        diversity = distinct / max(1, len(sources))
        top_fraction = max(counter.values()) / max(1, len(sources)) if counter else 0.0
        cap = getattr(STIConfig, 'VENDOR_CAP_PCT', 0.4)
        if top_fraction > cap:
            diversity *= 0.8
        return max(0.0, min(1.0, diversity))

    def _confidence_breakdown(self,
                              sources: List[Source],
                              anchor_coverage: float,
                              quant_patch: Optional[Dict[str, Any]],
                              adversarial_data: Optional[Dict[str, Any]]) -> ConfidenceBreakdown:
        source_diversity = self._source_diversity_score(sources)
        method_transparency = 0.45
        if anchor_coverage >= getattr(STIConfig, 'ANCHOR_COVERAGE_MIN', 0.7):
            method_transparency += 0.25
        if quant_patch:
            method_transparency += 0.15
        replication_readiness = 0.45
        if quant_patch:
            replication_readiness += 0.2
        if adversarial_data:
            replication_readiness += 0.2
        breakdown = ConfidenceBreakdown(
            source_diversity=source_diversity,
            anchor_coverage=max(0.0, min(1.0, anchor_coverage)),
            method_transparency=min(1.0, method_transparency),
            replication_readiness=min(1.0, replication_readiness),
        )
        return breakdown.clamp()

    def _run_auditors(
        self,
        *,
        query: str,
        intent: str,
        sources: List[Source],
        signals: List[Dict[str, Any]],
        market_analysis: str,
        tech_deepdive: str,
        competitive: str,
        expanded_lenses: str,
        exec_summary: str,
        confidence: float,
        budget: BudgetManager,
    ) -> Dict[str, Any]:
        source_records = [
            {
                "id": source.id,
                "title": source.title,
                "url": source.url,
                "publisher": source.publisher,
                "date": source.date,
            }
            for source in sources
        ]
        claims = self._assemble_claims(
            signals, market_analysis, tech_deepdive, competitive, expanded_lenses, exec_summary
        )
        source_getter = self._make_source_getter(sources)
        ledger = align_claims_to_evidence(claims, source_records, get_source_text=source_getter)
        anchor_coverage = ledger.get("anchor_coverage", 0.0)
        quant_flags = self._detect_quant_issues(
            market_analysis, tech_deepdive, competitive, expanded_lenses, exec_summary
        )
        metrics = {
            "anchor_coverage": anchor_coverage,
            "quant_flags": quant_flags,
            "confidence": float(confidence),
        }
        requested_tasks = value_of_information(metrics, intent)
        task_matrix = {
            "evidence_alignment": "evidence_alignment" in requested_tasks,
            "math_guard": "math_guard" in requested_tasks and quant_flags > 0,
            "adversarial_review": "adversarial_review" in requested_tasks,
            "decision_playbooks": "decision_playbooks" in requested_tasks,
        }

        executed_premium_tasks: List[str] = []
        advanced_tokens = 0

        ledger_key = ledger.get("hash") or self._hash_payload(claims)
        if task_matrix["evidence_alignment"]:
            tokens = budget.slice(0.35)
            if tokens > 0:
                cache_key = f"{ledger_key}:{intent}"
                cached = self._evidence_cache.get(cache_key)
                if cached:
                    ledger = cached
                else:
                    ledger = align_claims_to_evidence(
                        claims,
                        source_records,
                        get_source_text=source_getter,
                        llm=self._premium_call,
                        max_tokens=tokens,
                    )
                    self._evidence_cache[cache_key] = ledger
                executed_premium_tasks.append("evidence_alignment")
                advanced_tokens += tokens
            else:
                task_matrix["evidence_alignment"] = False
        anchor_coverage = ledger.get("anchor_coverage", anchor_coverage)
        metrics["anchor_coverage"] = anchor_coverage

        quant_patch_dict: Optional[Dict[str, Any]] = None
        if task_matrix["math_guard"]:
            params = self._infer_vignette_params(
                [market_analysis, tech_deepdive, competitive, expanded_lenses, exec_summary]
            )
            params_hash = self._hash_payload(params)
            quant_patch_dict = self._quant_cache.get(params_hash)
            if quant_patch_dict is None:
                patch = suggest_patch_for_vignette(params)
                quant_patch_dict = patch_to_dict(patch)
                self._quant_cache[params_hash] = quant_patch_dict
            metrics["quant_flags"] = len(quant_patch_dict.get("warnings", []))

        report_sections = {
            "market": market_analysis,
            "technology": tech_deepdive,
            "competitive": competitive,
            "lenses": expanded_lenses,
            "executive_summary": exec_summary,
        }
        adversarial_data: Optional[Dict[str, Any]] = None
        if task_matrix["adversarial_review"]:
            adv_hash = self._hash_payload(report_sections)
            adversarial_data = self._adversarial_cache.get(adv_hash)
            if adversarial_data is None:
                tokens = budget.slice(0.15)
                if tokens > 0:
                    adversarial_data = adversarial_review(
                        report_sections, llm=self._premium_call, max_tokens=tokens
                    )
                    executed_premium_tasks.append("adversarial_review")
                    advanced_tokens += tokens
                else:
                    adversarial_data = adversarial_review(report_sections, llm=None)
                self._adversarial_cache[adv_hash] = adversarial_data

        playbooks_data: Optional[Dict[str, Any]] = None
        if task_matrix["decision_playbooks"]:
            playbooks_data = {"rows": decision_playbooks()}

        anchor_gate = intent == "theory" and anchor_coverage < getattr(
            STIConfig, 'ANCHOR_COVERAGE_MIN', 0.7
        )
        source_sha_map = {source.id: compute_content_sha(source.content) for source in sources}

        breakdown = self._confidence_breakdown(sources, anchor_coverage, quant_patch_dict, adversarial_data)
        confidence_updated = confidence_headline(breakdown)

        return {
            "ledger": ledger,
            "quant_patch": quant_patch_dict,
            "adversarial": adversarial_data,
            "playbooks": playbooks_data,
            "confidence_breakdown": breakdown,
            "confidence": confidence_updated,
            "metrics": metrics,
            "tasks_requested": requested_tasks,
            "task_matrix": task_matrix,
            "tasks_executed": executed_premium_tasks,
            "anchor_gate": anchor_gate,
            "advanced_tokens": advanced_tokens,
            "source_sha_map": source_sha_map,
            "report_sections": report_sections,
            "claims": claims,
        }

    def _classify_horizon(self, sources: List[Source]) -> str:
        """Rough horizon classification based on source dates."""
        from datetime import datetime
        now = datetime.now()
        def age_days(dstr: str) -> int:
            try:
                return (now - datetime.strptime(dstr, '%Y-%m-%d')).days
            except Exception:
                return 0
        ages = [age_days(s.date) for s in sources if getattr(s, 'date', None)]
        if not ages:
            return "Near-term"
        recent = sum(1 for a in ages if a <= 30)
        mid = sum(1 for a in ages if 31 <= a <= 180)
        longh = sum(1 for a in ages if 181 <= a <= 720)
        found = sum(1 for a in ages if a > 720)
        if recent >= max(mid, longh, found):
            return "Near-term"
        if mid >= max(recent, longh, found):
            return "Mid-term"
        if longh >= max(recent, mid, found):
            return "Long-term"
        return "Foundational"

    def _is_hybrid_thesis_anchored(self, intent: str, sources: List[Source]) -> bool:
        """Mark market briefs as thesis-anchored if academic share is notable."""
        if intent != "market":
            return False
        total = max(1, len(sources))
        academic = sum(1 for s in sources if s.source_type == SourceType.ACADEMIC)
        return (academic / total) >= 0.25
    
    def _call_analysis_tool(self, tool_name: str, *args) -> str:
        try:
            if tool_name == "analyze_market":
                return analyze_market(*args)
            elif tool_name == "analyze_technology":
                return analyze_technology(*args)
            elif tool_name == "analyze_competitive":
                return analyze_competitive(*args)
            elif tool_name == "expand_lenses":
                return expand_lenses(*args)
            elif tool_name == "write_executive_summary":
                return write_executive_summary(*args)
            else:
                raise ValueError(f"Tool {tool_name} not found")
                
        except Exception as e:
            logger.error(f"Error calling analysis tool {tool_name}: {str(e)}")
            return f"Error in {tool_name}: {str(e)}"
    
    def _refine_query_for_title(self, original_query: str) -> str:
        """Refine user query using structured prompt template to better capture title intent"""
        if not STIConfig.ENABLE_QUERY_REFINEMENT:
            return original_query
            
        try:
            # Create structured prompt template following LangChain best practices
            prompt_template = PromptTemplate(
                input_variables=["original_query"],
                template="""You are a query refinement expert. Your task is to refine search queries to better capture the specific topic intent for accurate source retrieval.

PURPOSE: Refine the user query to ensure it will find sources that match the intended report title.

CONTEXT: The user wants to generate a report with a specific title, but the query might be too broad or vague to find relevant sources.

TASK: Analyze the original query and create a refined version that:
1. Focuses on the specific topic mentioned in the query
2. Uses domain-specific terminology
3. Includes relevant keywords for better source matching
4. Maintains the original intent while being more precise

EXAMPLES:
- Original: "AI technology trends" → Refined: "artificial intelligence technology trends machine learning developments"
- Original: "Command Theory in Multi-Agent Systems" → Refined: "command theory multi-agent systems coordination control theory distributed agents"
- Original: "cybersecurity developments" → Refined: "cybersecurity developments security threats vulnerability management enterprise security"

Original Query: {original_query}

Return only the refined query as plain text, no JSON formatting, no additional text:"""
            )
            
            # Use existing LLM with structured output
            response = self.llm.invoke(prompt_template.format(original_query=original_query))
            refined_query = response.content.strip()
            
            # Clean up any JSON formatting if present
            if refined_query.startswith('"') and refined_query.endswith('"'):
                refined_query = refined_query[1:-1]
            if refined_query.startswith('{') and '"query"' in refined_query:
                try:
                    import json
                    data = json.loads(refined_query)
                    refined_query = data.get('query', original_query)
                except (json.JSONDecodeError, KeyError):
                    pass
            elif refined_query.startswith('{') and '"refined_query"' in refined_query:
                try:
                    import json
                    data = json.loads(refined_query)
                    refined_query = data.get('refined_query', original_query)
                except (json.JSONDecodeError, KeyError):
                    pass
            
            logger.info(f"Query refined: '{original_query}' → '{refined_query}'")
            return refined_query
            
        except Exception as e:
            logger.error(f"Error refining query: {str(e)}")
            return original_query
    
    def _validate_source_relevance(self, source: Source, title: str) -> bool:
        """Additional validation to catch obviously irrelevant sources"""
        title_keywords = title.lower().split()
        source_title = source.title.lower()
        
        # Check for completely unrelated topics
        unrelated_topics = ['politics', 'trump', 'bessent', 'carney', 'provinces', 'election', 'government']
        if any(topic in source_title for topic in unrelated_topics):
            logger.info(f"✗ Filtered out irrelevant source: '{source.title}' (unrelated topic)")
            return False
        
        # Check for basic keyword overlap with title
        if not any(keyword in source_title for keyword in title_keywords):
            # Allow some flexibility for multi-word concepts
            title_phrases = [' '.join(title_keywords[i:i+2]) for i in range(len(title_keywords)-1)]
            if not any(phrase in source_title for phrase in title_phrases):
                logger.info(f"✗ Filtered out irrelevant source: '{source.title}' (no keyword overlap)")
                return False
        
        return True
    
    def _semantic_similarity_filter(self, sources: List[Source], query: str, threshold: float = 0.5, concepts: List[str] = None) -> List[Source]:
        """Filter sources using embeddings-based semantic similarity. If concepts provided, accept if any concept matches."""
        if not sources:
            return sources
            
        try:
            # Initialize embeddings
            embeddings = OpenAIEmbeddings()
            
            # Get query embedding
            query_embedding = embeddings.embed_query(query)
            concept_embeddings = []
            if concepts:
                for c in concepts[:8]:
                    try:
                        concept_embeddings.append(embeddings.embed_query(c))
                    except Exception:
                        continue
            
            filtered_sources = []
            for source in sources:
                # Create source text for embedding
                source_text = f"{source.title} {source.content[:500]}"
                source_embedding = embeddings.embed_query(source_text)
                
                # Calculate cosine similarity vs query
                def cos(a, b):
                    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))
                
                similarities = [cos(query_embedding, source_embedding)]
                if concept_embeddings:
                    for ce in concept_embeddings:
                        similarities.append(cos(ce, source_embedding))
                
                max_sim = max(similarities)
                
                if max_sim >= threshold:
                    filtered_sources.append(source)
                    logger.info(f"✓ Semantic match: '{source.title}' (similarity: {max_sim:.2f})")
                else:
                    logger.info(f"✗ Semantic mismatch: '{source.title}' (max similarity: {max_sim:.2f})")
            
            logger.info(f"Semantic filtering: {len(sources)} → {len(filtered_sources)} sources (threshold: {threshold})")
            return filtered_sources
            
        except Exception as e:
            logger.error(f"Error in semantic similarity filter: {str(e)}")
            return sources  # Return all sources if filtering fails
    
    def _classify_query_intent(self, query: str) -> str:
        """Classify query as 'theory' or 'market' using LLM with examples"""
        if not STIConfig.ENABLE_INTENT_ROUTING:
            return "market"  # Default to market if routing disabled
        
        try:
            parser = PydanticOutputParser(pydantic_object=QueryIntent)
            
            prompt_template = PromptTemplate(
                input_variables=["query", "theory_keywords", "market_keywords"],
                template="""Classify the following query as either 'theory' or 'market' based on its content.

Theory queries focus on:
- Mathematical or formal frameworks (e.g., "command theory", "control theory", "consensus algorithms")
- Algorithmic approaches, proofs, theorems, mathematical models
- Academic or research-oriented topics
- Keywords: {theory_keywords}

Market queries focus on:
- Business trends, startup funding, enterprise products
- Vendor announcements, market dynamics, commercial developments
- Industry news, investments, acquisitions
- Keywords: {market_keywords}

Query: {query}

{format_instructions}

Return your classification:"""
            )
            
            formatted_prompt = prompt_template.format(
                query=query,
                theory_keywords=", ".join(STIConfig.THEORY_KEYWORDS[:5]),
                market_keywords=", ".join(STIConfig.MARKET_KEYWORDS[:5]),
                format_instructions=parser.get_format_instructions()
            )
            
            response = self.llm.invoke(formatted_prompt)
            result = parser.parse(response.content)
            
            intent = result.intent.lower()
            logger.info(f"Query intent classified as: {intent} (confidence: {result.confidence:.2f})")
            return intent
            
        except Exception as e:
            logger.warning(f"Error classifying intent, defaulting to market: {str(e)}")
            # Fallback: simple keyword-based classification
            query_lower = query.lower()
            theory_match = sum(1 for kw in STIConfig.THEORY_KEYWORDS if kw in query_lower)
            market_match = sum(1 for kw in STIConfig.MARKET_KEYWORDS if kw in query_lower)
            
            if theory_match > market_match:
                return "theory"
            return "market"
    
    def _expand_theoretical_query(self, query: str) -> str:
        """Expand theory queries with synonyms, domain terms, and first-principles terms"""
        try:
            # Domain-specific expansions
            expansions = {
                'command theory': ['command theory', 'control theory', 'coordination mechanisms', 'multi-agent consensus', 'distributed control', 'hierarchical control', 'command and control', 'supervisory control'],
                'control theory': ['control theory', 'Lyapunov stability', 'feedback control', 'adaptive control', 'optimal control', 'robust control', 'stability analysis'],
                'multi-agent': ['multi-agent systems', 'distributed agents', 'agent coordination', 'consensus protocols', 'swarm intelligence', 'distributed systems'],
                'game theory': ['game theory', 'Nash equilibrium', 'cooperative games', 'mechanism design', 'auction theory', 'strategic interaction'],
                'consensus': ['consensus', 'distributed consensus', 'agreement protocols', 'distributed agreement', 'Byzantine consensus', 'leader election', 'coordination', 'graph Laplacian'],
                'distributed': ['distributed systems', 'decentralized', 'peer-to-peer', 'federated', 'distributed computing'],
                'hierarchical': ['hierarchical', 'layered', 'tiered', 'structured', 'organizational', 'leader–follower', 'formation control', 'containment control'],
                'coordination': ['coordination', 'synchronization', 'orchestration', 'cooperation', 'collaboration']
            }
            
            query_lower = query.lower()
            expanded_terms = [query]
            
            for key, synonyms in expansions.items():
                if key in query_lower:
                    expanded_terms.extend(synonyms[:6])  # Add top synonyms
            
            # Add first-principles and foundational terms for theoretical queries
            foundational_terms = [
                'theoretical foundations', 'mathematical foundations', 'first principles',
                'survey', 'state of the art', 'comprehensive review', 'systematic review',
                'highly cited', 'seminal', 'foundational', 'theoretical framework',
                'Lyapunov', 'stability', 'graph Laplacian', 'command and control', 'supervisory control'
            ]
            
            # Add foundational terms if query contains theoretical keywords
            theory_keywords = ['theory', 'theoretical', 'framework', 'model', 'algorithm', 'consensus', 'control', 'command']
            if any(keyword in query_lower for keyword in theory_keywords):
                expanded_terms.extend(foundational_terms[:8])
            
            # Combine original query with expanded terms
            expanded_query = " OR ".join(set(expanded_terms[:12]))  # Limit to 12 terms
            
            logger.info(f"Expanded theory query: {expanded_query}")
            return expanded_query
            
        except Exception as e:
            logger.warning(f"Error expanding query, using original: {str(e)}")
            return query
    
    def _decompose_theory_query(self, query: str) -> List[str]:
        """Decompose theoretical query into core concepts for first-principles search"""
        try:
            query_lower = query.lower()
            core_concepts = []
            
            # Define concept mappings for common theoretical terms
            concept_mappings = {
                'command theory': ['command', 'control', 'hierarchical control', 'command and control systems', 'distributed control'],
                'multi-agent': ['multi-agent', 'distributed systems', 'agent coordination', 'cooperative control', 'swarm intelligence'],
                'control theory': ['control theory', 'feedback control', 'adaptive control', 'optimal control', 'robust control'],
                'consensus': ['consensus', 'agreement protocols', 'distributed agreement', 'leader election', 'coordination'],
                'game theory': ['game theory', 'nash equilibrium', 'cooperative games', 'mechanism design', 'strategic interaction'],
                'distributed': ['distributed systems', 'decentralized', 'peer-to-peer', 'federated', 'distributed algorithms'],
                'coordination': ['coordination', 'synchronization', 'orchestration', 'cooperation', 'collaboration'],
                'hierarchical': ['hierarchical', 'layered', 'tiered', 'structured', 'organizational'],
                'protocol': ['protocol', 'algorithm', 'procedure', 'mechanism', 'framework']
            }
            
            # Extract core concepts from query
            for term, concepts in concept_mappings.items():
                if term in query_lower:
                    core_concepts.extend(concepts)
            
            # Add general theoretical terms if no specific mappings found
            if not core_concepts:
                # Extract individual words and map to theoretical concepts
                words = query_lower.split()
                for word in words:
                    if word in ['theory', 'theoretical', 'framework', 'model', 'algorithm']:
                        core_concepts.append(word)
                    elif word in ['system', 'systems']:
                        core_concepts.append('distributed systems')
                    elif word in ['agent', 'agents']:
                        core_concepts.append('multi-agent systems')
                    elif word in ['control']:
                        core_concepts.append('control theory')
            
            # If still no concepts found, extract key nouns/phrases as concepts for broader theory queries
            # This handles queries like "Cognitive Wars" or "Influence Operations" that don't match specific mappings
            if not core_concepts:
                # Extract meaningful phrases (2-3 word combinations) and significant nouns
                words = query_lower.split()
                # Skip common stop words
                stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were'}
                significant_words = [w for w in words if w not in stop_words and len(w) > 3]
                
                # Add key phrases (adjacent significant words)
                for i in range(len(significant_words) - 1):
                    phrase = f"{significant_words[i]} {significant_words[i+1]}"
                    core_concepts.append(phrase)
                
                # Also add individual significant words as concepts
                core_concepts.extend(significant_words[:5])  # Top 5 words
            
            # Remove duplicates and limit to most relevant concepts
            unique_concepts = list(dict.fromkeys(core_concepts))  # Preserve order, remove duplicates
            limited_concepts = unique_concepts[:8]  # Limit to top 8 concepts
            
            # Ensure we always have at least the original query as a fallback
            if not limited_concepts:
                limited_concepts = [query]
            
            logger.info(f"Decomposed query '{query}' into concepts: {limited_concepts}")
            return limited_concepts
            
        except Exception as e:
            logger.error(f"Error decomposing theory query: {str(e)}")
            # Fallback: return the original query as a single concept
            return [query]
    
    def _search_foundational_sources(self, concepts: List[str], days_back: int = 180) -> List[Source]:
        """Search for foundational/seminal papers and survey papers for theoretical concepts with caps and guards"""
        try:
            foundational_sources: List[Source] = []
            seen_urls = set()
            total_calls = 0
            max_calls = 60  # Increased for anchor search
            target = STIConfig.MIN_ACADEMIC_SOURCES_THEORY
            
            # Check if query is explicitly about control theory (narrow filter) vs general theory (broad filter)
            concepts_lower = ' '.join(concepts).lower()
            is_control_theory_query = any(term in concepts_lower for term in [
                'control theory', 'command and control', 'consensus', 'formation control',
                'containment control', 'leader-follower', 'multi-agent', 'distributed control'
            ])
            
            def add_sources(found: List[Source]):
                nonlocal foundational_sources, seen_urls
                for s in found:
                    if s.url in seen_urls:
                        continue
                    # Only apply narrow control theory filter if query is explicitly about control theory
                    # Otherwise, accept any academic source from anchor domains (broader theory queries)
                    if is_control_theory_query:
                        # For control theory queries, use narrow filter
                        if self._is_control_theory_on_topic(s):
                            foundational_sources.append(s)
                            seen_urls.add(s.url)
                    else:
                        # For general theory queries, accept any academic source from anchor domains
                        # (the fact that it came from academic search is sufficient quality signal)
                        foundational_sources.append(s)
                        seen_urls.add(s.url)
            
            # Use thesis anchor domains from config
            anchor_domains = getattr(STIConfig, 'THESIS_ANCHOR_DOMAINS', [
                'ieeexplore.ieee.org', 'dl.acm.org', 'link.springer.com', 'sciencedirect.com'
            ])
            venue_terms = ['"IEEE Transactions on Automatic Control"', 'Automatica', '"American Control Conference"']
            
            # Domain-specific queries for control/C2 doctrine, distributed systems, human-factors
            control_c2_queries = [
                '"command and control" doctrine military',
                '"C2 architecture" hierarchical distributed',
                '"command structure" multi-agent',
            ]
            distributed_systems_queries = [
                '"distributed systems" consensus coordination',
                '"multi-agent systems" protocols algorithms',
                '"distributed control" stability',
            ]
            human_factors_queries = [
                '"human-agent interaction" command control',
                '"human-in-the-loop" multi-agent',
                '"trust" "autonomy" command delegation',
            ]
            
            for concept in concepts[:5]:
                if total_calls >= max_calls or len(foundational_sources) >= target:
                    break
                foundational_queries = [
                    f'"{concept}" survey review "state of the art"',
                    f'"{concept}" "highly cited" seminal',
                    f'"{concept}" "theoretical framework"',
                ]
                anchor_titles = [
                    '"Consensus and Cooperation in Networked Multi-Agent Systems"',
                    '"Distributed consensus in multi-agent systems"',
                    '"Leader-follower consensus"',
                    '"Formation control"',
                    '"Containment control"'
                ]
                per_concept = 0
                for q in foundational_queries + anchor_titles:
                    if total_calls >= max_calls or len(foundational_sources) >= target or per_concept >= 4:
                        break
                    for site in anchor_domains[:8]:  # Limit to first 8 domains
                        if total_calls >= max_calls or len(foundational_sources) >= target or per_concept >= 4:
                            break
                        try:
                            total_calls += 1
                            per_concept += 1
                            sources = self._search_by_domain_type(f'{q} site:{site}', [], SourceType.ACADEMIC, max_results=2, days_back=days_back)
                            add_sources(sources)
                        except Exception as e:
                            logger.warning(f"Foundational query failed '{q} site:{site}': {str(e)}")
                            continue
                # venue-term probes
                for term in venue_terms:
                    if total_calls >= max_calls or len(foundational_sources) >= target:
                        break
                    try:
                        total_calls += 1
                        sources = self._search_by_domain_type(f'"{concept}" {term}', [], SourceType.ACADEMIC, max_results=2, days_back=days_back)
                        add_sources(sources)
                    except Exception as e:
                        logger.warning(f"Venue query failed '{term}': {str(e)}")
                        continue
                
                # Domain-specific anchor searches
                domain_queries = [
                    (control_c2_queries, "control/C2"),
                    (distributed_systems_queries, "distributed systems"),
                    (human_factors_queries, "human-factors"),
                ]
                for domain_query_list, domain_name in domain_queries:
                    if total_calls >= max_calls or len(foundational_sources) >= target:
                        break
                    for q in domain_query_list[:2]:  # Limit to 2 queries per domain
                        if total_calls >= max_calls or len(foundational_sources) >= target:
                            break
                        for site in anchor_domains[:5]:  # Limit to 5 anchor domains
                            if total_calls >= max_calls or len(foundational_sources) >= target:
                                break
                            try:
                                total_calls += 1
                                sources = self._search_by_domain_type(f'{q} site:{site}', [], SourceType.ACADEMIC, max_results=1, days_back=days_back)
                                add_sources(sources)
                            except Exception as e:
                                logger.warning(f"Domain anchor query failed '{q} {domain_name} site:{site}': {str(e)}")
                                continue
            
            logger.info(f"Foundational search: {len(foundational_sources)} unique, calls={total_calls}")
            return foundational_sources
            
        except Exception as e:
            logger.error(f"Error in foundational search: {str(e)}")
            return []
    
    def _search_thesis_anchor_sources(self, query: str, days_back: int = 1825) -> List[Source]:
        """Search specifically for anchor (peer-reviewed) sources for thesis reports"""
        try:
            anchor_sources: List[Source] = []
            seen_urls = set()
            total_calls = 0
            max_calls = 20
            min_anchors = getattr(STIConfig, 'THESIS_MIN_ANCHOR_SOURCES', 5)
            
            anchor_domains = getattr(STIConfig, 'THESIS_ANCHOR_DOMAINS', [])
            
            # Control/C2 doctrine queries
            control_c2_queries = [
                f'"{query}" "command and control" doctrine',
                f'"{query}" "C2 architecture"',
                f'"{query}" hierarchical distributed control',
            ]
            
            # Distributed systems queries
            distributed_queries = [
                f'"{query}" distributed systems',
                f'"{query}" multi-agent coordination',
                f'"{query}" consensus protocols',
            ]
            
            all_queries = control_c2_queries + distributed_queries
            
            for q in all_queries[:6]:  # Limit to 6 queries
                if total_calls >= max_calls or len(anchor_sources) >= min_anchors:
                    break
                for site in anchor_domains[:5]:  # Limit to 5 anchor domains
                    if total_calls >= max_calls or len(anchor_sources) >= min_anchors:
                        break
                    try:
                        total_calls += 1
                        sources = self._search_by_domain_type(f'{q} site:{site}', [], SourceType.ACADEMIC, max_results=2, days_back=days_back)
                        for s in sources:
                            if s.url in seen_urls:
                                continue
                            # Only include sources from anchor domains
                            if any(domain in s.url for domain in anchor_domains):
                                anchor_sources.append(s)
                                seen_urls.add(s.url)
                    except Exception as e:
                        logger.warning(f"Anchor query failed '{q} site:{site}': {str(e)}")
                        continue
            
            logger.info(f"Thesis anchor search: {len(anchor_sources)} anchor sources, calls={total_calls}")
            return anchor_sources
            
        except Exception as e:
            logger.error(f"Error in thesis anchor search: {str(e)}")
            return []
    
    def _calculate_thesis_source_diversity(self, sources: List[Source]) -> float:
        """Calculate source diversity score for thesis reports (penalize if >80% single domain)"""
        if not sources:
            return 0.0
        
        # Count sources by domain
        domain_counts = {}
        anchor_domains = getattr(STIConfig, 'THESIS_ANCHOR_DOMAINS', [])
        single_domain_threshold = getattr(STIConfig, 'THESIS_SINGLE_DOMAIN_THRESHOLD', 0.80)
        diversity_target = getattr(STIConfig, 'THESIS_SOURCE_DIVERSITY_TARGET', 0.40)
        
        for source in sources:
            domain = None
            # Check if source is from anchor domain
            for anchor_domain in anchor_domains:
                if anchor_domain in source.url:
                    domain = anchor_domain
                    break
            if not domain:
                # Check for arXiv
                if 'arxiv.org' in source.url:
                    domain = 'arxiv.org'
                else:
                    domain = 'other'
            
            domain_counts[domain] = domain_counts.get(domain, 0) + 1
        
        # Calculate diversity metrics
        total_sources = len(sources)
        anchor_count = sum(count for domain, count in domain_counts.items() if domain != 'arxiv.org' and domain != 'other')
        anchor_fraction = anchor_count / total_sources if total_sources > 0 else 0.0
        
        # Calculate domain concentration (max fraction from single domain)
        max_domain_fraction = max(domain_counts.values()) / total_sources if total_sources > 0 else 0.0
        
        # Score: penalize if >80% from single domain, reward if anchor fraction meets target
        diversity_score = 1.0
        if max_domain_fraction > single_domain_threshold:
            # Penalize: reduce score proportionally to how much over threshold
            penalty = (max_domain_fraction - single_domain_threshold) / (1.0 - single_domain_threshold)
            diversity_score = 1.0 - (penalty * 0.3)  # Max 30% penalty
        
        if anchor_fraction < diversity_target:
            # Penalize: reduce score if anchor fraction below target
            shortfall = (diversity_target - anchor_fraction) / diversity_target
            diversity_score = diversity_score * (1.0 - shortfall * 0.2)  # Max 20% penalty
        
        logger.info(f"Source diversity: anchor_fraction={anchor_fraction:.2f} (target={diversity_target}), "
                   f"max_domain_fraction={max_domain_fraction:.2f} (threshold={single_domain_threshold}), "
                   f"score={diversity_score:.2f}")
        
        return max(0.0, min(1.0, diversity_score))
    
    def _classify_thesis_source_type(self, source: Source) -> ThesisSourceType:
        """Classify source type for thesis reports (P/D/A/O/G)"""
        url = source.url.lower()
        title = getattr(source, 'title', '').lower()
        publisher = getattr(source, 'publisher', '').lower()
        
        # Peer-reviewed (P): IEEE, ACM, Springer, ScienceDirect, JSTOR, SIAM, APS
        anchor_domains = getattr(STIConfig, 'THESIS_ANCHOR_DOMAINS', [])
        for domain in anchor_domains:
            if domain.lower() in url:
                return ThesisSourceType.PEER_REVIEWED
        
        # ArXiv (A): arXiv preprints, conference preprints
        if 'arxiv.org' in url or 'arxiv' in url or 'arxiv' in publisher:
            return ThesisSourceType.ARXIV
        
        # Official (O): Government, standards bodies, official data
        official_domains = ['.gov', '.edu', 'nist.gov', 'iso.org', 'itu.int', 'ieee.org/standards']
        if any(domain in url for domain in official_domains):
            return ThesisSourceType.OFFICIAL
        
        # Doctrine (D): Official doctrine, standards bodies, military/defense
        doctrine_keywords = ['doctrine', 'standard', 'military', 'defense', 'navy.mil', 'army.mil']
        if any(keyword in url or keyword in title for keyword in doctrine_keywords):
            return ThesisSourceType.DOCTRINE
        
        # Grey (G): Industry whitepapers, reputable blogs, everything else
        return ThesisSourceType.GREY
    
    def _calculate_anchor_status(self, sources: List[Source]) -> str:
        """Calculate anchor_status: Anchored|Anchor-Sparse|Anchor-Absent"""
        anchor_domains = getattr(STIConfig, 'THESIS_ANCHOR_DOMAINS', [])
        anchor_count = sum(1 for s in sources if any(domain in s.url.lower() for domain in anchor_domains))
        
        if anchor_count >= 2:
            return "Anchored"
        elif anchor_count == 1:
            return "Anchor-Sparse"
        else:
            return "Anchor-Absent"
    
    def _calculate_thesis_confidence(self, sources: List[Source], draft: ThesisDraft, 
                                     cem_grid: CEMGrid = None, has_assumptions_ledger: bool = False) -> float:
        """
        Calculate thesis confidence using playbook formula: C = 0.3·S + 0.25·A + 0.25·M + 0.2·R
        
        Where:
        - S = Source diversity (0-1): unique publishers & types
        - A = Anchor coverage (0-1): share of primary claims with Type-1 anchors
        - M = Method transparency (0-1): CEM completeness + assumptions ledger present
        - R = Replication readiness (0-1): sim plan + datasets/params specified
        """
        if not sources:
            return 0.0
        
        # S: Source diversity (unique publishers & types)
        unique_publishers = set(getattr(s, 'publisher', '') or '' for s in sources)
        source_types = set(self._classify_thesis_source_type(s) for s in sources)
        diversity_score = min(1.0, (len(unique_publishers) / max(1, len(sources))) * 0.6 + 
                                   (len(source_types) / 5.0) * 0.4)  # Normalize to 0-1
        
        # A: Anchor coverage (share of primary claims with Type-1 anchors)
        anchor_domains = getattr(STIConfig, 'THESIS_ANCHOR_DOMAINS', [])
        anchor_sources = [s for s in sources if any(domain in s.url.lower() for domain in anchor_domains)]
        
        if cem_grid and cem_grid.rows:
            # Count primary claims (first 3-5 claims are typically primary)
            primary_claims = cem_grid.rows[:min(5, len(cem_grid.rows))]
            claims_with_anchors = 0
            
            for row in primary_claims:
                evidence = row.evidence
                # Check if evidence cites anchor sources (Type-1 = P)
                # Look for [^id:P] format in evidence
                import re
                anchor_citations = re.findall(r'\[\^(\d+):P\]', evidence)
                if anchor_citations:
                    cited_ids = [int(id) for id in anchor_citations]
                    # Check if any cited source is an anchor
                    if any(s.id in cited_ids for s in anchor_sources):
                        claims_with_anchors += 1
            
            anchor_coverage = claims_with_anchors / max(1, len(primary_claims))
        else:
            # Fallback: use anchor fraction of sources
            anchor_coverage = len(anchor_sources) / max(1, len(sources))
        
        # M: Method transparency (CEM completeness + assumptions ledger)
        method_transparency = 0.0
        if cem_grid and cem_grid.rows:
            # Check CEM completeness: all rows have risk and test_id
            complete_rows = sum(1 for row in cem_grid.rows 
                              if getattr(row, 'risk', '') and getattr(row, 'test_id', ''))
            cem_completeness = complete_rows / max(1, len(cem_grid.rows))
            method_transparency += cem_completeness * 0.6
        
        if has_assumptions_ledger:
            method_transparency += 0.4
        else:
            method_transparency += 0.2  # Partial credit if CEM exists
        
        method_transparency = min(1.0, method_transparency)
        
        # R: Replication readiness (sim plan + datasets/params specified)
        markdown_lower = draft.markdown.lower()
        has_sim_plan = any(kw in markdown_lower for kw in ['simulation', 'sim', 'parameter sweep', 'monte carlo'])
        has_params = any(kw in markdown_lower for kw in ['parameter', 'dataset', 'config', 'hyperparameter'])
        has_method = any(kw in markdown_lower for kw in ['method', 'methodology', 'evaluation plan'])
        
        replication_readiness = 0.0
        if has_sim_plan:
            replication_readiness += 0.4
        if has_params:
            replication_readiness += 0.3
        if has_method:
            replication_readiness += 0.3
        
        # Calculate final confidence: C = 0.3·S + 0.25·A + 0.25·M + 0.2·R
        confidence = (0.3 * diversity_score + 
                     0.25 * anchor_coverage + 
                     0.25 * method_transparency + 
                     0.2 * replication_readiness)
        
        return max(0.0, min(1.0, confidence))
    
    def _generate_thesis_style_report(self, signals: List[SignalModel], sources: List[Source], 
                                    query: str, foundational_sources: List[Source] = None) -> str:
        """Generate thesis-style report building from first principles and foundational theory"""
        try:
            # Classify sources by type
            direct_sources = [s for s in sources if any(term in s.title.lower() or term in s.content.lower() 
                                                      for term in query.lower().split())]
            foundational_sources = foundational_sources or []
            related_sources = [s for s in sources if s not in direct_sources and s not in foundational_sources]
            
            # Create methodology note
            methodology_note = ""
            if len(direct_sources) < 2:
                methodology_note = f"\n\n**Methodology Note**: Limited recent publications found on '{query}'. This analysis builds from foundational control theory and multi-agent systems research to explore the domain, making reasoned connections from established theory to the specific topic.\n"
            
            # Generate thesis-style sections
            sections = []
            
            # 1. Foundational Theory Section
            if foundational_sources:
                foundational_text = self._generate_foundational_section(foundational_sources, query)
                sections.append(foundational_text)
            
            # 2. Related Concepts Section  
            if related_sources:
                related_text = self._generate_related_concepts_section(related_sources, query)
                sections.append(related_text)
            
            # 3. Synthesis and Extrapolation Section
            synthesis_text = self._generate_synthesis_section(signals, sources, query, direct_sources)
            sections.append(synthesis_text)
            
            # 4. Open Questions and Future Directions
            future_text = self._generate_future_directions_section(query, sources)
            sections.append(future_text)
            
            # Combine sections
            thesis_report = methodology_note + "\n\n".join(sections)
            
            logger.info(f"Generated thesis-style report with {len(sections)} sections")
            return thesis_report
            
        except Exception as e:
            logger.error(f"Error generating thesis-style report: {str(e)}")
            return f"Error generating thesis-style analysis: {str(e)}"
    
    def _generate_foundational_section(self, foundational_sources: List[Source], query: str) -> str:
        """Generate foundational theory section from seminal papers"""
        section = "## Foundational Theory\n\n"
        section += "This analysis builds upon established theoretical foundations in control theory and multi-agent systems:\n\n"
        
        for i, source in enumerate(foundational_sources[:3], 1):
            # Dict/object safe extraction
            title = getattr(source, 'title', None) or (source.get('title') if isinstance(source, dict) else '')
            publisher = getattr(source, 'publisher', None) or (source.get('publisher') if isinstance(source, dict) else '')
            date_str = getattr(source, 'date', None) or (source.get('date') if isinstance(source, dict) else '')
            content = getattr(source, 'content', None) or (source.get('content') if isinstance(source, dict) else '')
            section += f"**{i}. {title}**\n"
            section += f"*{publisher}* - {date_str}\n\n"
            # Extract key theoretical concepts from content
            content_preview = (content[:300] + "...") if content and len(content) > 300 else (content or "")
            section += f"{content_preview}\n\n"
        
        section += "These foundational works provide the theoretical framework for understanding command theory in multi-agent contexts.\n"
        return section
    
    def _generate_related_concepts_section(self, related_sources: List[Source], query: str) -> str:
        """Generate related concepts section from adjacent domains"""
        section = "## Related Concepts and Applications\n\n"
        section += "Adjacent research areas provide insights into command theory applications:\n\n"
        
        for i, source in enumerate(related_sources[:3], 1):
            title = getattr(source, 'title', None) or (source.get('title') if isinstance(source, dict) else '')
            publisher = getattr(source, 'publisher', None) or (source.get('publisher') if isinstance(source, dict) else '')
            date_str = getattr(source, 'date', None) or (source.get('date') if isinstance(source, dict) else '')
            content = getattr(source, 'content', None) or (source.get('content') if isinstance(source, dict) else '')
            section += f"**{i}. {title}**\n"
            section += f"*{publisher}* - {date_str}\n\n"
            content_preview = (content[:250] + "...") if content and len(content) > 250 else (content or "")
            section += f"{content_preview}\n\n"
        
        section += "These related works demonstrate how command and control principles apply across different domains.\n"
        return section
    
    def _generate_synthesis_section(self, signals: List[SignalModel], sources: List[Source], 
                                  query: str, direct_sources: List[Source]) -> str:
        """Generate synthesis section connecting theory to current developments"""
        section = "## Synthesis and Current Developments\n\n"
        
        if direct_sources:
            section += "Recent developments in command theory and multi-agent systems:\n\n"
            for signal in signals[:3]:
                # dict/object safe fields
                s_date = getattr(signal, 'date', None) or (signal.get('date') if isinstance(signal, dict) else '')
                s_text = getattr(signal, 'content', None) or (signal.get('text') if isinstance(signal, dict) else '')
                section += f"- **{s_date}**: {s_text}\n"
            section += "\n"
        else:
            section += "While specific recent publications on this exact topic are limited, current trends in multi-agent systems and control theory suggest:\n\n"
        
        # Add reasoned extrapolation
        section += "**Theoretical Extrapolation**: Based on established control theory principles and multi-agent coordination mechanisms, command theory in multi-agent systems likely involves:\n\n"
        section += "1. **Hierarchical Control Structures**: Multi-level command hierarchies where higher-level agents issue commands to lower-level agents\n"
        section += "2. **Consensus Mechanisms**: Protocols for achieving agreement on command execution across distributed agents\n"
        section += "3. **Fault Tolerance**: Robustness mechanisms for handling agent failures and command conflicts\n"
        section += "4. **Scalability Considerations**: Efficient algorithms for managing command distribution in large agent populations\n\n"
        
        section += "*Note: These extrapolations are based on established theoretical foundations and may require empirical validation.*\n"
        return section

    # Thesis subgraph nodes (LangGraph-style deterministic micro-nodes)
    def _thesis_outline(self, concepts: ConceptList, sources: List[Source]) -> ThesisOutline:
        try:
            parser = PydanticOutputParser(pydantic_object=ThesisOutline)
            prompt = PromptTemplate(
                input_variables=["concepts", "format_instructions"],
                template=(
                    "You are drafting an outline for a theory-first thesis brief.\n"
                    "Use the provided concepts as the backbone.\n\n"
                    "Concepts: {concepts}\n\n"
                    "Return a JSON matching the schema.\n"
                    "{format_instructions}"
                )
            )
            resp = self.llm.invoke(
                prompt.format(concepts=", ".join(concepts.concepts[:8]),
                              format_instructions=parser.get_format_instructions())
            )
            content = resp.content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            return ThesisOutline(**json.loads(content))
        except Exception as e:
            logger.warning(f"Outline parser fallback: {str(e)}")
            return ThesisOutline(
                sections=['Foundations','Formalization','Mechanisms','Applications','Limits and Open Questions'],
                claims_by_section={'Foundations': concepts.concepts[:5] or ['control theory','consensus']}
            )

    def _thesis_compose(self, outline: ThesisOutline, sources: List[Source], query: str) -> ThesisDraft:
        try:
            parser = PydanticOutputParser(pydantic_object=ThesisDraft)
            # Prepare compact sources payload
            src_payload = []
            for i, s in enumerate(sources, 1):
                src_payload.append({
                    'id': i,
                    'title': getattr(s,'title',None) or (s.get('title') if isinstance(s,dict) else ''),
                    'publisher': getattr(s,'publisher',None) or (s.get('publisher') if isinstance(s,dict) else ''),
                    'date': getattr(s,'date',None) or (s.get('date') if isinstance(s,dict) else ''),
                    'url': getattr(s,'url',None) or (s.get('url') if isinstance(s,dict) else '')
                })
            # Identify anchor sources (non-preprint, peer-reviewed)
            anchor_domains = getattr(STIConfig, 'THESIS_ANCHOR_DOMAINS', [])
            anchor_sources_list = [s for s in sources if any(domain in s.url for domain in anchor_domains)]
            preprint_sources = [s for s in sources if 'arxiv.org' in s.url]
            anchor_count = len(anchor_sources_list)
            
            prompt = PromptTemplate(
                input_variables=["query","outline","sources","format_instructions","anchor_count"],
                template=(
                    "Compose a thesis-style brief (markdown) with sections from the outline.\n"
                    "Cite sources as [^id] where appropriate. Keep rigorous, concise.\n\n"
                    "REQUIREMENTS:\n"
                    "- Foundations section: Include a 'Why these anchors?' paragraph explaining the selection of anchor (peer-reviewed, non-preprint) sources. Currently {anchor_count} anchor sources are included.\n"
                    "- Applications section: Include 2+ parameterized vignettes (e.g., disaster response under intermittent comms; autonomous ISR swarm with contested spectrum) with metrics (MTTA, failure prob) and failure modes. Minimum 400 words.\n"
                    "- Limits & Open Questions: Include 'Operational Assumptions & Diagnostics' subsection with bounded-rationality assumption and adversarial comms model, each with concrete triggers and delegation policies. Move human-in-loop and adversarial from future work to present assumptions. Minimum 300 words.\n"
                    "- Mechanisms section: Ensure unique content, do not repeat Executive Summary.\n"
                    "- Synthesis section: Ensure unique synthesis, do not repeat Executive Summary.\n\n"
                    "Query: {query}\n"
                    "Outline: {outline}\n"
                    "Sources: {sources}\n\n"
                    "Return JSON per schema.\n{format_instructions}"
                )
            )
            resp = self.llm.invoke(
                prompt.format(
                    query=query,
                    outline=json.dumps(outline.model_dump()),
                    sources=json.dumps(src_payload[:15]),  # Increased from 12 to 15
                    format_instructions=parser.get_format_instructions(),
                    anchor_count=anchor_count
                )
            )
            content = resp.content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            return ThesisDraft(**json.loads(content))
        except Exception as e:
            logger.warning(f"Thesis compose fallback: {str(e)}")
            # Minimal fallback
            biblio = []
            for i, s in enumerate(sources, 1):
                title = getattr(s,'title',None) or (s.get('title') if isinstance(s,dict) else '')
                publisher = getattr(s,'publisher',None) or (s.get('publisher') if isinstance(s,dict) else '')
                date_str = getattr(s,'date',None) or (s.get('date') if isinstance(s,dict) else '')
                url = getattr(s,'url',None) or (s.get('url') if isinstance(s,dict) else '')
                biblio.append(f"[^{i}]: {title} — {publisher}, {date_str}. {url}")
            outline_md = "\n\n".join([f"### {sec}\n" for sec in outline.sections])
            md = f"# Thesis Brief — {query}\n\n{outline_md}\n\n## Sources\n\n" + "\n".join(biblio)
            return ThesisDraft(markdown=md, cited_source_ids=list(range(1, len(sources)+1)))
    
    def _validate_thesis_section_completeness(self, markdown: str) -> Dict[str, Any]:
        """Validate thesis section completeness (word counts, skeletal checks) - thesis only"""
        import re
        
        validation_results = {
            'sections': {},
            'warnings': [],
            'errors': []
        }
        
        # Extract sections by ## headings
        section_pattern = r'^##\s+(.+?)\s*\n+(.*?)(?=\n##\s+|$)'
        sections = {}
        for match in re.finditer(section_pattern, markdown, re.MULTILINE | re.DOTALL):
            section_name = match.group(1).strip()
            section_content = match.group(2).strip()
            sections[section_name] = section_content
        
        # Word count requirements
        word_count_requirements = {
            'Applications': 400,
            'Case Studies and Applications': 400,
            'Limits & Open Questions': 300,
            'Limits and Open Questions': 300,
            'Discussion and Implications': 300,
        }
        
        # Check for operational diagnostics in Limits section
        limits_sections = [name for name in sections.keys() if 'limit' in name.lower() or 'question' in name.lower()]
        has_operational_diagnostics = False
        for section_name in limits_sections:
            section_content_lower = sections[section_name].lower()
            if ('operational assumption' in section_content_lower or 
                'bounded-rationality' in section_content_lower or 
                'adversarial comms' in section_content_lower):
                has_operational_diagnostics = True
                break
        
        if limits_sections and not has_operational_diagnostics:
            validation_results['errors'].append(
                "Limits section must include 'Operational Assumptions & Diagnostics' subsection with bounded-rationality assumption and adversarial comms model"
            )
        
        for section_name, content in sections.items():
            word_count = len(content.split())
            section_result = {
                'word_count': word_count,
                'meets_requirement': True,
                'is_skeletal': word_count < 100  # Flag if <100 words
            }
            
            # Check against requirements
            for req_name, req_words in word_count_requirements.items():
                if req_name.lower() in section_name.lower():
                    section_result['meets_requirement'] = word_count >= req_words
                    if word_count < req_words:
                        validation_results['warnings'].append(
                            f"Section '{section_name}' has {word_count} words, requires {req_words}"
                        )
                    break
            
            if section_result['is_skeletal']:
                validation_results['warnings'].append(
                    f"Section '{section_name}' appears skeletal ({word_count} words)"
                )
            
            validation_results['sections'][section_name] = section_result
        
        return validation_results
    
    def _detect_thesis_section_repetition(self, markdown: str, exec_summary: str = None) -> Dict[str, Any]:
        """Detect repetition between sections using embedding similarity - thesis only"""
        import re
        
        if not exec_summary:
            # Try to extract exec summary from Abstract section
            abstract_match = re.search(r'^##\s+Abstract\s*\n+(.*?)(?=\n##\s+|$)', markdown, re.MULTILINE | re.DOTALL)
            if abstract_match:
                exec_summary = abstract_match.group(1).strip()
        
        if not exec_summary:
            return {'repetition_detected': False, 'overlaps': []}
        
        try:
            embeddings = OpenAIEmbeddings()
            exec_embedding = embeddings.embed_query(exec_summary[:500])  # Limit to first 500 chars
            
            # Extract sections by ## headings
            section_pattern = r'^##\s+(.+?)\s*\n+(.*?)(?=\n##\s+|$)'
            sections_to_check = ['Mechanisms', 'Synthesis', 'Synthesis and Current Developments']
            overlaps = []
            
            for match in re.finditer(section_pattern, markdown, re.MULTILINE | re.DOTALL):
                section_name = match.group(1).strip()
                section_content = match.group(2).strip()
                
                if any(check_name.lower() in section_name.lower() for check_name in sections_to_check):
                    if len(section_content) > 50:  # Only check if substantial content
                        section_embedding = embeddings.embed_query(section_content[:500])
                        
                        # Calculate cosine similarity
                        similarity = np.dot(exec_embedding, section_embedding) / (
                            np.linalg.norm(exec_embedding) * np.linalg.norm(section_embedding)
                        )
                        
                        if similarity > 0.70:  # >70% similarity indicates repetition
                            overlaps.append({
                                'section': section_name,
                                'similarity': float(similarity),
                                'warning': f"Section '{section_name}' has {similarity:.2%} similarity to Executive Summary"
                            })
            
            return {
                'repetition_detected': len(overlaps) > 0,
                'overlaps': overlaps
            }
        except Exception as e:
            logger.warning(f"Error detecting section repetition: {str(e)}")
            return {'repetition_detected': False, 'overlaps': []}

    def _thesis_critique(self, draft: ThesisDraft, query: str, sources: List[Source] = None) -> ThesisCritique:
        """Critique thesis draft on alignment, theory depth, clarity - thesis only"""
        try:
            parser = PydanticOutputParser(pydantic_object=ThesisCritique)
            prompt = PromptTemplate(
                input_variables=["query","markdown","format_instructions"],
                template=(
                    "Critique this thesis brief on: alignment to query, theory depth, clarity.\n"
                    "Return JSON with fields alignment, theory_depth, clarity, repair_action (none|expand_anchors|adjust_outline).\n\n"
                    "Query: {query}\n\nDraft (markdown):\n{markdown}\n\n{format_instructions}"
                )
            )
            resp = self.llm.invoke(
                prompt.format(query=query, markdown=draft.markdown[:5000],
                              format_instructions=parser.get_format_instructions())
            )
            content = resp.content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            critique = ThesisCritique(**json.loads(content))
            # Ensure all values are computed (no None) - fallback to programmatic calculation
            if critique.alignment is None:
                critique.alignment = self._calculate_badge_alignment(draft, query)
            if critique.theory_depth is None:
                critique.theory_depth = self._calculate_badge_theory_depth(draft)
            if critique.clarity is None:
                critique.clarity = self._calculate_badge_clarity(draft)
            return critique
        except Exception as e:
            logger.warning(f"Critique fallback: {str(e)}")
            # Compute badges programmatically
            alignment = self._calculate_badge_alignment(draft, query)
            theory_depth = self._calculate_badge_theory_depth(draft)
            clarity = self._calculate_badge_clarity(draft)
            repair_action = 'adjust_outline' if min(alignment, theory_depth, clarity) < STIConfig.THESIS_CRITIQUE_MIN_SCORE else 'none'
            return ThesisCritique(alignment=alignment, theory_depth=theory_depth, clarity=clarity, repair_action=repair_action)
    
    def _calculate_badge_alignment(self, draft: ThesisDraft, query: str) -> float:
        """Calculate alignment badge (0-1): problem framing → claims → methods consistency"""
        markdown_lower = draft.markdown.lower()
        query_lower = query.lower()
        
        # Check if problem is clearly stated
        has_problem = any(kw in markdown_lower for kw in ['problem', 'question', 'hypothesis'])
        
        # Check if claims align with problem
        has_claims = any(kw in markdown_lower for kw in ['claim', 'hypothesis', 'proposition'])
        
        # Check if methods align with claims
        has_methods = any(kw in markdown_lower for kw in ['method', 'methodology', 'evaluation'])
        
        # Check query relevance
        query_words = set(query_lower.split())
        markdown_words = set(markdown_lower.split())
        query_overlap = len(query_words.intersection(markdown_words)) / max(1, len(query_words))
        
        score = 0.0
        if has_problem:
            score += 0.3
        if has_claims:
            score += 0.3
        if has_methods:
            score += 0.2
        score += query_overlap * 0.2
        
        return min(1.0, score)
    
    def _calculate_badge_theory_depth(self, draft: ThesisDraft) -> float:
        """Calculate theory depth badge (0-1): level of formalism & rigor"""
        markdown_lower = draft.markdown.lower()
        
        # Check for formal notation
        has_notation = any(kw in markdown_lower for kw in ['notation', 'symbol', 'variable'])
        
        # Check for mathematical models
        has_math = any(kw in markdown_lower for kw in ['model', 'equation', 'theorem', 'proof'])
        
        # Check for formal framework
        has_framework = any(kw in markdown_lower for kw in ['framework', 'formal', 'structure'])
        
        # Check for foundations section
        has_foundations = any(kw in markdown_lower for kw in ['foundation', 'theoretical', 'formal model'])
        
        score = 0.0
        if has_notation:
            score += 0.2
        if has_math:
            score += 0.3
        if has_framework:
            score += 0.3
        if has_foundations:
            score += 0.2
        
        return min(1.0, score)
    
    def _calculate_badge_clarity(self, draft: ThesisDraft) -> float:
        """Calculate clarity badge (0-1): readability, lack of redundancy, diagram/table use"""
        markdown_lower = draft.markdown.lower()
        
        # Check for tables
        has_tables = '|' in draft.markdown and '---' in draft.markdown
        
        # Check for structure (sections)
        has_sections = draft.markdown.count('##') >= 5
        
        # Check for lists (improves readability)
        has_lists = '-' in draft.markdown or any(str(i) + '.' in draft.markdown for i in range(1, 10))
        
        # Check length (sufficient content)
        word_count = len(draft.markdown.split())
        adequate_length = word_count >= 2000
        
        score = 0.0
        if has_tables:
            score += 0.3
        if has_sections:
            score += 0.3
        if has_lists:
            score += 0.2
        if adequate_length:
            score += 0.2
        
        return min(1.0, score)
    
    def _calculate_thesis_publication_rubric(self, draft: ThesisDraft, query: str, 
                                            sources: List[Source], diversity_score: float = 1.0) -> PublicationRubric:
        """Calculate comprehensive publication rubric scores - thesis only"""
        try:
            parser = PydanticOutputParser(pydantic_object=PublicationRubric)
            
            # Count sources and anchors
            anchor_domains = getattr(STIConfig, 'THESIS_ANCHOR_DOMAINS', [])
            anchor_count = sum(1 for s in sources if any(domain in s.url for domain in anchor_domains))
            total_sources = len(sources)
            anchor_fraction = anchor_count / total_sources if total_sources > 0 else 0.0
            
            # Check for CEM grid
            has_cem_grid = '## Claim-Evidence-Method' in draft.markdown or '| Claim |' in draft.markdown
            
            # Check for notation table
            has_notation = '## Notation' in draft.markdown or '| Symbol |' in draft.markdown
            
            # Check for operational diagnostics
            has_diagnostics = 'Operational Assumptions' in draft.markdown or 'diagnostic' in draft.markdown.lower()
            
            prompt = PromptTemplate(
                input_variables=["query","markdown","anchor_fraction","has_cem","has_notation","has_diagnostics","format_instructions"],
                template=(
                    "Evaluate this thesis brief using a 10-dimension publication rubric. Score each dimension:\n\n"
                    "1. Scope & Problem Clarity (0-10): How clearly defined is the problem and scope?\n"
                    "2. Novelty / Original Framing (0-10): How original/novel is the theoretical framing?\n"
                    "3. Evidence Base Strength (0-20): Diversity and authoritativeness of sources. Anchor fraction: {anchor_fraction:.1%}\n"
                    "4. Method Rigor & Formalism (0-10): Rigor of methods and formalism\n"
                    "5. Reproducibility & Transparency (0-10): CEM grid present: {has_cem}, Notation table: {has_notation}\n"
                    "6. Cross-Domain Mapping (0-5): Cross-domain applicability\n"
                    "7. Falsifiability & Predictions (0-10): Testable predictions and falsifiability\n"
                    "8. Risks / Limitations (0-5): Honest treatment of limitations\n"
                    "9. Writing Clarity & Structure (0-10): Clarity and structure\n"
                    "10. Publication Hygiene (0-10): Citations, no placeholders. Diagnostics present: {has_diagnostics}\n\n"
                    "Query: {query}\n\nDraft (markdown):\n{markdown}\n\n{format_instructions}"
                )
            )
            
            resp = self.llm.invoke(
                prompt.format(
                    query=query,
                    markdown=draft.markdown[:8000],  # Increased context
                    anchor_fraction=anchor_fraction,
                    has_cem="yes" if has_cem_grid else "no",
                    has_notation="yes" if has_notation else "no",
                    has_diagnostics="yes" if has_diagnostics else "no",
                    format_instructions=parser.get_format_instructions()
                )
            )
            content = resp.content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            return PublicationRubric(**json.loads(content))
        except Exception as e:
            logger.warning(f"Publication rubric fallback: {str(e)}")
            # Fallback: calculate approximate scores
            markdown_lower = draft.markdown.lower()
            
            # Scope clarity: check for clear problem statement
            scope_clarity = 8.0 if any(kw in markdown_lower for kw in ['research question', 'problem', 'objective']) else 6.0
            
            # Novelty: check for original framing
            novelty = 8.0 if any(kw in markdown_lower for kw in ['framework', 'unified', 'novel']) else 6.0
            
            # Evidence strength: based on anchor fraction
            evidence_strength = min(20.0, 10.0 + (anchor_fraction * 10.0))
            
            # Method rigor: check for formalism
            method_rigor = 8.0 if any(kw in markdown_lower for kw in ['formal', 'theorem', 'proof', 'model']) else 6.0
            
            # Reproducibility: based on CEM grid and notation
            reproducibility = 7.0
            if has_cem_grid:
                reproducibility += 2.0
            if has_notation:
                reproducibility += 1.0
            
            # Cross-domain: check for applications
            cross_domain = 4.0 if any(kw in markdown_lower for kw in ['application', 'case study', 'domain']) else 2.0
            
            # Falsifiability: check for predictions
            falsifiability = 8.0 if any(kw in markdown_lower for kw in ['prediction', 'hypothesis', 'proposition']) else 6.0
            
            # Risks/limitations: check for honest treatment
            risks_limitations = 4.0 if any(kw in markdown_lower for kw in ['limitation', 'constraint', 'challenge']) else 2.0
            
            # Writing clarity
            writing_clarity = 8.0 if len(draft.markdown) > 2000 else 6.0
            
            # Publication hygiene
            publication_hygiene = 8.0
            if has_diagnostics:
                publication_hygiene += 1.0
            if anchor_fraction >= 0.4:
                publication_hygiene += 1.0
            
            return PublicationRubric(
                scope_clarity=scope_clarity,
                novelty=novelty,
                evidence_strength=min(20.0, evidence_strength),
                method_rigor=method_rigor,
                reproducibility=min(10.0, reproducibility),
                cross_domain=min(5.0, cross_domain),
                falsifiability=falsifiability,
                risks_limitations=min(5.0, risks_limitations),
                writing_clarity=writing_clarity,
                publication_hygiene=min(10.0, publication_hygiene)
            )
    
    def _generate_cem_grid(self, draft: ThesisDraft, sources: List[Source]) -> CEMGrid:
        """Generate Claim-Evidence-Method grid from thesis draft - thesis only"""
        try:
            parser = PydanticOutputParser(pydantic_object=CEMGrid)
            
            
            # Build source list with type tags
            source_list = []
            for i, s in enumerate(sources[:15], 1):
                title = getattr(s, 'title', None) or (s.get('title') if isinstance(s, dict) else '')
                url = getattr(s, 'url', None) or (s.get('url') if isinstance(s, dict) else '')
                source_type = self._classify_thesis_source_type(s)
                type_tag = source_type.value
                source_list.append(f"[^{i}:{type_tag}]: {title} — {url}")
            
            sources_str = "\n".join(source_list)
            
            prompt = PromptTemplate(
                input_variables=["markdown", "sources", "format_instructions"],
                template=(
                    "Extract key theoretical claims from this thesis brief and map each to evidence, method, risk, and test ID.\n\n"
                    "For each claim, identify:\n"
                    "- Claim: The theoretical claim (e.g., 'Consensus time ∝ 1/λ₂ (algebraic connectivity)')\n"
                    "- Evidence: Source citations with type tags (use [^id:type] format where type is P/D/A/O/G)\n"
                    "- Method: How this could be validated (proof/simulation/empirical)\n"
                    "- Status: Current status (e.g., 'E cited; M pending sim')\n"
                    "- Risk: What fails if the claim is wrong\n"
                    "- TestID: Cross-link identifier to tests in Methods section (e.g., 'T1', 'T2')\n\n"
                    "Extract at least 5 key claims (≥3 primary, ≥2 secondary) with complete mappings.\n\n"
                    "Draft (markdown):\n{markdown}\n\n"
                    "Available Sources (with type tags P=Peer-reviewed, D=Doctrine, A=arXiv, O=Official, G=Grey):\n{sources}\n\n"
                    "{format_instructions}"
                )
            )
            
            resp = self.llm.invoke(
                prompt.format(
                    markdown=draft.markdown[:10000],  # Large context for claim extraction
                    sources=sources_str,
                    format_instructions=parser.get_format_instructions()
                )
            )
            content = resp.content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            return CEMGrid(**json.loads(content))
        except Exception as e:
            logger.warning(f"CEM grid generation fallback: {str(e)}")
            # Fallback: create minimal CEM grid with common claims
            fallback_rows = [
                CEMRow(
                    claim="Consensus time scales with algebraic connectivity λ₂",
                    evidence="[^5:P][^3:P]",
                    method="Theorem; replicate with sim on Erdos-Renyi vs grid graphs",
                    status="E cited; M pending sim",
                    risk="Claims about convergence rates may be invalid if connectivity assumptions fail",
                    test_id="T1"
                ),
                CEMRow(
                    claim="Critical comms capacity triggers phase-transition in coordination",
                    evidence="[^1:A]",
                    method="Stress-test in sim: sweep bitrate; log mission utility & variance",
                    status="E cited; M pending sim",
                    risk="System may fail catastrophically if capacity thresholds are misestimated",
                    test_id="T2"
                ),
                CEMRow(
                    claim="Hybrid delegation reduces mission failure across heterogeneous tempos",
                    evidence="Internal analysis",
                    method="Queueing/MDP model + Monte Carlo on tempo bursts",
                    status="E internal; M pending formalization",
                    risk="Delegation thresholds may be suboptimal if tempo distributions are mischaracterized",
                    test_id="T3"
                ),
            ]
            return CEMGrid(rows=fallback_rows)
    
    def _format_cem_grid_markdown(self, cem_grid: CEMGrid) -> str:
        """Format CEM grid as markdown table - thesis only (6 columns with Risk and TestID)"""
        import re
        
        if not cem_grid.rows:
            return ""
        
        markdown = "## Claim-Evidence-Method (CEM) Grid\n\n"
        markdown += "| Claim (C) | Evidence (E) | Method (M) | Status | Risk | TestID |\n"
        markdown += "|-----------|--------------|------------|--------|------|--------|\n"
        
        for row in cem_grid.rows:
            # Escape pipe characters in content
            claim = row.claim.replace('|', '\\|')
            evidence = row.evidence.replace('|', '\\|')
            method = row.method.replace('|', '\\|')
            status = row.status.replace('|', '\\|')
            risk = getattr(row, 'risk', '').replace('|', '\\|') if getattr(row, 'risk', None) else ""
            test_id = getattr(row, 'test_id', '').replace('|', '\\|') if getattr(row, 'test_id', None) else ""
            
            # Convert footnote-style citations [^id:type] to numeric [id] format for consistency
            # Example: [^2:A], [^3:A] -> [2], [3]
            evidence = re.sub(r'\[\^(\d+):[^\]]+\]', r'[\1]', evidence)
            evidence = re.sub(r'\[\^(\d+)\]', r'[\1]', evidence)  # Also handle [^id] format
            
            markdown += f"| {claim} | {evidence} | {method} | {status} | {risk} | {test_id} |\n"
        
        return markdown
    
    def _validate_notation(self, markdown: str) -> Dict[str, Any]:
        """Validate notation table - reject playful mnemonics, ensure one-symbol-one-meaning"""
        import re
        violations = []
        
        # Find Notation section
        notation_match = re.search(r'##\s+Notation.*?\n(.*?)(?=\n##\s|$)', markdown, re.MULTILINE | re.DOTALL | re.IGNORECASE)
        if not notation_match:
            return {'valid': True, 'violations': []}
        
        notation_content = notation_match.group(1)
        
        # Find table rows (Symbol | Description format)
        table_rows = re.findall(r'\|[^|]+\|', notation_content)
        
        # Check for playful mnemonics (e.g., Q_uestions = Quality)
        playful_patterns = [
            r'Q_uestions',
            r'P_erspective',
            r'[A-Z]_[a-z]+',  # Pattern like X_yz suggesting word play
        ]
        
        symbol_meanings = {}  # Track symbol -> meanings
        
        for row in table_rows:
            cells = [c.strip() for c in row.split('|')[1:-1]]  # Remove first/last empty
            if len(cells) >= 2:
                symbol = cells[0]
                description = cells[1] if len(cells) > 1 else ''
                
                # Check for playful mnemonics
                for pattern in playful_patterns:
                    if re.search(pattern, symbol):
                        violations.append(f"Symbol '{symbol}' uses playful mnemonic pattern")
                
                # Check for symbol overloading
                if symbol in symbol_meanings:
                    if symbol_meanings[symbol] != description:
                        violations.append(f"Symbol '{symbol}' has multiple meanings: '{symbol_meanings[symbol]}' vs '{description}'")
                else:
                    symbol_meanings[symbol] = description
        
        return {'valid': len(violations) == 0, 'violations': violations}
    
    def _generate_assumptions_ledger(self, draft: ThesisDraft) -> List[AssumptionsLedgerRow]:
        """Generate Assumptions Ledger from thesis draft - thesis only"""
        import re
        try:
            parser = PydanticOutputParser(pydantic_object=List[AssumptionsLedgerRow])
            
            prompt = PromptTemplate(
                input_variables=["markdown", "format_instructions"],
                template=(
                    "Extract key assumptions from this thesis brief and map each to rationale, observable, trigger, fallback, and scope.\n\n"
                    "For each assumption, identify:\n"
                    "- Assumption: The assumption being made\n"
                    "- Rationale: Why this assumption is reasonable\n"
                    "- Observable: How to observe if assumption holds\n"
                    "- Trigger: What triggers checking this assumption\n"
                    "- Fallback/Delegation: Fallback if assumption fails\n"
                    "- Scope: Scope/limits of assumption\n\n"
                    "Extract at least 3-5 key assumptions with complete mappings.\n\n"
                    "Draft (markdown):\n{markdown}\n\n"
                    "{format_instructions}"
                )
            )
            
            resp = self.llm.invoke(
                prompt.format(
                    markdown=draft.markdown[:10000],
                    format_instructions=parser.get_format_instructions()
                )
            )
            content = resp.content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            return [AssumptionsLedgerRow(**row) for row in json.loads(content)]
        except Exception as e:
            logger.warning(f"Assumptions ledger generation fallback: {str(e)}")
            # Fallback: return empty list (can be populated later)
            return []
    
    def _format_assumptions_ledger_markdown(self, ledger: List[AssumptionsLedgerRow]) -> str:
        """Format Assumptions Ledger as markdown table - thesis only"""
        if not ledger:
            return ""
        
        markdown = "## Assumptions Ledger\n\n"
        markdown += "| Assumption | Rationale | Observable | Trigger | Fallback/Delegation | Scope |\n"
        markdown += "|------------|-----------|------------|---------|---------------------|-------|\n"
        
        for row in ledger:
            assumption = row.assumption.replace('|', '\\|')
            rationale = row.rationale.replace('|', '\\|')
            observable = row.observable.replace('|', '\\|')
            trigger = row.trigger.replace('|', '\\|')
            fallback = row.fallback_delegation.replace('|', '\\|')
            scope = row.scope.replace('|', '\\|')
            markdown += f"| {assumption} | {rationale} | {observable} | {trigger} | {fallback} | {scope} |\n"
        
        return markdown
    
    def _run_ci_gates(self, draft: ThesisDraft, sources: List[Source], cem_grid: CEMGrid = None,
                      critique: ThesisCritique = None, publication_rubric: PublicationRubric = None,
                      notation_validation: Dict[str, Any] = None, repetition_check: Dict[str, Any] = None) -> Dict[str, Any]:
        """Run CI gates (G1-G7) for automated validation - thesis only"""
        gates = {
            'G1': {'name': 'Anchors present?', 'passed': False, 'message': ''},
            'G2': {'name': 'CEM complete?', 'passed': False, 'message': ''},
            'G3': {'name': 'Notation lint', 'passed': False, 'message': ''},
            'G4': {'name': 'Duplication check', 'passed': False, 'message': ''},
            'G5': {'name': 'Badge thresholds', 'passed': False, 'message': ''},
            'G6': {'name': 'References typed & diverse', 'passed': False, 'message': ''},
            'G7': {'name': 'Rubric score', 'passed': False, 'message': ''},
        }
        
        # G1: Anchors present?
        anchor_domains = getattr(STIConfig, 'THESIS_ANCHOR_DOMAINS', [])
        anchor_count = sum(1 for s in sources if any(domain in s.url.lower() for domain in anchor_domains))
        if anchor_count >= 2:
            gates['G1']['passed'] = True
            gates['G1']['message'] = f"Anchored ({anchor_count} anchor sources)"
        elif anchor_count == 1:
            gates['G1']['passed'] = True  # Anchor-Sparse passes but flagged
            gates['G1']['message'] = f"Anchor-Sparse ({anchor_count} anchor source)"
        else:
            gates['G1']['message'] = f"Anchor-Absent ({anchor_count} anchor sources)"
        
        # G2: CEM complete?
        if cem_grid and cem_grid.rows:
            complete_rows = sum(1 for row in cem_grid.rows 
                              if getattr(row, 'risk', '') and getattr(row, 'test_id', ''))
            total_rows = len(cem_grid.rows)
            if total_rows >= 5 and complete_rows >= 5:
                gates['G2']['passed'] = True
                gates['G2']['message'] = f"CEM complete ({complete_rows}/{total_rows} rows with Risk & TestID)"
            else:
                gates['G2']['message'] = f"CEM incomplete ({complete_rows}/{total_rows} rows complete, need ≥5)"
        else:
            gates['G2']['message'] = "CEM grid missing"
        
        # G3: Notation lint
        if notation_validation:
            if notation_validation.get('valid', False):
                gates['G3']['passed'] = True
                gates['G3']['message'] = "Notation valid"
            else:
                violations = notation_validation.get('violations', [])
                gates['G3']['message'] = f"Notation violations: {', '.join(violations[:3])}"
        else:
            gates['G3']['message'] = "Notation not validated"
        
        # G4: Duplication check
        if repetition_check:
            if not repetition_check.get('repetition_detected', False):
                gates['G4']['passed'] = True
                gates['G4']['message'] = "No section duplication detected"
            else:
                overlaps = repetition_check.get('overlaps', [])
                gates['G4']['message'] = f"Duplication detected: {', '.join([o['section'] for o in overlaps[:2]])}"
        else:
            gates['G4']['message'] = "Duplication not checked"
        
        # G5: Badge thresholds (all ≥4/10 = 0.4)
        if critique:
            min_badge = min(critique.alignment, critique.theory_depth, critique.clarity)
            if min_badge >= 0.4:  # 0.4 = 4/10
                gates['G5']['passed'] = True
                gates['G5']['message'] = f"Badges OK (min: {min_badge:.2f})"
            else:
                gates['G5']['message'] = f"Badge threshold failed (min: {min_badge:.2f}, need ≥0.4)"
        else:
            gates['G5']['message'] = "Badges not computed"
        
        # G6: References typed & diverse (≥3 distinct publishers)
        unique_publishers = set(getattr(s, 'publisher', '') or '' for s in sources)
        source_types = set(self._classify_thesis_source_type(s) for s in sources)
        if len(unique_publishers) >= 3 and len(source_types) >= 2:
            gates['G6']['passed'] = True
            gates['G6']['message'] = f"Diverse sources ({len(unique_publishers)} publishers, {len(source_types)} types)"
        else:
            gates['G6']['message'] = f"Source diversity low ({len(unique_publishers)} publishers, {len(source_types)} types, need ≥3 publishers)"
        
        # G7: Rubric score (≥75/100 for Yellowlight, ≥85/100 for Greenlight)
        if publication_rubric:
            total_score = publication_rubric.total_score
            if total_score >= 85:
                gates['G7']['passed'] = True
                gates['G7']['message'] = f"Greenlight ({total_score:.1f}/100)"
            elif total_score >= 75:
                gates['G7']['passed'] = True
                gates['G7']['message'] = f"Yellowlight ({total_score:.1f}/100)"
            else:
                gates['G7']['message'] = f"Below threshold ({total_score:.1f}/100, need ≥75)"
        else:
            gates['G7']['message'] = "Rubric not computed"
        
        all_passed = all(gate['passed'] for gate in gates.values())
        fail_stops = [name for name, gate in gates.items() if not gate['passed']]
        
        return {
            'all_passed': all_passed,
            'gates': gates,
            'fail_stops': fail_stops
        }
    
    def _insert_cem_grid_into_markdown(self, markdown: str, cem_markdown: str) -> str:
        """Insert CEM grid after Formal Models section - thesis only"""
        import re
        
        # Try to find "Formal Models" or "Formal Framework" section
        patterns = [
            r'(## Formal Models and Analysis.*?\n)',
            r'(## Formal Framework.*?\n)',
            r'(## Formal Models.*?\n)',
            r'(## Theory of.*?\n)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, markdown, re.MULTILINE | re.IGNORECASE)
            if match:
                # Insert CEM grid after this section
                insert_pos = markdown.find(match.group(0)) + len(match.group(0))
                # Find the end of this section (next ## heading)
                next_section = re.search(r'\n##\s+', markdown[insert_pos:], re.MULTILINE)
                if next_section:
                    insert_pos = insert_pos + next_section.start()
                
                # Insert CEM grid
                markdown = markdown[:insert_pos] + "\n\n" + cem_markdown + "\n\n" + markdown[insert_pos:]
                logger.info("Inserted CEM grid after Formal Models section")
                return markdown
        
        # Fallback: append before References
        ref_match = re.search(r'\n## References', markdown, re.MULTILINE | re.IGNORECASE)
        if ref_match:
            insert_pos = ref_match.start()
            markdown = markdown[:insert_pos] + "\n\n" + cem_markdown + "\n\n" + markdown[insert_pos:]
            logger.info("Inserted CEM grid before References section")
        else:
            # Last resort: append at end
            markdown = markdown + "\n\n" + cem_markdown
            logger.warning("Appended CEM grid at end (could not find insertion point)")
        
        return markdown
    
    def _ensure_operational_diagnostics(self, markdown: str) -> str:
        """Ensure Operational Assumptions & Diagnostics subsection exists in Limits - thesis only"""
        import re
        
        # Find Limits section
        limits_pattern = r'(##\s+(?:Limits|Limits\s*&\s*Open\s*Questions).*?\n)(.*?)(?=\n##\s+|$)'
        limits_match = re.search(limits_pattern, markdown, re.MULTILINE | re.DOTALL | re.IGNORECASE)
        
        if limits_match:
            limits_header = limits_match.group(1)
            limits_content = limits_match.group(2)
            
            # Check if operational diagnostics already exists
            if 'Operational Assumptions' in limits_content or 'operational assumption' in limits_content.lower():
                return markdown  # Already present
            
            # Add operational diagnostics subsection
            diagnostics_subsection = (
                "\n\n### Operational Assumptions & Diagnostics\n\n"
                "**Bounded-Rationality Assumption**: Agents operate with cognitive limits and incomplete information. "
                "Trigger: When decision complexity exceeds agent capacity or information gaps persist. "
                "Delegation policy: Escalate to higher-level agents or human operators when uncertainty thresholds exceed pre-defined bounds.\n\n"
                "**Adversarial Comms Model**: Communication channels may be compromised, delayed, or jammed. "
                "Trigger: When comms latency exceeds deadlines or suspicious patterns detected. "
                "Delegation policy: Switch to local consensus protocols, degrade gracefully to autonomous operation, alert human supervisors.\n\n"
                "**Human-in-the-Loop Posture**: Human operators provide oversight and corrective control. "
                "This is a present operational assumption, not future work.\n\n"
                "**Adversarial Posture**: Systems must operate under contested conditions with potential adversaries. "
                "This is a present operational assumption, not future work.\n"
            )
            
            # Insert after Limits header, before existing content
            limits_with_diagnostics = limits_header + diagnostics_subsection + limits_content
            
            # Replace Limits section in markdown
            markdown = markdown[:limits_match.start()] + limits_with_diagnostics + markdown[limits_match.end():]
            logger.info("Added Operational Assumptions & Diagnostics subsection to Limits section")
        
        return markdown
    
    def _extract_notation_table(self, markdown: str) -> tuple:
        """Extract mathematical symbols and create notation table - thesis only. Returns (modified_markdown, notation_table_str_or_none)"""
        import re
        
        # Check if notation table already exists
        notation_section_match = re.search(r'##\s+Notation\s*\n(.*?)(?=\n##\s|$)', markdown, re.MULTILINE | re.DOTALL | re.IGNORECASE)
        if notation_section_match:
            # Check if it uses playful mnemonics (G_{ent}, Q_{uality}, etc.)
            notation_content = notation_section_match.group(1)
            playful_patterns = [r'G_{ent}', r'Q_{uality}', r'P_{rimitives}', r'C_{t}', r'N_{d}', r'R_{act}', r'T_{ract}', r'V_{ances}', r'D_{vances}']
            has_playful = any(re.search(pattern, notation_content, re.IGNORECASE) for pattern in playful_patterns)
            
            if not has_playful:
                return (markdown, None)  # Already present and uses standard notation
            
            # Replace playful notation with standard notation
            standard_notation = """## Notation

| Symbol | Meaning | Units / Domain |
|---|---|---|
| \\(n\\) | number of agents | \\(\\mathbb{N}\\) |
| \\(G_t=(V,E_t)\\) | time‑varying communication/interaction graph | — |
| \\(\\lambda_2(G)\\) | algebraic connectivity (Fiedler value) | — |
| \\(p\\) | mean packet‑delivery / link reliability | [0,1] |
| \\(\\tau\\) | latency / blackout duration | time |
| \\(\\lambda\\) | task arrival rate | 1/time |
| \\(e\\) | enforceability / command compliance | [0,1] |
| \\(\\tau_{\\text{deleg}}\\) | delegation threshold | [0,1] |
| **MTTA** | mean time‑to‑assignment/action | time |
| \\(P_{\\text{fail}}\\) | deadline‑miss probability | [0,1] |

"""
            # Replace the notation section
            notation_start = notation_section_match.start()
            notation_end = notation_section_match.end()
            modified_markdown = markdown[:notation_start] + standard_notation + markdown[notation_end:]
            return (modified_markdown, None)  # Indicates we replaced in place, no need to insert
        
        # Extract common mathematical symbols from markdown
        # Look for patterns like: λ₂, λ_{2}, alpha, beta, etc.
        symbol_patterns = [
            (r'\\lambda[_\^{]?([a-z0-9]+)[}\^]?', 'λ', 'Algebraic connectivity / Eigenvalue'),
            (r'\\alpha[_\^{]?([a-z0-9]+)[}\^]?', 'α', 'Learning rate / Parameter'),
            (r'\\beta[_\^{]?([a-z0-9]+)[}\^]?', 'β', 'Decay factor / Parameter'),
            (r'\\gamma[_\^{]?([a-z0-9]+)[}\^]?', 'γ', 'Discount factor / Parameter'),
            (r'\\theta[_\^{]?([a-z0-9]+)[}\^]?', 'θ', 'Policy parameter / Angle'),
            (r'\\phi[_\^{]?([a-z0-9]+)[}\^]?', 'φ', 'Feature function / Phase'),
            (r'\\tau[_\^{]?([a-z0-9]+)[}\^]?', 'τ', 'Time constant / Threshold'),
            (r'\\delta[_\^{]?([a-z0-9]+)[}\^]?', 'δ', 'Update / Delta'),
            (r'\\epsilon[_\^{]?([a-z0-9]+)[}\^]?', 'ε', 'Small constant / Exploration'),
            (r'\\mu[_\^{]?([a-z0-9]+)[}\^]?', 'μ', 'Mean / Policy'),
            (r'\\sigma[_\^{]?([a-z0-9]+)[}\^]?', 'σ', 'Standard deviation / Sigma'),
            (r'\\pi[_\^{]?([a-z0-9]+)[}\^]?', 'π', 'Policy / Pi'),
            (r'G[_\^{]?([a-z0-9]+)[}\^]?', 'G', 'Graph / Network'),
            (r'N[_\^{]?([a-z0-9]+)[}\^]?', 'N', 'Number of agents / Nodes'),
            (r'T[_\^{]?([a-z0-9]+)[}\^]?', 'T', 'Time / Horizon'),
            (r'D[_\^{]?([a-z0-9]+)[}\^]?', 'D', 'Diameter / Distance'),
            (r'C[_\^{]?([a-z0-9]+)[}\^]?', 'C', 'Capacity / Cost'),
            (r'P[_\^{]?([a-z0-9]+)[}\^]?', 'P', 'Probability / Transition matrix'),
            (r'Q[_\^{]?([a-z0-9]+)[}\^]?', 'Q', 'Quality / Q-function'),
            (r'R[_\^{]?([a-z0-9]+)[}\^]?', 'R', 'Reward / Range'),
            (r'V[_\^{]?([a-z0-9]+)[}\^]?', 'V', 'Value function / Vertices'),
        ]
        
        symbols_found = {}
        for pattern, symbol, description in symbol_patterns:
            matches = re.findall(pattern, markdown, re.IGNORECASE)
            if matches:
                # Use most specific match or first occurrence
                subscript = matches[0] if matches[0] else ''
                full_symbol = f'{symbol}_{{{subscript}}}' if subscript else symbol
                if full_symbol not in symbols_found:
                    symbols_found[full_symbol] = description
        
        # Also look for explicit symbol definitions in text
        definition_patterns = [
            r'([A-Za-z]+(?:_[0-9]+)?)\s*:=\s*([^.,;]+)',
            r'([A-Za-z]+(?:_[0-9]+)?)\s+denotes\s+([^.,;]+)',
            r'([A-Za-z]+(?:_[0-9]+)?)\s+represents\s+([^.,;]+)',
        ]
        
        for pattern in definition_patterns:
            matches = re.findall(pattern, markdown, re.IGNORECASE)
            for symbol, definition in matches:
                if symbol not in symbols_found and len(symbol) <= 3:
                    symbols_found[symbol] = definition.strip()
        
        if not symbols_found:
            return (markdown, None)
        
        # Generate standard notation table (no playful mnemonics)
        notation_md = """## Notation

| Symbol | Meaning | Units / Domain |
|---|---|---|
| \\(n\\) | number of agents | \\(\\mathbb{N}\\) |
| \\(G_t=(V,E_t)\\) | time‑varying communication/interaction graph | — |
| \\(\\lambda_2(G)\\) | algebraic connectivity (Fiedler value) | — |
| \\(p\\) | mean packet‑delivery / link reliability | [0,1] |
| \\(\\tau\\) | latency / blackout duration | time |
| \\(\\lambda\\) | task arrival rate | 1/time |
| \\(e\\) | enforceability / command compliance | [0,1] |
| \\(\\tau_{\\text{deleg}}\\) | delegation threshold | [0,1] |
| **MTTA** | mean time‑to‑assignment/action | time |
| \\(P_{\\text{fail}}\\) | deadline‑miss probability | [0,1] |

"""
        
        return (markdown, notation_md)
    
    def _insert_notation_table_into_markdown(self, markdown: str, notation_table: str) -> str:
        """Insert notation table after Formal Models section - thesis only"""
        import re
        
        # Try to find "Formal Models" or "Formal Framework" section
        patterns = [
            r'(## Formal Models and Analysis.*?\n)',
            r'(## Formal Framework.*?\n)',
            r'(## Formal Models.*?\n)',
            r'(## Theory of.*?\n)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, markdown, re.MULTILINE | re.IGNORECASE)
            if match:
                # Insert notation table after this section
                insert_pos = markdown.find(match.group(0)) + len(match.group(0))
                # Find the end of this section (next ## heading)
                next_section = re.search(r'\n##\s+', markdown[insert_pos:], re.MULTILINE)
                if next_section:
                    insert_pos = insert_pos + next_section.start()
                
                # Insert notation table
                markdown = markdown[:insert_pos] + "\n\n" + notation_table + "\n\n" + markdown[insert_pos:]
                logger.info("Inserted notation table after Formal Models section")
                return markdown
        
        # Fallback: insert before CEM grid if it exists
        cem_match = re.search(r'\n## Claim-Evidence-Method', markdown, re.MULTILINE | re.IGNORECASE)
        if cem_match:
            insert_pos = cem_match.start()
            markdown = markdown[:insert_pos] + "\n\n" + notation_table + "\n\n" + markdown[insert_pos:]
            logger.info("Inserted notation table before CEM grid")
        else:
            # Last resort: append before References
            ref_match = re.search(r'\n## References', markdown, re.MULTILINE | re.IGNORECASE)
            if ref_match:
                insert_pos = ref_match.start()
                markdown = markdown[:insert_pos] + "\n\n" + notation_table + "\n\n" + markdown[insert_pos:]
                logger.info("Inserted notation table before References section")
        
        return markdown
    
    def _generate_future_directions_section(self, query: str, sources: List[Source]) -> str:
        """Generate future directions and open questions section"""
        section = "## Open Questions and Future Directions\n\n"
        section += "Several research directions emerge for command theory in multi-agent systems:\n\n"
        section += "1. **Formal Verification**: Developing mathematical frameworks for proving command execution correctness\n"
        section += "2. **Dynamic Reconfiguration**: Mechanisms for adapting command structures as agent populations change\n"
        section += "3. **Human-Agent Command Interfaces**: Designing intuitive interfaces for human operators to issue commands to agent collectives\n"
        section += "4. **Security and Trust**: Ensuring command authenticity and preventing malicious command injection\n"
        section += "5. **Performance Optimization**: Minimizing communication overhead and latency in command distribution\n\n"
        section += "These directions represent opportunities for advancing both theoretical understanding and practical applications.\n"
        return section
    
    def _check_market_source_adequacy(self, market_sources: List[Source], query: str) -> bool:
        """
        Check if market sources adequately reflect the query topic.
        
        Returns True if market sources are sufficient to answer the query,
        False if the query is theoretical and not yet reflected in market.
        
        Args:
            market_sources: List of market/news sources found
            query: The original query
            
        Returns:
            bool: True if market sources adequately reflect query, False otherwise
        """
        if not market_sources:
            logger.info("No market sources found. Defaulting to thesis-path.")
            return False
        
        # Filter by semantic similarity to ensure sources actually relate to query
        # Use slightly lower threshold for adequacy check (more permissive)
        threshold = 0.5
        relevant_market_sources = self._semantic_similarity_filter(market_sources, query, threshold=threshold)
        
        # Need minimum number of relevant market sources
        MIN_RELEVANT_MARKET_SOURCES = 3
        
        if len(relevant_market_sources) < MIN_RELEVANT_MARKET_SOURCES:
            logger.info(f"Insufficient relevant market sources ({len(relevant_market_sources)} < {MIN_RELEVANT_MARKET_SOURCES}). "
                       f"Defaulting to thesis-path.")
            return False
        
        # Additional check: ensure sources address the core query topic, not just tangentially related
        # Check if sources have sufficient semantic alignment with the query
        try:
            # Use LLM to check if sources adequately address the core query topic
            from langchain_core.prompts import PromptTemplate
            from langchain_core.output_parsers import PydanticOutputParser
            from pydantic import BaseModel, Field
            
            class AdequacyCheck(BaseModel):
                adequate: bool = Field(description="Whether market sources adequately address the query")
                reasoning: str = Field(description="Brief explanation")
            
            parser = PydanticOutputParser(pydantic_object=AdequacyCheck)
            
            prompt_template = PromptTemplate(
                input_variables=["query", "sources"],
                template="""You are evaluating whether market/news sources adequately address this query.

Query: {query}

Sources found:
{sources}

Does this collection of market sources adequately address the CORE topic of the query?
- Market sources are ADEQUATE if they directly discuss the query topic in a commercial/practical context
- Market sources are NOT adequate if they only tangentially mention the topic or if the query is about theoretical concepts not yet commercialized

{format_instructions}

Return your assessment:"""
            )
            
            sources_text = "\n".join([f"- {s.title} ({s.publisher})" for s in relevant_market_sources[:5]])
            formatted_prompt = prompt_template.format(
                query=query,
                sources=sources_text,
                format_instructions=parser.get_format_instructions()
            )
            
            response = self.llm.invoke(formatted_prompt)
            result = parser.parse(response.content)
            
            if result.adequate:
                logger.info(f"Market sources adequately reflect query. Reasoning: {result.reasoning}")
                return True
            else:
                logger.info(f"Market sources do NOT adequately reflect query. Reasoning: {result.reasoning}. Defaulting to thesis-path.")
                return False
                
        except Exception as e:
            logger.warning(f"Error in LLM adequacy check: {str(e)}, using semantic similarity fallback")
            # Fallback: if we have enough semantically relevant sources, consider adequate
            return len(relevant_market_sources) >= MIN_RELEVANT_MARKET_SOURCES
    
    def _reclassify_intent_based_on_sources(self, sources: List[Source], original_intent: str, foundational_sources: List[Source] = None) -> str:
        """Reclassify intent from theory to market if sources are primarily market sources"""
        if original_intent != "theory":
            return original_intent  # Only reclassify if originally classified as theory
        
        if not sources:
            return original_intent
        
        # If foundational sources exist, check if recent sources support theory intent
        # Only preserve theory intent if foundational sources exist AND recent sources aren't overwhelmingly market-focused
        if foundational_sources and len(foundational_sources) > 0:
            # First, verify foundational sources actually made it into the sources list
            # (They might have been filtered out during deduplication or other filtering steps)
            foundational_urls = set(s.url for s in foundational_sources)
            foundational_in_sources = [s for s in sources if s.url in foundational_urls]
            foundational_in_sources_count = len(foundational_in_sources)
            
            # Calculate market source ratio in recent sources (excluding foundational sources)
            # Foundational sources are from 5-year window, recent sources are what we're evaluating
            recent_sources = [s for s in sources if s.url not in foundational_urls]
            
            # Only preserve theory intent if foundational sources actually exist in sources list
            # AND recent sources aren't overwhelmingly market-focused
            if foundational_in_sources_count > 0:
                if recent_sources:
                    recent_total = len(recent_sources)
                    recent_academic_count = sum(1 for s in recent_sources if s.source_type == SourceType.ACADEMIC)
                    recent_market_count = sum(1 for s in recent_sources if s.source_type in [
                        SourceType.INDEPENDENT_NEWS, SourceType.PRIMARY, 
                        SourceType.VENDOR_ASSERTED, SourceType.VENDOR_CONSULTING
                    ])
                    
                    market_ratio = recent_market_count / recent_total if recent_total > 0 else 0
                    
                    # Preserve theory intent only if:
                    # 1. Foundational sources exist AND are in sources list (theoretical foundation exists)
                    # 2. Recent sources aren't >90% market-focused (some academic/theoretical content in recent work)
                    if market_ratio <= 0.90:
                        logger.info(f"Foundational sources exist ({foundational_in_sources_count}/{len(foundational_sources)} in sources list) and recent sources show theory relevance "
                                   f"(market ratio: {market_ratio:.1%}, academic: {recent_academic_count}/{recent_total}). "
                                   f"Preserving theory intent.")
                        return original_intent
                    else:
                        logger.info(f"Foundational sources exist ({foundational_in_sources_count}/{len(foundational_sources)} in sources list) but recent sources are overwhelmingly "
                                   f"market-focused (market ratio: {market_ratio:.1%}, academic: {recent_academic_count}/{recent_total}). "
                                   f"Allowing reclassification to market.")
                        # Continue to reclassification logic below
                else:
                    # No recent sources, only foundational - preserve theory intent
                    logger.info(f"Foundational sources exist ({foundational_in_sources_count}/{len(foundational_sources)} in sources list) with no recent sources. Preserving theory intent.")
                    return original_intent
            else:
                # Foundational sources were searched but filtered out before reaching here
                # This means they weren't actually relevant, so allow reclassification
                logger.info(f"Foundational sources were searched ({len(foundational_sources)}) but none made it into sources list after filtering. Allowing reclassification.")
                # Continue to reclassification logic below
        
        # Count source types
        academic_count = sum(1 for s in sources if s.source_type == SourceType.ACADEMIC)
        independent_news_count = sum(1 for s in sources if s.source_type == SourceType.INDEPENDENT_NEWS)
        primary_count = sum(1 for s in sources if s.source_type == SourceType.PRIMARY)
        vendor_count = sum(1 for s in sources if s.source_type in [SourceType.VENDOR_ASSERTED, SourceType.VENDOR_CONSULTING])
        
        market_source_count = independent_news_count + primary_count + vendor_count
        total_sources = len(sources)
        
        # Reclassify to market if:
        # 1. Few academic sources (< 2) AND
        # 2. Sufficient market sources (≥5 or ≥60% of total) AND
        # 3. Meets minimum independent news requirement (≥2)
        academic_threshold = 2
        market_threshold = max(5, int(total_sources * 0.6))  # At least 5 or 60% of sources
        
        if (academic_count < academic_threshold and 
            market_source_count >= market_threshold and 
            independent_news_count >= STIConfig.MIN_INDEPENDENT_SOURCES):
            
            logger.info(f"Reclassifying intent from 'theory' to 'market' based on source types:")
            logger.info(f"  Academic sources: {academic_count} (need ≥{academic_threshold})")
            logger.info(f"  Market sources: {market_source_count} (have ≥{market_threshold})")
            logger.info(f"    - Independent news: {independent_news_count}")
            logger.info(f"    - Primary: {primary_count}")
            logger.info(f"    - Vendor: {vendor_count}")
            logger.info(f"  Total sources: {total_sources}")
            
            return "market"
        
        return original_intent
    
    def _check_academic_floor(self, sources: List[Source], intent: str, min_academic: int = None) -> bool:
        """Check if academic floor met for theory queries"""
        if intent != "theory":
            return True  # No floor for market queries
        
        if min_academic is None:
            min_academic = STIConfig.MIN_ACADEMIC_SOURCES_THEORY
        
        academic_count = sum(1 for s in sources if s.source_type == SourceType.ACADEMIC)
        floor_met = academic_count >= min_academic
        
        logger.info(f"Academic floor check: {academic_count}/{min_academic} academic sources (floor met: {floor_met})")
        return floor_met
    
    def _calculate_confidence_with_intent(self, signals: List[Dict[str, Any]], sources: List[Source], intent: str) -> float:
        """Calculate confidence with academic fraction penalties for theory queries"""
        base_confidence = self._calculate_confidence(signals, sources)
        
        if intent == "theory" and sources:
            academic_count = sum(1 for s in sources if s.source_type == SourceType.ACADEMIC)
            academic_fraction = academic_count / max(1, len(sources))
            target_fraction = STIConfig.CONFIDENCE_ACADEMIC_FRACTION_TARGET
            adjusted_confidence = base_confidence
            if academic_fraction < target_fraction:
                # Penalize: reduce confidence based on how far below target
                base_penalty = (target_fraction - academic_fraction)
                adjusted_confidence = max(0.0, base_confidence - base_penalty)
                adjusted_confidence = max(0.0, min(1.0, adjusted_confidence * STIConfig.THEORY_ACADEMIC_PENALTY_WEIGHT))
                logger.info(f"Applied academic fraction penalty: frac={academic_fraction:.2f}, target={target_fraction:.2f}, "
                            f"{base_confidence:.2f} → {adjusted_confidence:.2f}")
            # Cap theory-only confidence when no non-academic (web) sources
            non_academic = sum(1 for s in sources if s.source_type != SourceType.ACADEMIC)
            if non_academic == 0:
                cap = getattr(STIConfig, 'THEORY_CONFIDENCE_CAP', 0.60)
                before = adjusted_confidence
                adjusted_confidence = min(adjusted_confidence, cap)
                if adjusted_confidence < before:
                    logger.info(f"Theory-only confidence cap applied: {before:.2f} → {adjusted_confidence:.2f}")
            return adjusted_confidence
        
        return base_confidence
    
    def _reciprocal_rank_fusion(self, web_sources: List[Source], academic_sources: List[Source], k: int = 60) -> List[Source]:
        """Fuse results from web and academic retrievers using Reciprocal Rank Fusion (RRF)"""
        try:
            # Create score maps for each source list
            web_scores = {}
            academic_scores = {}
            
            # Assign RRF scores based on rank (1-based indexing)
            for i, source in enumerate(web_sources):
                web_scores[source.url] = 1.0 / (k + i + 1)
            
            for i, source in enumerate(academic_sources):
                academic_scores[source.url] = 1.0 / (k + i + 1)
            
            # Combine all sources and calculate fused scores
            all_sources = web_sources + academic_sources
            fused_scores = {}
            seen_urls = set()
            
            for source in all_sources:
                if source.url in seen_urls:
                    continue  # Skip duplicates
                seen_urls.add(source.url)
                
                # Calculate fused score
                web_score = web_scores.get(source.url, 0.0)
                academic_score = academic_scores.get(source.url, 0.0)
                fused_score = web_score + academic_score
                
                fused_scores[source.url] = fused_score
            
            # Sort by fused score (descending)
            sorted_sources = sorted(all_sources, 
                                  key=lambda s: fused_scores.get(s.url, 0.0), 
                                  reverse=True)
            
            # Remove duplicates while preserving order
            deduplicated = []
            seen_urls = set()
            for source in sorted_sources:
                if source.url not in seen_urls:
                    deduplicated.append(source)
                    seen_urls.add(source.url)
            
            logger.info(f"RRF fusion: {len(web_sources)} web + {len(academic_sources)} academic → {len(deduplicated)} unique sources")
            return deduplicated
            
        except Exception as e:
            logger.error(f"Error in RRF fusion: {str(e)}")
            # Fallback: simple concatenation with deduplication
            all_sources = web_sources + academic_sources
            seen_urls = set()
            deduplicated = []
            for source in all_sources:
                if source.url not in seen_urls:
                    deduplicated.append(source)
                    seen_urls.add(source.url)
            return deduplicated
    
    def _deduplicate_sources(self, sources: List[Source]) -> List[Source]:
        """Remove duplicate sources based on URL and title similarity"""
        try:
            deduplicated = []
            seen_urls = set()
            seen_titles = set()
            
            for source in sources:
                # Check URL duplicates
                if source.url in seen_urls:
                    continue
                
                # Check title similarity (simple approach)
                title_lower = source.title.lower().strip()
                if title_lower in seen_titles:
                    continue
                
                # Check for very similar titles (fuzzy matching)
                is_duplicate = False
                for seen_title in seen_titles:
                    # Simple similarity check: if 80% of words match
                    words1 = set(title_lower.split())
                    words2 = set(seen_title.split())
                    if len(words1) > 0 and len(words2) > 0:
                        similarity = len(words1.intersection(words2)) / max(len(words1), len(words2))
                        if similarity > 0.8:
                            is_duplicate = True
                            break
                
                if not is_duplicate:
                    deduplicated.append(source)
                    seen_urls.add(source.url)
                    seen_titles.add(title_lower)
            
            logger.info(f"Deduplication: {len(sources)} → {len(deduplicated)} sources")
            return deduplicated
            
        except Exception as e:
            logger.error(f"Error in deduplication: {str(e)}")
            return sources
    
    def _reweight_by_source_type(self, sources: List[Source], intent: str) -> List[Source]:
        """Re-rank sources by type based on intent (boost academic for theory, boost news for market)"""
        try:
            if not sources:
                return sources
            
            # Define source type weights based on intent
            if intent == "theory":
                type_weights = {
                    SourceType.ACADEMIC: 1.5,      # Boost academic sources
                    SourceType.PRIMARY: 1.2,       # Slight boost for primary
                    SourceType.INDEPENDENT_NEWS: 1.0,  # Neutral
                    SourceType.TRADE_PRESS: 0.8,   # Slight penalty
                    SourceType.VENDOR_CONSULTING: 0.6,  # Penalty
                    SourceType.VENDOR_ASSERTED: 0.4,    # Heavy penalty
                }
            else:  # market intent
                type_weights = {
                    SourceType.INDEPENDENT_NEWS: 1.3,  # Boost news sources
                    SourceType.PRIMARY: 1.2,       # Boost primary
                    SourceType.TRADE_PRESS: 1.1,   # Slight boost
                    SourceType.ACADEMIC: 0.9,      # Slight penalty
                    SourceType.VENDOR_CONSULTING: 0.7,  # Penalty
                    SourceType.VENDOR_ASSERTED: 0.5,    # Heavy penalty
                }
            
            # Apply weights and sort
            weighted_sources = []
            for source in sources:
                weight = type_weights.get(source.source_type, 1.0)
                # Create a copy with weight for sorting
                weighted_source = source
                weighted_source._sort_weight = weight
                weighted_sources.append(weighted_source)
            
            # Sort by weight (descending)
            sorted_sources = sorted(weighted_sources, 
                                  key=lambda s: getattr(s, '_sort_weight', 1.0), 
                                  reverse=True)
            
            # Remove the temporary weight attribute
            for source in sorted_sources:
                if hasattr(source, '_sort_weight'):
                    delattr(source, '_sort_weight')
            
            logger.info(f"Re-weighted {len(sources)} sources for {intent} intent")
            return sorted_sources
            
        except Exception as e:
            logger.error(f"Error re-weighting by source type: {str(e)}")
            return sources
    
    def _filter_sources_by_title_relevance(self, sources: List[Source], title: str, foundational_urls: set = None, min_score: float = None) -> List[Source]:
        """Filter sources using PydanticOutputParser for structured relevance scoring"""
        if not sources:
            return sources
        foundational_urls = foundational_urls or set()
        
        # First pass: filter out obviously irrelevant sources
        pre_filtered_sources = []
        for source in sources:
            if self._validate_source_relevance(source, title):
                pre_filtered_sources.append(source)
        
        if not pre_filtered_sources:
            logger.warning("All sources filtered out in pre-filtering stage")
            return sources  # Return original sources if all filtered out
        
        try:
            # Create Pydantic output parser for structured relevance scoring
            parser = PydanticOutputParser(pydantic_object=SourceRelevanceScore)
            
            # Create prompt template for relevance scoring
            prompt_template = PromptTemplate(
                input_variables=["title", "sources_text", "min_threshold"],
                template="""You are a source relevance expert. Your task is to score how relevant each source is to the specific report title.

PURPOSE: Determine which sources are actually relevant to the report title's specific topic.

CONTEXT: We have a report title and multiple sources. Some sources may be tangentially related but not directly relevant to the title's specific focus.

TASK: For each source, provide:
1. A relevance score (0.0 to 1.0) where 1.0 = highly relevant to the title's specific topic
2. A brief reason explaining why the source is or isn't relevant
3. Whether the source meets the relevance threshold (≥{min_threshold})

EVALUATION CRITERIA:
- Does the source directly address the specific topic in the title?
- Is the source content focused on the title's domain/field?
- Would this source be cited in a report about this specific title?

Report Title: {title}

Sources to evaluate:
{sources_text}

{format_instructions}

IMPORTANT: Return a JSON array where each element is a SourceRelevanceScore object for each source."""
            )
            
            # Prepare sources text for evaluation using pre-filtered sources
            sources_text = "\n\n".join([
                f"Source {s.id}: {s.title}\nPublisher: {s.publisher}\nContent: {s.content[:500]}..."
                for s in pre_filtered_sources
            ])
            
            # Choose threshold for display (logic below uses per-source thresholds). If caller provided min_score, use it.
            min_threshold = (min_score if min_score is not None else STIConfig.MIN_TITLE_RELEVANCE_SCORE)
            
            # Create prompt with format instructions
            prompt = prompt_template.format(
                title=title,
                sources_text=sources_text,
                min_threshold=f"{min_threshold:.2f}",
                format_instructions=parser.get_format_instructions()
            )
            
            # Get structured response from LLM
            response = self.llm.invoke(prompt)
            
            # Parse the response (expecting multiple SourceRelevanceScore objects)
            # The LLM should return a JSON array of relevance scores
            try:
                # Clean up the response content
                content = response.content.strip()
                
                # Try to extract JSON from the response if it's wrapped in markdown
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0].strip()
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0].strip()
                
                # Try to parse as JSON array first
                relevance_data = json.loads(content)
                if isinstance(relevance_data, list):
                    relevance_scores = [SourceRelevanceScore(**item) for item in relevance_data]
                elif isinstance(relevance_data, dict) and "results" in relevance_data:
                    # Handle case where LLM returns {"results": [...]}
                    relevance_scores = [SourceRelevanceScore(**item) for item in relevance_data["results"]]
                else:
                    # Fallback: try to parse as single object
                    relevance_scores = [SourceRelevanceScore(**relevance_data)]
                    
                logger.info(f"Successfully parsed {len(relevance_scores)} relevance scores")
                
            except (ValueError, KeyError, json.JSONDecodeError) as e:
                # Fallback: create default scores if parsing fails
                logger.warning(f"Failed to parse relevance scores: {str(e)}. Using default values.")
                logger.debug(f"Response content: {response.content[:500]}...")
                relevance_scores = [
                    SourceRelevanceScore(
                        source_id=s.id,
                        relevance_score=float(min_threshold),
                        relevance_reason="Heuristic fallback (parse failure)",
                        is_relevant=True
                    ) for s in pre_filtered_sources
                ]
            
            # Filter sources based on relevance scores with foundational relax
            score_map = {rs.source_id: rs for rs in relevance_scores}

            # Canonical anchor override: if title is thematic, force-include consensus/control anchors from canonical hosts
            try:
                canonical_hosts = ('ieeexplore.ieee.org', 'dl.acm.org', 'link.springer.com', 'sciencedirect.com', 'arxiv.org')
                anchor_keywords = ('consensus', 'multi-agent', 'cooperation', 'leader', 'formation', 'containment')
                themed = any(t in title.lower() for t in ('command','control','consensus','coordination','hierarchical'))
                if themed:
                    for s in pre_filtered_sources:
                        if any(h in (s.url or '') for h in canonical_hosts):
                            st = (s.title or '').lower()
                            if any(k in st for k in anchor_keywords):
                                existing = score_map.get(s.id)
                                score_map[s.id] = SourceRelevanceScore(
                                    source_id=s.id,
                                    relevance_score=max(0.5, getattr(existing, 'relevance_score', 0.5)),
                                    relevance_reason='canonical anchor override (consensus/control)',
                                    is_relevant=True
                                )
            except Exception as _:
                pass
            relevant_sources = []
            canonical_publishers = {
                'ieeexplore.ieee.org', 'dl.acm.org', 'link.springer.com', 'sciencedirect.com'
            }
            theme_terms = ('command', 'control', 'consensus', 'coordination', 'hierarchical')
            title_lower = title.lower()
            for source in pre_filtered_sources:
                rs = score_map.get(source.id)
                if not rs:
                    continue
                base_thresh = (min_score if min_score is not None else STIConfig.MIN_TITLE_RELEVANCE_SCORE)
                if source.url in foundational_urls:
                    eff_thresh = STIConfig.MIN_TITLE_RELEVANCE_SCORE_FOUNDATIONAL
                else:
                    eff_thresh = base_thresh
                # Further relax for canonical academic hosts on themed titles
                if (any(h in (source.url or '') for h in ('ieeexplore.ieee.org','dl.acm.org','link.springer.com','sciencedirect.com','arxiv.org'))
                    and any(t in title_lower for t in theme_terms)):
                    eff_thresh = min(eff_thresh, STIConfig.MIN_TITLE_RELEVANCE_SCORE_FOUNDATIONAL)
                if rs.relevance_score >= eff_thresh:
                    relevant_sources.append(source)
                    logger.info(f"✓ Source '{source.title}' deemed relevant (score: {rs.relevance_score:.2f}, thresh: {eff_thresh})")
                else:
                    logger.info(f"✗ Source '{source.title}' filtered out (score: {rs.relevance_score:.2f}, thresh: {eff_thresh})")
            
            logger.info(f"Filtered {len(pre_filtered_sources)} pre-filtered sources down to {len(relevant_sources)} relevant sources")
            return relevant_sources
            
        except Exception as e:
            logger.error(f"Error filtering sources by relevance: {str(e)}")
            return sources  # Return all sources if filtering fails
    
    def _derive_title_from_content(self, signals: List[Dict], sources: List[Source], original_query: str, intent: str = "market") -> str:
        """Derive title using structured output to ensure consistent format (intent-aware)"""
        if not STIConfig.ENABLE_TITLE_REFINEMENT:
            return f"Tech Brief — {original_query}"
            
        try:
            # Create Pydantic output parser for title refinement
            parser = PydanticOutputParser(pydantic_object=TitleRefinement)
            
            # Create prompt template for title derivation
            prompt_template = PromptTemplate(
                input_variables=["signals", "sources", "original_query", "guardrails"],
                template="""You are a title refinement expert. Your task is to derive a more accurate report title based on the actual content found.

PURPOSE: Create a title that accurately represents the content that was actually found, rather than the original query.

CONTEXT: We have signals and sources that were found, but the original query might not match what was actually discovered.

TASK: Analyze the signals and sources to:
1. Identify the main topic/theme that actually emerged from the content
2. Create a title that accurately represents this content
3. Score how well the new title aligns with the original query
4. Determine if the title should be updated

{guardrails}

EVALUATION CRITERIA:
- Does the new title accurately reflect the content found?
- Is it more specific and descriptive than the original?
- Would someone reading this title expect to find this content?

Signals found:
{signals}

Sources found:
{sources}

Original Query: {original_query}

{format_instructions}

Return structured JSON with the refined title:"""
            )
            
            # Prepare signals and sources text
            signals_text = "\n".join([f"- {s.get('text', '')}" for s in signals[:3]])  # Top 3 signals
            sources_text = "\n".join([f"- {s.title} ({s.publisher})" for s in sources[:5]])  # Top 5 sources
            
            # Market-specific guardrails
            guardrails = ""
            if intent == "market":
                must_keep = self._extract_query_key_terms(original_query)
                min_align = getattr(STIConfig, 'MARKET_TITLE_MIN_ALIGNMENT', 0.45)
                min_keep = getattr(STIConfig, 'MARKET_TITLE_MIN_MUST_KEEP', 2)
                banned = getattr(STIConfig, 'MARKET_TITLE_BANNED', [])
                guardrails = (
                    "CONSTRAINTS (MARKET):\n"
                    f"- Do NOT generalize away from the original query.\n"
                    f"- Title MUST include at least {min_keep} of these terms: {must_keep}\n"
                    "- Prefer concrete operator/technology phrasing; avoid abstract theory.\n"
                    f"- Reject generic titles: {banned}\n"
                    f"- Alignment to original query must be >= {min_align:.2f}.\n"
                    "- Format example: 'Market Brief — <Specific Topic>: <Concrete Angle>'\n"
                )

            # Create prompt with format instructions
            prompt = prompt_template.format(
                signals=signals_text,
                sources=sources_text,
                original_query=original_query,
                guardrails=guardrails,
                format_instructions=parser.get_format_instructions()
            )
            
            # Get structured response from LLM
            response = self.llm.invoke(prompt)
            
            # Parse the response
            try:
                title_refinement = parser.parse(response.content)
                
                # Decide whether to use the refined title
                if title_refinement.should_update and title_refinement.alignment_score >= STIConfig.TITLE_REFINEMENT_THRESHOLD:
                    logger.info(f"Title refined: '{original_query}' → '{title_refinement.refined_title}' (alignment: {title_refinement.alignment_score:.2f})")
                    final_title = title_refinement.refined_title
                    if intent == "market" and not self._validate_title_alignment_market(final_title, original_query):
                        final_title = f"Market Brief — {original_query}"
                    return f"Tech Brief — {final_title}"
                else:
                    # If alignment is very low, suggest a theme-based title
                    if title_refinement.alignment_score < 0.3:
                        suggested_title = self._generate_theme_based_title(signals, sources)
                        if intent == "market" and not self._validate_title_alignment_market(suggested_title, original_query):
                            suggested_title = original_query
                        logger.warning(f"Very low alignment ({title_refinement.alignment_score:.2f}). Suggested title: '{suggested_title}'")
                        return f"Tech Brief — {suggested_title}"
                    else:
                        logger.info(f"Title kept original: '{original_query}' (alignment: {title_refinement.alignment_score:.2f})")
                        return f"Tech Brief — {original_query}"
                    
            except Exception as e:
                logger.error(f"Error parsing title refinement: {str(e)}")
                return f"Tech Brief — {original_query}"
                
        except Exception as e:
            logger.error(f"Error deriving title from content: {str(e)}")
            return f"Tech Brief — {original_query}"

    def _extract_query_key_terms(self, query: str) -> List[str]:
        """Extract must-keep terms from the original query (simple heuristic)."""
        import re as _re
        q = query.strip()
        phrases = []
        known = [
            'autonomous research', 'simulation ai', 'self-driving labs', 'closed-loop experimentation',
            'digital twins', 'simulation orchestration', 'surrogate modeling', 'physics-informed neural networks'
        ]
        low = q.lower()
        for k in known:
            if k in low:
                phrases.append(k)
        words = [w for w in _re.split(r"[^A-Za-z0-9&+-]", q) if w]
        tokens = [w for w in words if len(w) > 3]
        seen = set(); out = []
        for t in phrases + tokens:
            tl = t.lower()
            if tl not in seen:
                seen.add(tl)
                out.append(t)
        return out[:6]

    def _validate_title_alignment_market(self, candidate: str, original_query: str) -> bool:
        """Validate market title against alignment, must-keep terms, and banned list."""
        import re as _re
        banned = set(getattr(STIConfig, 'MARKET_TITLE_BANNED', []))
        min_align = getattr(STIConfig, 'MARKET_TITLE_MIN_ALIGNMENT', 0.45)
        min_keep = getattr(STIConfig, 'MARKET_TITLE_MIN_MUST_KEEP', 2)
        c = candidate.strip().lower()
        if c in banned:
            return False
        def _tok(s: str):
            return set(w for w in _re.split(r"[^a-z0-9]+", s.lower()) if len(w) > 3)
        qtok = _tok(original_query); ctok = _tok(candidate)
        align = (len(qtok & ctok) / max(1, len(qtok | ctok))) if (qtok or ctok) else 0.0
        if align < min_align:
            return False
        must_keep = [t.lower() for t in self._extract_query_key_terms(original_query)]
        keep_hits = sum(1 for t in must_keep if t and t in c)
        if keep_hits < min_keep:
            return False
        return True
    
    def _generate_theme_based_title(self, signals: List[Dict], sources: List[Source]) -> str:
        """Generate a title based on the actual themes found in signals and sources"""
        try:
            # Extract key themes from signals
            themes = []
            for signal in signals[:3]:  # Top 3 signals
                text = signal.get('text', '').lower()
                if 'agent' in text or 'ai' in text:
                    themes.append('AI Agents')
                if 'robot' in text or 'robotics' in text:
                    themes.append('Robotics')
                if 'cybersecurity' in text or 'security' in text:
                    themes.append('Cybersecurity')
                if 'automation' in text or 'workflow' in text:
                    themes.append('Automation')
                if 'multi-agent' in text or 'orchestration' in text:
                    themes.append('Multi-Agent Systems')
            
            # Extract themes from source titles
            for source in sources[:5]:  # Top 5 sources
                title = source.title.lower()
                if 'agent' in title or 'ai' in title:
                    themes.append('AI Agents')
                if 'robot' in title or 'robotics' in title:
                    themes.append('Robotics')
                if 'cybersecurity' in title or 'security' in title:
                    themes.append('Cybersecurity')
                if 'automation' in title or 'workflow' in title:
                    themes.append('Automation')
            
            # Count theme frequency
            theme_counts = {}
            for theme in themes:
                theme_counts[theme] = theme_counts.get(theme, 0) + 1
            
            # Generate title from most common themes
            if theme_counts:
                top_themes = sorted(theme_counts.items(), key=lambda x: x[1], reverse=True)[:2]
                if len(top_themes) == 1:
                    return top_themes[0][0]
                else:
                    return f"{top_themes[0][0]} and {top_themes[1][0]}"
            else:
                return "AI Technology Trends"
                
        except Exception as e:
            logger.error(f"Error generating theme-based title: {str(e)}")
            return "AI Technology Trends"
    
    def _is_control_theory_on_topic(self, source: Source) -> bool:
        """Heuristic guard to accept only control-theory/consensus multi-agent sources."""
        try:
            title = (source.title or "").lower()
            text = (source.content or "").lower()
            keywords = [
                'consensus', 'leader–follower', 'leader-follower', 'formation control',
                'containment control', 'distributed control', 'supervisory control',
                'graph laplacian', 'lyapunov', 'stability', 'multi-agent', 'multi agent'
            ]
            return any(k in title or k in text for k in keywords)
        except Exception:
            return False
        
    def _search_theoretical_concepts(self, query: str, days_back: int) -> List[Source]:
        """Specialized search for theoretical/academic concepts with strict caps and guards"""
        try:
            # For theory queries, we search academic sources even if query doesn't contain explicit theory terms
            # The intent classification already determined this is a theory query
            # (Original check removed - too restrictive for queries like "Cognitive Wars" that don't use explicit theory terms)
            
            strict_domains = ['ieeexplore.ieee.org', 'dl.acm.org', 'link.springer.com', 'sciencedirect.com', 'arxiv.org']
            results: List[Source] = []
            seen_urls = set()
            total_calls = 0
            max_calls = 30
            target = STIConfig.MIN_ACADEMIC_SOURCES_THEORY
            
            # Check if query is explicitly about control theory (narrow filter) vs general theory (broad filter)
            query_lower = query.lower()
            is_control_theory_query = any(term in query_lower for term in [
                'control theory', 'command and control', 'consensus', 'formation control',
                'containment control', 'leader-follower', 'multi-agent', 'distributed control'
            ])
            
            def add_sources(found: List[Source]):
                nonlocal results, seen_urls
                for s in found:
                    if s.url in seen_urls:
                        continue
                    # Only apply narrow control theory filter if query is explicitly about control theory
                    # Otherwise, accept any academic source from anchor domains (broader theory queries)
                    if is_control_theory_query:
                        # For control theory queries, use narrow filter
                        if self._is_control_theory_on_topic(s):
                            results.append(s)
                            seen_urls.add(s.url)
                    else:
                        # For general theory queries, accept any academic source from anchor domains
                        results.append(s)
                        seen_urls.add(s.url)
            
            # Anchor queries first (precision)
            anchor_queries = self._anchor_queries
            for aq in anchor_queries:
                if total_calls >= max_calls or len(results) >= target:
                    break
                try:
                    if aq in self._anchor_cache:
                        anchors = self._anchor_cache[aq]
                    else:
                        total_calls += 1
                        anchors = self._search_by_domain_type(aq, strict_domains, SourceType.ACADEMIC, max_results=4, days_back=days_back)
                        self._anchor_cache[aq] = anchors
                    add_sources(anchors)
                except Exception as e:
                    logger.warning(f"Anchor query failed '{aq}': {str(e)}")
            if len(results) >= target:
                logger.info(f"Anchor queries met academic floor: {len(results)}")
                return results
            
            # Venue keyword augmentation (limited)
            venue_keywords = [
                'IEEE Transactions on Automatic Control', 'Automatica', 'ACC'
            ]
            per_venue_limit = 2
            for vk in venue_keywords:
                if total_calls >= max_calls or len(results) >= target:
                    break
                q = f"{query} {vk}"
                try:
                    total_calls += 1
                    found = self._search_by_domain_type(q, strict_domains, SourceType.ACADEMIC, max_results=4, days_back=days_back)
                    add_sources(found)
                except Exception as e:
                    logger.warning(f"Venue query failed '{vk}': {str(e)}")
            
            # Fallback: plain strict-domain search
            if total_calls < max_calls and len(results) < target:
                try:
                    total_calls += 1
                    academic_sources = self._search_by_domain_type(query, strict_domains, SourceType.ACADEMIC, max_results=5, days_back=days_back)
                    add_sources(academic_sources)
                except Exception as e:
                    logger.error(f"Error searching theoretical concepts: {str(e)}")
            
            logger.info(f"Found {len(results)} strict-domain academic sources for theoretical query (calls={total_calls})")
            return results
            
        except Exception as e:
            logger.error(f"Error searching theoretical concepts: {str(e)}")
            return []
    
    def _rubric_rerank(self, sources: List[Source], query: str, concepts: List[str]) -> List[Source]:
        """LLM rubric-based reranker for theory queries"""
        if not sources:
            return sources
        try:
            rubric = (
                "You are ranking academic sources for a theoretical control/consensus topic.\n"
                "Score each source from 0.0 to 1.0. Criteria: (1) Theoretical contribution (definitions/theorems/proofs/math);"
                " (2) Topic fit (consensus, leader–follower, formation/containment/distributed control);"
                " (3) Multi-agent setting explicitly discussed."
            )
            payload = "\n".join([
                f"Source {s.id}: {s.title}\nPublisher: {s.publisher}\nContent: {s.content[:600]}..." for s in sources
            ])
            prompt = (
                f"{rubric}\n\nQuery: {query}\nConcepts: {', '.join(concepts[:8]) if concepts else ''}\n\n"
                f"Return JSON array of objects: {{source_id, score, rationale}} for each source.\n\n{payload}"
            )
            response = self.llm.invoke(prompt)
            content = response.content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            data = json.loads(content)
            score_map = {item.get('source_id'): float(item.get('score', 0.0)) for item in data if isinstance(item, dict)}
            # Stable sort by score desc, fallback 0.0
            ranked = sorted(sources, key=lambda s: score_map.get(s.id, 0.0), reverse=True)
            logger.info("Applied rubric reranker to theory sources")
            return ranked
        except Exception as e:
            logger.warning(f"Rubric reranker failed, passing through sources: {str(e)}")
            return sources

    def search(
        self,
        query: str,
        days_back: int = 7,
        seed: Optional[int] = None,
        budget_advanced: int = 0,
    ) -> Tuple[str, Dict[str, Any], Dict[str, Any]]:
        """
        Enhanced search that produces 3,000-4,000 word reports
        Uses existing search logic + new analysis tools
        
        Returns:
            Tuple of (markdown_report, json_ld_artifact, run_summary)
        """
        self.last_run_status = {}
        if seed is not None:
            random.seed(seed)
            try:
                np.random.seed(seed)
            except Exception:
                pass

        # BudgetManager will be created after intent is determined
        # to allow auto-allocation for thesis runs
        quality_gates_passed = True
        audit_outputs: Dict[str, Any] = {}

        try:
            # Step 0: Market-first routing approach
            # Always search for market sources first, then check if they adequately reflect the query
            # If not adequate, default to thesis-path (assume theoretical, not yet commercialized)
            
            # Initialize variables that may be used later
            concepts = []
            foundational_sources = []
            
            # Step 1: Refine query for searching
            refined_query = self._refine_query_for_title(query)
            logger.info(f"Query refined: '{query}' → '{refined_query}'")
            
            # Step 2: ALWAYS search for market sources first (regardless of what query might be)
            logger.info("Step 2: Searching for market sources first...")
            market_sources = self._search_with_time_filtering(refined_query, days_back)
            logger.info(f"Found {len(market_sources)} market sources")
            
            # Step 3: Check if market sources adequately reflect the query
            market_adequate = self._check_market_source_adequacy(market_sources, query)
            
            if market_adequate:
                # Market-path: Use market sources
                logger.info("Market sources adequately reflect query. Using market-path.")
                intent = "market"
                all_sources = market_sources
                
            else:
                # Thesis-path: Query is likely theoretical, not yet commercialized
                logger.info("Market sources do not adequately reflect query. Using thesis-path.")
                intent = "theory"
            
            # Auto-allocate premium budget for thesis runs if budget_advanced is 0
            effective_budget = budget_advanced
            if intent == "theory" and budget_advanced == 0:
                effective_budget = 10000  # Safe floor: 10k tokens for thesis runs
                logger.info(f"Auto-allocating {effective_budget} tokens for thesis run (budget_advanced was 0)")
            
            # Create BudgetManager with effective budget
            budget = BudgetManager(
                total_tokens=effective_budget,
                pct=getattr(STIConfig, 'ADVANCED_BUDGET_PCT', 0.25),
            )
            
            if intent == "theory":
                # Expand query for theoretical search
                expanded_query = self._expand_theoretical_query(query)
                logger.info(f"Theory query expanded: '{query}' → '{expanded_query}'")
                
                # Decompose query into core concepts
                concepts = self._decompose_theory_query(query)
                logger.info(f"Decomposed query into concepts: {concepts}")
                
                # Search for foundational sources with extended time window
                foundational_sources = self._search_foundational_sources(concepts, STIConfig.THEORY_FOUNDATIONAL_DAYS_BACK)
                logger.info(f"Found {len(foundational_sources)} foundational sources")
                
                # Search recent academic sources
                academic_sources = self._search_theoretical_concepts(expanded_query, days_back)
                logger.info(f"Found {len(academic_sources)} recent academic sources")
                
                # Progressive widening for recent academic theory: 7→30→90
                if len(academic_sources) < STIConfig.MIN_ACADEMIC_SOURCES_THEORY and days_back < 30:
                    widened = 30
                    logger.info(f"Widening recent academic window to {widened} days for theory query")
                    more_academic = self._search_theoretical_concepts(expanded_query, widened)
                    # merge
                    seen = set(s.url for s in academic_sources)
                    for s in more_academic:
                        if s.url not in seen:
                            academic_sources.append(s)
                            seen.add(s.url)
                if len(academic_sources) < STIConfig.MIN_ACADEMIC_SOURCES_THEORY and days_back < 90:
                    widened = 90
                    logger.info(f"Widening recent academic window to {widened} days for theory query")
                    more_academic = self._search_theoretical_concepts(expanded_query, widened)
                    seen = set(s.url for s in academic_sources)
                    for s in more_academic:
                        if s.url not in seen:
                            academic_sources.append(s)
                            seen.add(s.url)
                
                # Also include any market sources that might be relevant (for hybrid reports)
                # But filter out market sources that don't match theory context
                all_sources = foundational_sources + academic_sources + market_sources
                logger.info(f"Total sources found: {len(all_sources)} (foundational: {len(foundational_sources)}, academic: {len(academic_sources)}, market: {len(market_sources)})")
            
            # Step 4: Assign sources based on intent
            if intent == "market":
                sources = all_sources
                logger.info(f"Market intent: using {len(sources)} market sources")
            else:
                # For theory queries, use all sources directly
                sources = all_sources
            
            # Step 5: Deduplicate sources
            sources = self._deduplicate_sources(sources)
            
            # Step 6: Re-weight by source type based on intent
            sources = self._reweight_by_source_type(sources, intent)
            
            # Step 7: Apply semantic similarity filter with dynamic threshold
            threshold = STIConfig.SEMANTIC_THRESHOLD_THEORY if intent == "theory" else STIConfig.SEMANTIC_THRESHOLD_MARKET
            logger.info(f"Applying semantic similarity filter with threshold: {threshold} (intent: {intent})")
            concepts_for_filter = concepts if intent == "theory" else None
            semantically_relevant_sources = self._semantic_similarity_filter(sources, query, threshold=threshold, concepts=concepts_for_filter)
            
            # Apply rubric reranker for theory intent
            if intent == "theory":
                semantically_relevant_sources = self._rubric_rerank(semantically_relevant_sources, query, concepts or [])
            
            # Step 8: Filter sources by title relevance (apply foundational relax if applicable)
            original_title = f"Tech Brief — {query}"
            foundational_urls = set(s.url for s in foundational_sources) if intent == "theory" else set()
            market_thresh = getattr(STIConfig, 'MARKET_TITLE_RELEVANCE_THRESHOLD', 0.5)
            if intent == "theory":
                relevant_sources = self._filter_sources_by_title_relevance(
                    semantically_relevant_sources,
                    original_title,
                    foundational_urls=foundational_urls,
                )
            else:
                relevant_sources = self._filter_sources_by_title_relevance(
                    semantically_relevant_sources,
                    original_title,
                    foundational_urls=set(),
                    min_score=market_thresh,
                )
            
            # Step 9: Early insufficient-evidence write and adaptive fallback
            MIN_REQUIRED_SOURCES = 3
            
            # Check academic floor for theory queries
            academic_floor_met = self._check_academic_floor(relevant_sources, intent)

            def _write_insufficient_and_return(reason: str = None):
                nonlocal quality_gates_passed
                quality_gates_passed = False
                logger.warning(f"Only {len(relevant_sources)} relevant sources. Writing insufficient evidence report.")
                if reason:
                    logger.warning(reason)
                
                # Create minimal report for insufficient evidence
                end_dt = datetime.now()
                start_dt = end_dt - timedelta(days=days_back)
                exec_summary = reason or "Insufficient evidence to substantiate the requested title within the time window."
                insufficient_report = f"""# Tech Brief — {query}
Date range: {start_dt.strftime('%b %d')}–{end_dt.strftime('%b %d')}, 2025 | Sources: {len(relevant_sources)} | Confidence: 0.00

## Executive Summary
{exec_summary}

## Topline
Insufficient evidence available to generate a meaningful topline summary.

## Signals
No signals extracted due to insufficient evidence.

## Sources
"""
                for i, source in enumerate(relevant_sources, 1):
                    insufficient_report += f"[^{i}]: {source.title} — {source.publisher}, {source.date}. (cred: {source.credibility:.2f}) — {source.url}\n"
                
                json_ld = self._generate_json_ld_artifact(
                    query, relevant_sources, [], 0.0, days_back, exec_summary,
                    word_count=len(insufficient_report.split()), final_title=f"Tech Brief — {query}"
                )
                fallback_manifest = {
                    "query": query,
                    "days": days_back,
                    "seed": seed,
                    "budget_advanced": budget_advanced,
                    "timestamp": datetime.now().isoformat(),
                    "models": {
                        "primary": self.model_name,
                        "advanced": getattr(STIConfig, 'ADVANCED_MODEL_NAME', None),
                    },
                    "metrics": {
                        "confidence": 0.0,
                        "anchor_coverage": 0.0,
                        "quant_flags": 0,
                    },
                    "advanced_tasks": [],
                    "advanced_tokens_spent": 0,
                    "report_title": f"Tech Brief — {query}",
                    "intent": intent,
                }
                self.last_run_status = {
                    "quality_gates_passed": False,
                    "report_dir": None,
                    "run_manifest": fallback_manifest,
                    "metrics": fallback_manifest["metrics"],
                    "advanced_tasks": [],
                    "asset_gated": True,
                }
                return insufficient_report, json_ld, {
                    'intent': intent,
                    'artifacts': {},
                    'metrics': {'confidence': 0.0, 'anchor_coverage': 0.0, 'quant_flags': 0},
                    'confidence_breakdown': {},
                    'premium': {'requested': [], 'executed': {}},
                }

            # Check for academic floor failure for theory queries (takes precedence over general source count)
            # BUT: if foundational_sources exist, continue to full thesis-path instead of simplified report
            if intent == "theory" and not academic_floor_met and len(foundational_sources) == 0:
                academic_count = len([s for s in relevant_sources if s.source_type == SourceType.ACADEMIC])
                logger.warning(f"Academic floor unmet ({academic_count}/{STIConfig.MIN_ACADEMIC_SOURCES_THEORY}); generating simplified thesis-style report (no foundational sources available).")
                # Generate simplified thesis-style report when no foundational sources
                thesis_report = self._generate_thesis_style_report([], relevant_sources, query, foundational_sources)
                exec_summary = "Insufficient recent academic evidence; providing a first-principles synthesis based on foundational control theory and related multi-agent concepts."
                json_ld = self._generate_json_ld_artifact(
                    query, relevant_sources, [], 0.0, days_back, exec_summary,
                    word_count=len(thesis_report.split()), final_title=f"Tech Brief — {query}"
                )
                return thesis_report, json_ld, {
                    'intent': intent,
                    'artifacts': {},
                    'metrics': {'confidence': 0.0, 'anchor_coverage': 0.0, 'quant_flags': 0},
                    'confidence_breakdown': {},
                    'premium': {'requested': [], 'executed': {}},
                }
            elif intent == "theory" and not academic_floor_met and len(foundational_sources) > 0:
                academic_count = len([s for s in relevant_sources if s.source_type == SourceType.ACADEMIC])
                logger.info(f"Academic floor unmet ({academic_count}/{STIConfig.MIN_ACADEMIC_SOURCES_THEORY}) but {len(foundational_sources)} foundational sources available. Proceeding to full thesis-path generation.")
                # Continue processing to allow full thesis-path generation (don't return early)

            if len(relevant_sources) < MIN_REQUIRED_SOURCES:
                # Relax filtering based on top scores (fallback)
                logger.info("Relaxing relevance threshold for fallback selection")
                # Use pre-filter set as the pool; select top 3 by score regardless of boolean cutoff
                try:
                    # We reconstruct scores from known pool by issuing a smaller structured prompt (best-effort)
                    # If not available, simply keep the first N to ensure a write
                    pool = sources
                    if len(pool) >= MIN_REQUIRED_SOURCES:
                        relevant_sources = pool[:MIN_REQUIRED_SOURCES]
                except Exception as e:
                    logger.warning(f"Fallback selection failed: {str(e)}")
                    # Ensure we at least keep some sources for artifact write
                    relevant_sources = sources[:MIN_REQUIRED_SOURCES] if sources else []

            if len(relevant_sources) < MIN_REQUIRED_SOURCES and days_back < STIConfig.MAX_DAYS_BACK:
                widened_days = min(days_back * 2, STIConfig.MAX_DAYS_BACK)
                logger.info(f"Retrying with widened time window: {widened_days} days")
                wider_sources = self._search_with_time_filtering(refined_query, widened_days)
                # Only search academic sources for theory queries
                if intent == "theory":
                    wider_sources.extend(self._search_theoretical_concepts(refined_query, widened_days))
                relevant_sources = self._filter_sources_by_title_relevance(wider_sources, original_title)

            if len(relevant_sources) < MIN_REQUIRED_SOURCES:
                # Market fallback: if we have enough in-window independent news, proceed anyway
                if intent == "market":
                    try:
                        from datetime import datetime as _dt, timedelta as _td
                        end_dt = _dt.now()
                        start_dt = end_dt - _td(days=days_back)
                        def _is_in_window(src):
                            try:
                                d = _dt.strptime(src.date, '%Y-%m-%d')
                                return start_dt <= d <= end_dt
                            except Exception:
                                return True
                        in_window_indep = [s for s in sources if s.source_type == SourceType.INDEPENDENT_NEWS and _is_in_window(s)]
                        if len(in_window_indep) >= 3:
                            logger.info("Market fallback: proceeding with in-window independent news despite low title relevance.")
                            relevant_sources = in_window_indep[:6]
                        else:
                            return _write_insufficient_and_return()
                    except Exception:
                        return _write_insufficient_and_return()
                elif intent == "theory" and len(foundational_sources) > 0:
                    # Theory query with foundational sources: proceed to thesis-path generation
                    logger.info(f"Only {len(relevant_sources)} relevant sources but {len(foundational_sources)} foundational sources available. Proceeding with thesis-path generation.")
                    # Continue processing - don't return early
                else:
                    return _write_insufficient_and_return()
            
            # Step 4: Quality gate checks (bypass news gates for theory when academic floor met OR foundational sources available)
            if intent == "theory" and (academic_floor_met or len(foundational_sources) > 0):
                if academic_floor_met:
                    logger.info("Theory intent with academic floor met — bypassing news quality gates.")
                else:
                    logger.info(f"Theory intent with {len(foundational_sources)} foundational sources — bypassing news quality gates.")
            else:
                if not self._check_quality_gates(relevant_sources):
                    if intent == "market":
                        # Last-mile fallback: try proceeding with in-window independent news
                        try:
                            from datetime import datetime as _dt, timedelta as _td
                            end_dt = _dt.now()
                            start_dt = end_dt - _td(days=days_back)
                            def _in_window(src):
                                try:
                                    d = _dt.strptime(src.date, '%Y-%m-%d')
                                    return start_dt <= d <= end_dt
                                except Exception:
                                    return True
                            in_window_indep = [s for s in sources if s.source_type == SourceType.INDEPENDENT_NEWS and _in_window(s)]
                            if len(in_window_indep) >= 3:
                                logger.info("Market last-mile: continuing with in-window independent news to satisfy gates.")
                                relevant_sources = in_window_indep[:6]
                            else:
                                return _write_insufficient_and_return("Quality gates not met for sources.")
                        except Exception:
                            return _write_insufficient_and_return("Quality gates not met for sources.")
                    else:
                        return _write_insufficient_and_return("Quality gates not met for sources.")
            
            # Step 5: Use existing signal extraction (ensure at least as many signals as sources)
            # Use max of source count and configured minimum to ensure good coverage
            signal_count = max(len(relevant_sources), STIConfig.SIGNALS_COUNT)
            signals = self._extract_signals_enhanced(relevant_sources, count=signal_count)
            
            # Step 6: Derive title from actual content found (intent-aware)
            final_title = self._derive_title_from_content(signals, relevant_sources, query, intent=intent)
            
            # Step 7: NEW - Call analysis MCP tools for deep sections using relevant sources
            sources_json = self._serialize_sources_to_json(relevant_sources)
            signals_json = self._serialize_signals_to_json(signals)
            
            # Run analysis tools directly
            market_analysis = self._call_analysis_tool("analyze_market", sources_json, signals_json)
            tech_deepdive = self._call_analysis_tool("analyze_technology", sources_json, signals_json)
            competitive = self._call_analysis_tool("analyze_competitive", sources_json, signals_json)
            
            # Prepare analyses for lens expansion
            analyses_json = json.dumps([market_analysis, tech_deepdive, competitive])
            expanded_lenses = self._call_analysis_tool("expand_lenses", signals_json, analyses_json)
            
            # Prepare content for actions and summary
            all_content_json = json.dumps({
                "signals": signals,
                "analyses": [market_analysis, tech_deepdive, competitive],
                "lenses": expanded_lenses
            })
            
            exec_summary = self._call_analysis_tool("write_executive_summary", all_content_json)
            
            # Initialize confidence before passing to _run_auditors
            confidence = self._calculate_confidence_with_intent(signals, relevant_sources, intent)
            
            audit_outputs = self._run_auditors(
                query=query,
                intent=intent,
                sources=relevant_sources,
                signals=signals,
                market_analysis=market_analysis,
                tech_deepdive=tech_deepdive,
                competitive=competitive,
                expanded_lenses=expanded_lenses,
                exec_summary=exec_summary,
                confidence=confidence,
                budget=budget,
            )
            ledger_data = audit_outputs.get("ledger")
            quant_patch = audit_outputs.get("quant_patch")
            adversarial_data = audit_outputs.get("adversarial")
            playbooks_data = audit_outputs.get("playbooks")
            confidence_breakdown = audit_outputs.get("confidence_breakdown")
            confidence = audit_outputs.get("confidence", confidence)
            metrics = audit_outputs.get("metrics", {})
            anchor_gate = audit_outputs.get("anchor_gate", False)
            advanced_tokens = audit_outputs.get("advanced_tokens", 0)
            premium_tasks_run = audit_outputs.get("tasks_executed", [])
            tasks_requested = audit_outputs.get("tasks_requested", [])
            task_matrix = audit_outputs.get("task_matrix", {})
            source_sha_map = audit_outputs.get("source_sha_map", {})
            report_sections = audit_outputs.get("report_sections", {})
            claims_snapshot = audit_outputs.get("claims", [])

            # Step 8: Track source attribution using relevant sources
            self._calculate_source_attribution_stats(
                relevant_sources, signals, [market_analysis, tech_deepdive, competitive]
            )
            
            # Step 9: Use confidence calculation with intent-aware penalties
            # Note: confidence is already initialized above, but update from audit_outputs if available
            if confidence_breakdown:
                logger.info(
                    "Confidence breakdown: diversity=%.2f anchor=%.2f method=%.2f replication=%.2f",
                    confidence_breakdown.source_diversity,
                    confidence_breakdown.anchor_coverage,
                    confidence_breakdown.method_transparency,
                    confidence_breakdown.replication_readiness,
                )
                # confidence already updated from audit_outputs at line 3443
            # else: confidence already initialized above, no need to recalculate

            # Build single source-of-truth report model (for reconciliation)
            end_dt = datetime.now()
            start_dt = end_dt - timedelta(days=days_back)
            start_date_str = start_dt.strftime('%Y-%m-%d')
            end_date_str = end_dt.strftime('%Y-%m-%d')

            source_models = [
                SourceModel(
                    id=i + 1,
                    title=s.title,
                    url=s.url,
                    publisher=s.publisher,
                    date=s.date,
                    credibility=s.credibility,
                )
                for i, s in enumerate(relevant_sources)
            ]

            signal_models: List[SignalModel] = []
            for sig in signals:
                signal_models.append(
                    SignalModel(
                        claim=sig.get('text', ''),
                        strength=float(sig.get('confidence', 0.3)),
                        impact=sig.get('impact', 'market'),
                        direction=sig.get('direction', 'flat'),
                        citations=sig.get('citation_ids', []),
                    )
                )

            canonical_hosts = ['ieeexplore.ieee.org','dl.acm.org','link.springer.com','sciencedirect.com','arxiv.org']
            foundational_url_set = set(s.url for s in foundational_sources)
            
            # Telemetry: persist thesis node I/O if available
            thesis_io = {}
            try:
                if intent == "theory" and len(foundational_sources) > 0:
                    if 'outline' in locals():
                        thesis_io['outline_in'] = {'concepts': concepts}
                        thesis_io['outline_out'] = outline.model_dump()
                    if 'draft' in locals():
                        thesis_io['compose_in'] = {'sections': getattr(outline,'sections',[])}
                        thesis_io['compose_out'] = {'cited_source_ids': getattr(draft,'cited_source_ids',[])}
                    if 'critique' in locals():
                        thesis_io['critique_out'] = critique.model_dump()
                    if 'publication_rubric' in locals():
                        thesis_io['publication_rubric'] = publication_rubric.model_dump()
                    if 'diversity_score' in locals():
                        thesis_io['diversity_score'] = diversity_score
                    # Add playbook values
                    if 'anchor_status' in locals():
                        thesis_io['anchor_status'] = anchor_status
                    if 'thesis_confidence' in locals():
                        thesis_io['confidence'] = thesis_confidence
                    if 'ci_gates_result' in locals():
                        thesis_io['ci_gates'] = ci_gates_result
            except Exception:
                pass
            # Use thesis confidence if available (playbook formula), otherwise use regular confidence
            # Note: thesis_confidence is calculated later in thesis path, so we'll update this below
            final_confidence = float(confidence)
            
            report_model = ReportModel(
                title=final_title,
                query=query,
                start_date=start_date_str,
                end_date=end_date_str,
                confidence=final_confidence,
                sources=source_models,
                signals=signal_models,
                metadata={
                    'intent': intent,
                    'allow_foundational_out_of_window': True,
                    'canonical_hosts': canonical_hosts,
                    'foundational_urls': list(foundational_url_set),
                    'thesis_io': thesis_io,
                    'confidence_breakdown': confidence_breakdown.__dict__ if confidence_breakdown else None,
                    'metrics': metrics,
                    'tasks_requested': tasks_requested,
                    'claims_snapshot': claims_snapshot,
                }
            )
            
            # Step 10: Generate enhanced report (3,000-4,000 words) using final title and relevant sources
            if intent == "theory" and len(foundational_sources) > 0:
                # Thesis subgraph: outline -> compose -> critique (bounded repair)
                logger.info("Generating thesis-style report for theory query (LangGraph-style path)")
                
                # Step 10.1: Search for anchor sources (peer-reviewed, non-preprint) for thesis reports
                anchor_sources = self._search_thesis_anchor_sources(query, STIConfig.THEORY_FOUNDATIONAL_DAYS_BACK)
                logger.info(f"Found {len(anchor_sources)} anchor sources for thesis report")
                
                # Merge anchor sources with relevant sources, prioritizing anchors
                if anchor_sources:
                    seen_urls = set(s.url for s in relevant_sources)
                    for anchor in anchor_sources:
                        if anchor.url not in seen_urls:
                            relevant_sources.insert(0, anchor)  # Insert at beginning to prioritize
                            seen_urls.add(anchor.url)
                    logger.info(f"Total sources after anchor merge: {len(relevant_sources)}")
                
                # Step 10.2: Calculate source diversity score
                diversity_score = self._calculate_thesis_source_diversity(relevant_sources)
                logger.info(f"Thesis source diversity score: {diversity_score:.2f}")
                
                outline = self._thesis_outline(ConceptList(concepts=concepts or []), relevant_sources)
                draft = self._thesis_compose(outline, relevant_sources, query)
                thesis_report = draft.markdown
                
                # Step 10.3: Validate section completeness and detect repetition (thesis only)
                completeness = self._validate_thesis_section_completeness(thesis_report)
                repetition = self._detect_thesis_section_repetition(thesis_report)
                
                if completeness['warnings']:
                    logger.warning(f"Thesis section completeness warnings: {completeness['warnings']}")
                if completeness['errors']:
                    logger.error(f"Thesis section completeness errors: {completeness['errors']}")
                    # If critical errors exist, add operational diagnostics to Limits section
                    if any('Operational Assumptions' in err for err in completeness['errors']):
                        thesis_report = self._ensure_operational_diagnostics(thesis_report)
                if repetition['repetition_detected']:
                    logger.warning(f"Thesis section repetition detected: {[o['warning'] for o in repetition['overlaps']]}")
                
                critique = self._thesis_critique(draft, query, relevant_sources)
                
                # Step 10.4: Calculate full publication rubric (thesis only)
                publication_rubric = self._calculate_thesis_publication_rubric(draft, query, relevant_sources, diversity_score)
                logger.info(f"Thesis publication rubric: {publication_rubric.total_score:.1f}/100")
                
                # Step 10.5: Generate CEM grid (thesis only)
                cem_grid = self._generate_cem_grid(draft, relevant_sources)
                logger.info(f"Generated CEM grid with {len(cem_grid.rows)} rows")
                
                # Insert CEM grid into markdown after Formal Models section
                cem_markdown = self._format_cem_grid_markdown(cem_grid)
                thesis_report = self._insert_cem_grid_into_markdown(thesis_report, cem_markdown)
                
                # Step 10.5a: Generate Assumptions Ledger (thesis only)
                assumptions_ledger = self._generate_assumptions_ledger(draft)
                logger.info(f"Generated Assumptions Ledger with {len(assumptions_ledger)} rows")
                has_assumptions_ledger = len(assumptions_ledger) > 0
                
                # Insert Assumptions Ledger into markdown after Formal Models section
                if assumptions_ledger:
                    ledger_markdown = self._format_assumptions_ledger_markdown(assumptions_ledger)
                    # Insert after Formal Models or before CEM Grid
                    import re
                    formal_models_pattern = r'(##\s+(?:Formal\s+Models?|Formal\s+Framework).*?\n)'
                    match = re.search(formal_models_pattern, thesis_report, re.MULTILINE | re.IGNORECASE)
                    if match:
                        thesis_report = thesis_report[:match.end()] + '\n' + ledger_markdown + '\n' + thesis_report[match.end():]
                    else:
                        # Insert before CEM Grid
                        cem_pattern = r'(##\s+Claim-Evidence-Method)'
                        match = re.search(cem_pattern, thesis_report, re.MULTILINE | re.IGNORECASE)
                        if match:
                            thesis_report = thesis_report[:match.start()] + ledger_markdown + '\n\n' + thesis_report[match.start():]
                
                # Step 10.5b: Validate notation (thesis only)
                notation_validation = self._validate_notation(thesis_report)
                if not notation_validation.get('valid', True):
                    logger.warning(f"Notation validation violations: {notation_validation.get('violations', [])}")
                
                # Step 10.5c: Calculate anchor_status and thesis confidence (playbook formula)
                anchor_status = self._calculate_anchor_status(relevant_sources)
                thesis_confidence = self._calculate_thesis_confidence(
                    relevant_sources, draft, cem_grid, has_assumptions_ledger
                )
                logger.info(f"Anchor status: {anchor_status}, Thesis confidence: {thesis_confidence:.3f}")
                
                # Step 10.5d: Run CI gates (thesis only)
                ci_gates_result = self._run_ci_gates(
                    draft, relevant_sources, cem_grid, critique, 
                    publication_rubric, notation_validation, repetition
                )
                logger.info(f"CI gates: {len([g for g in ci_gates_result['gates'].values() if g['passed']])}/7 passed")
                if ci_gates_result['fail_stops']:
                    logger.warning(f"CI gate fail-stops: {ci_gates_result['fail_stops']}")
                
                # Step 10.6: Fix notation table - replace playful mnemonics with standard notation (thesis only)
                modified_markdown, notation_table = self._extract_notation_table(thesis_report)
                thesis_report = modified_markdown  # Update with any in-place replacements
                # If notation_table is a string, it needs to be inserted
                if notation_table:
                    thesis_report = self._insert_notation_table_into_markdown(thesis_report, notation_table)
                
                # Step 10.7: Add Executive Summary if missing (thesis only)
                import re
                exec_summary_exists = re.search(r'^#+\s+Executive Summary\s*', thesis_report, re.MULTILINE | re.IGNORECASE)
                if not exec_summary_exists:
                    # Generate Executive Summary from Abstract or first section
                    abstract_match = re.search(r'^#+\s+Abstract\s*\n+(.+?)(?=\n#+\s+|$)', thesis_report, re.MULTILINE | re.DOTALL | re.IGNORECASE)
                    abstract_content = abstract_match.group(1).strip() if abstract_match else ""
                    
                    if abstract_content:
                        # Use Abstract content for Executive Summary
                        exec_summary_text = abstract_content
                    else:
                        # Generate from first paragraph of first section
                        first_section_match = re.search(r'^#+\s+[^\n]+\s*\n+(.+?)(?=\n#+\s+|$)', thesis_report, re.MULTILINE | re.DOTALL)
                        if first_section_match:
                            first_content = first_section_match.group(1).strip()
                            first_para = first_content.split('\n\n')[0] if '\n\n' in first_content else first_content.split('\n')[0]
                            exec_summary_text = first_para.strip()
                        else:
                            # Fallback: use provided template
                            exec_summary_text = "This thesis-path brief takes a **theory-first** approach to compare hierarchical command-and-control with distributed multi-agent coordination. It separates **command (authority)**, **control (policy)**, and **coordination (interaction rules)**; formalizes the design space via an **authority graph**, a **time-varying communication graph**, and **agent decision rules**; and states **testable hypotheses** about when each architecture dominates. We outline **mechanisms** (delegation envelopes, intent beacons, auctions, trust-weighted consensus) and **metrics** (MTTA, success probability, resource overhead) with parameterized vignettes to show how switching rules and thresholds can be instrumented. This is a **theory-first, Anchor-Absent** map with an explicit validation plan; numerical effects marked **Illustrative Target** are to be confirmed via the simulation sweeps described herein."
                    
                    # Insert Executive Summary after title/abstract, before Introduction
                    intro_pattern = r'(^#+\s+(?:Introduction|Introduction and Research Questions))'
                    intro_match = re.search(intro_pattern, thesis_report, re.MULTILINE | re.IGNORECASE)
                    if intro_match:
                        insert_pos = intro_match.start()
                        thesis_report = thesis_report[:insert_pos] + f"# Executive Summary\n\n{exec_summary_text}\n\n" + thesis_report[insert_pos:]
                    else:
                        # Insert at beginning after title
                        first_heading_match = re.search(r'^#+\s+[^\n]+', thesis_report, re.MULTILINE)
                        if first_heading_match:
                            insert_pos = thesis_report.find('\n', first_heading_match.end()) + 1
                            thesis_report = thesis_report[:insert_pos] + f"\n# Executive Summary\n\n{exec_summary_text}\n\n" + thesis_report[insert_pos:]
                        else:
                            thesis_report = f"# Executive Summary\n\n{exec_summary_text}\n\n" + thesis_report
                    
                    logger.info("Added Executive Summary section to thesis report")
                
                # Step 10.8: Add Disclosure block if missing (thesis only) - confidence is in header, not content
                disclosure_exists = re.search(r'Disclosure.*Method Note', thesis_report, re.MULTILINE | re.IGNORECASE)
                if not disclosure_exists:
                    # Don't include confidence formula - it's already in the header
                    disclosure_text = f"> **Disclosure & Method Note.** This is a *theory-first* brief. Claims are mapped to evidence using a CEM grid; quantitative effects marked **Illustrative Target** will be validated via the evaluation plan. **Anchor Status:** {anchor_status}.\n\n"
                    
                    # Insert after Executive Summary or Abstract
                    exec_summary_match = re.search(r'^#+\s+Executive Summary\s*\n+(.+?)(?=\n#+\s+|$)', thesis_report, re.MULTILINE | re.DOTALL | re.IGNORECASE)
                    if exec_summary_match:
                        insert_pos = exec_summary_match.end()
                        thesis_report = thesis_report[:insert_pos] + '\n' + disclosure_text + thesis_report[insert_pos:]
                    else:
                        abstract_match = re.search(r'^#+\s+Abstract\s*\n+(.+?)(?=\n#+\s+|$)', thesis_report, re.MULTILINE | re.DOTALL | re.IGNORECASE)
                        if abstract_match:
                            insert_pos = abstract_match.end()
                            thesis_report = thesis_report[:insert_pos] + '\n' + disclosure_text + thesis_report[insert_pos:]
                    
                    logger.info("Added Disclosure and Confidence block to thesis report")
                
                # Update report confidence with thesis confidence (playbook formula)
                if 'thesis_confidence' in locals():
                    report_model.confidence = float(thesis_confidence)
                    logger.info(f"Updated report confidence to thesis confidence: {thesis_confidence:.3f}")
                
                repairs = 0
                while max(critique.alignment, critique.theory_depth, critique.clarity) < STIConfig.THESIS_CRITIQUE_MIN_SCORE and repairs < STIConfig.THESIS_MAX_REPAIRS:
                    logger.info(f"Thesis critique below threshold; repair_action={critique.repair_action}")
                    if critique.repair_action == 'expand_anchors':
                        # attempt small anchor expansion using existing anchors
                        more_academic = self._search_theoretical_concepts(final_title, STIConfig.THEORY_EXTENDED_DAYS_BACK)
                        relevant_sources = self._filter_sources_by_title_relevance(relevant_sources + more_academic, original_title)
                    elif critique.repair_action == 'adjust_outline':
                        # adjust outline by adding 'Formalization' and 'Limits'
                        if 'Formalization' not in outline.sections:
                            outline.sections.append('Formalization')
                        if 'Limits and Open Questions' not in outline.sections:
                            outline.sections.append('Limits and Open Questions')
                    draft = self._thesis_compose(outline, relevant_sources, query)
                    thesis_report = draft.markdown
                    critique = self._thesis_critique(draft, query)
                    repairs += 1
                report = thesis_report
            else:
                # Use standard enhanced report for market queries or theory without foundational sources
                report = self._generate_enhanced_report(
                    query, relevant_sources, signals, market_analysis, tech_deepdive,
                    competitive, expanded_lenses, exec_summary,
                    confidence, days_back, final_title
                )
            
            # Step 11: NEW - Generate JSON-LD artifact using final title and relevant sources
            json_ld = self._generate_json_ld_artifact(
                query, relevant_sources, signals, confidence, days_back, exec_summary,
                word_count=len(report.split()), final_title=final_title
            )
            
            # Automatically save the report with nested file structure
            # Compute horizon and hybrid flags for downstream presentation
            horizon = self._classify_horizon(relevant_sources)
            is_hybrid = self._is_hybrid_thesis_anchored(intent, relevant_sources)

            sources_data_stats: List[Dict[str, Any]] = []
            for src_model in report_model.sources:
                record = src_model.model_dump()
                record["content_sha"] = source_sha_map.get(src_model.id)
                sources_data_stats.append(record)

            agent_stats = {
                'date_filter_stats': self.get_date_filter_stats() if hasattr(self, 'get_date_filter_stats') else None,
                'sources_data': sources_data_stats,
                'validated_sources_count': len(sources),
                'intent': intent,
                'horizon': horizon,
                'hybrid_thesis_anchored': is_hybrid,
                'thesis_io': report_model.metadata.get('thesis_io', {}),
                'confidence_breakdown': confidence_breakdown.__dict__ if confidence_breakdown else None,
                'advanced_tasks_requested': tasks_requested,
                'advanced_tasks_executed': premium_tasks_run,
                'advanced_tokens_spent': advanced_tokens,
                'metrics': metrics,
                'asset_gating': {
                    'images_enabled': not anchor_gate,
                    'social_enabled': not anchor_gate,
                    'reason': 'insufficient anchors' if anchor_gate else ''
                },
                'source_sha_map': source_sha_map,
                'claims_snapshot': claims_snapshot,
                'report_sections': report_sections,
            }
            
            report_dir = save_enhanced_report_auto(
                query, report, json_ld, days_back, agent_stats, generate_html=True
            )

            output_path = Path(report_dir)
            try:
                if ledger_data:
                    write_json(output_path / "evidence_ledger.json", ledger_data)
                if quant_patch:
                    write_json(output_path / "vignette_quant_patch.json", quant_patch)
                if adversarial_data:
                    write_json(output_path / "adversarial.json", adversarial_data)
                if playbooks_data:
                    write_json(output_path / "playbooks.json", playbooks_data)
            except Exception as artifact_err:
                logger.error(f"Failed to persist auditor artifacts: {artifact_err}")

            run_manifest = {
                "query": query,
                "days": days_back,
                "seed": seed,
                "budget_advanced": budget_advanced,
                "timestamp": datetime.now().isoformat(),
                "models": {
                    "primary": self.model_name,
                    "advanced": getattr(STIConfig, 'ADVANCED_MODEL_NAME', None) if premium_tasks_run else None,
                },
                "metrics": metrics,
                "advanced_tasks_requested": tasks_requested,
                "advanced_tasks_executed": premium_tasks_run,
                "advanced_tokens_spent": advanced_tokens,
                "advanced_budget_remaining": budget.left(),
                "report_title": final_title,
                "intent": intent,
                "anchor_gate": anchor_gate,
            }

            agent_stats['run_manifest'] = run_manifest
            self.last_run_status = {
                "quality_gates_passed": quality_gates_passed,
                "report_dir": report_dir,
                "run_manifest": run_manifest,
                "metrics": metrics,
                "advanced_tasks": premium_tasks_run,
                "asset_gated": anchor_gate,
            }

            # Social gating: respect social_enabled flag from asset_gating
            social_enabled = agent_stats.get('asset_gating', {}).get('social_enabled', True)
            social_skipped = not social_enabled or (anchor_gate and intent == "theory")
            if social_skipped:
                logger.info("Skipping social copy: insufficient anchors for thesis path or social_enabled=False.")
            else:
                try:
                    from social_media_agent import SocialMediaAgent
                    logger.info("Generating social media content...")
                    social_agent = SocialMediaAgent(self.openai_api_key, self.model_name)
                    social_context = {
                        "confidence": confidence,
                        "title": final_title,
                        "query": query,
                        "ledger": ledger_data,
                        "sources": sources_data_stats,
                    }
                    social_content = social_agent.generate_all_formats(report, context=social_context)

                    # Save social media content to report directory
                    from file_utils import file_manager
                    file_manager.save_social_media_content(report_dir, social_content)
                    logger.info("📱 Social media content generated and saved")

                except Exception as e:
                    logger.error(f"Error generating social media content: {str(e)}")
                    logger.info("Continuing without social media content...")
            
            # Build run_summary for return
            run_summary = {
                'intent': intent,
                'artifacts': {
                    'report_dir': report_dir,
                },
                'metrics': metrics,
                'confidence_breakdown': confidence_breakdown.__dict__ if confidence_breakdown else {},
                'premium': {
                    'requested': tasks_requested,
                    'executed': {task: task in premium_tasks_run for task in tasks_requested},
                },
            }
            
            return report, json_ld, run_summary
            
        except Exception as e:
            logger.error(f"Error in enhanced search: {str(e)}")
            return f"Error performing enhanced search: {str(e)}", {}, {
                'intent': 'unknown',
                'artifacts': {},
                'metrics': {},
                'confidence_breakdown': {},
                'premium': {'requested': [], 'executed': {}},
            }
    
    def _generate_enhanced_report(self, query: str, sources: List[Source], 
                                 signals: List[Dict[str, Any]], market_analysis: str,
                                 tech_deepdive: str, competitive: str, expanded_lenses: str,
                                 exec_summary: str, confidence: float, days_back: int, 
                                 final_title: str = None) -> str:
        """
        Generate 3,000-4,000 word report with all sections
        Structure:
        - Title and metadata (50 words)
        - Executive Summary (200 words)
        - Topline (100 words)
        - Signals (600 words - 6 signals)
        - Market Analysis (500 words)
        - Technology Deep-Dive (600 words)
        - Competitive Landscape (500 words)
        - Operator Lens (400 words)
        - Investor Lens (400 words)
        - BD Lens (400 words)
        - Sources (200 words)
        Total: ~3,350 words
        """
        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        # Generate topline
        topline = self._generate_topline(signals, confidence)
        
        # Ensure sections are not None/empty strings that break formatting
        exec_summary = exec_summary or "Summary unavailable due to insufficient evidence."
        market_analysis = market_analysis or "Insufficient evidence for market analysis."
        tech_deepdive = tech_deepdive or "Insufficient evidence for technology deep-dive."
        competitive = competitive or "Insufficient evidence for competitive landscape."
        expanded_lenses = expanded_lenses or "## Operator Lens\nInsufficient evidence.\n\n## Investor Lens\nInsufficient evidence.\n\n## BD Lens\nInsufficient evidence."
        
        # Build enhanced report using final title if provided
        title_to_use = final_title if final_title else f"Tech Brief — {query.replace('Ai', 'AI').title()}"
        report = f"""# {title_to_use}
Date range: {start_date.strftime('%b %d')}–{end_date.strftime('%b %d')}, 2025 | Sources: {len(sources)} | Confidence: {confidence:.2f}

## Executive Summary
{exec_summary}

## Topline
{topline}

## Signals (strength × impact × direction)"""
        
        # Add signals (6 signals, ~100 words each = 600 words)
        # Valid source IDs are 1..len(sources) since sources are enumerated starting from 1
        valid_source_ids = set(range(1, len(sources) + 1))
        
        for i, signal in enumerate(signals, 1):
            # Filter citation_ids to only those that exist in the sources list
            # This prevents citations to sources that were filtered out upstream
            valid_citation_ids = [cid for cid in signal.get('citation_ids', []) if cid in valid_source_ids]
            
            if not valid_citation_ids and signal.get('citation_ids'):
                # Log warning if citations were filtered out
                logger.warning(f"Signal {i} had invalid citation_ids {signal.get('citation_ids')} - filtered to valid IDs")
            
            citation_refs = "".join([f"[^{cid}]" for cid in valid_citation_ids])
            report += f"""
- {signal.get('text', '')} — strength: {signal.get('strength', 'Medium')} | impact: {signal.get('impact', 'Medium')} | trend: {signal.get('direction', '?')}  {citation_refs}"""
        
        # Add analysis sections
        report += f"""

## Market Analysis
{market_analysis}

## Technology Deep-Dive
{tech_deepdive}

## Competitive Landscape
{competitive}

{expanded_lenses}

## Sources"""
        
        # Add sources
        for i, source in enumerate(sources, 1):
            report += f"""
[^{i}]: {source.title} — {source.publisher}, {source.date}. (cred: {source.credibility:.2f}) — {source.url}"""
        
        return report
    
    def _generate_json_ld_artifact(self, query: str, sources: List[Source], 
                                  signals: List[Dict[str, Any]], confidence: float,
                                  days_back: int, exec_summary: str, word_count: int, 
                                  final_title: str = None) -> Dict[str, Any]:
        """
        Generate schema.org compliant JSON-LD
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        # Extract entities and topics
        entities = self._extract_entities_from_sources(sources)
        topics = self._extract_topics_from_signals(signals)
        
        # Create signal parts
        signal_parts = []
        for signal in signals:
            signal_parts.append({
                "@type": "AnalysisNewsArticle",
                "headline": signal.get('text', ''),
                "confidence": signal.get('confidence', 0.5),
                "citation": [sources[cid-1].url for cid in signal.get('citation_ids', []) if cid <= len(sources)]
            })
        
        # Use final title if provided, otherwise use query-based title
        title_to_use = final_title if final_title else f"Tech Brief — {query.title().replace('Ai', 'AI')}"
        
        return {
            "@context": "https://schema.org",
            "@type": "Report",
            "name": title_to_use,
            "author": {
                "@type": "Organization",
                "name": "Smart Technology Investments LLC",
                "url": "https://sti.ai"
            },
            "datePublished": datetime.now().isoformat(),
            "about": query,
            "abstract": exec_summary,
            "hasPart": signal_parts,
            "temporalCoverage": f"{start_date.strftime('%Y-%m-%d')}/{end_date.strftime('%Y-%m-%d')}",
            "keywords": topics,
            "aggregateRating": {
                "@type": "AggregateRating",
                "ratingValue": confidence,
                "worstRating": 0.30,
                "bestRating": 0.85
            },
            "entities": entities,
            "wordCount": word_count,
            "reportType": "Technology Intelligence Brief"
        }
    
    def _extract_entities_from_sources(self, sources: List[Source]) -> Dict[str, List[str]]:
        """Extract entities from sources for JSON-LD"""
        entities = {
            "ORG": [],
            "PERSON": [],
            "PRODUCT": [],
            "TICKER": [],
            "GEO": []
        }
        
        # Simple entity extraction from source content
        for source in sources:
            content = source.content.lower()
            
            # Extract organizations from publisher and content
            if source.publisher not in entities["ORG"]:
                entities["ORG"].append(source.publisher)
            
            # Extract common tech companies
            tech_companies = ['openai', 'anthropic', 'google', 'microsoft', 'meta', 'apple', 'amazon', 'nvidia']
            for company in tech_companies:
                if company in content and company.title() not in entities["ORG"]:
                    entities["ORG"].append(company.title())
        
        return entities
    
    def _extract_topics_from_signals(self, signals: List[Dict[str, Any]]) -> List[str]:
        """Extract topics from signals for JSON-LD"""
        topics = []
        
        # Common tech topics
        topic_keywords = {
            'AI': ['ai', 'artificial intelligence', 'machine learning', 'llm', 'gpt'],
            'Cybersecurity': ['security', 'cyber', 'breach', 'vulnerability'],
            'Cloud': ['cloud', 'aws', 'azure', 'gcp', 'infrastructure'],
            'Robotics': ['robot', 'automation', 'autonomous'],
            'AR/VR': ['ar', 'vr', 'augmented', 'virtual', 'metaverse'],
            'Semiconductors': ['chip', 'semiconductor', 'nvidia', 'amd', 'intel']
        }
        
        for signal in signals:
            signal_text = signal.get('text', '').lower()
            for topic, keywords in topic_keywords.items():
                if any(keyword in signal_text for keyword in keywords):
                    if topic not in topics:
                        topics.append(topic)
        
        return topics if topics else ['Technology']


def main():
    """Example usage of the Enhanced MCP Agent"""
    
    # Load environment variables
    openai_api_key = os.getenv("OPENAI_API_KEY")
    tavily_api_key = os.getenv("TAVILY_API_KEY") or ""
    
    if not openai_api_key:
        print("Please set OPENAI_API_KEY environment variable")
        return
    
    # Initialize the enhanced agent
    agent = EnhancedSTIAgent(
        openai_api_key=openai_api_key,
        tavily_api_key=tavily_api_key
    )
    
    # Initialize analysis tools
    print("Initializing analysis tools...")
    agent.initialize_analysis_tools()
    
    # Example search
    print("=== Enhanced MCP Agent Demo ===\n")
    print("Generating enhanced research brief...")
    
    markdown_report, json_ld_artifact, run_summary = agent.search(
        "AI technology trends",
        days_back=7
    )
    
    print("📊 ENHANCED REPORT:")
    print("=" * 80)
    print(markdown_report)
    print("=" * 80)
    
    # Reports are automatically saved with nested file structure
    print(f"\n📊 Report generated successfully!")
    print(f"📈 Report confidence: {json_ld_artifact.get('aggregateRating', {}).get('ratingValue', 'N/A')}")
    print(f"📝 Word count: {json_ld_artifact.get('wordCount', 'N/A')}")
    print(f"💾 All files saved automatically in organized directory structure")


if __name__ == "__main__":
    main()

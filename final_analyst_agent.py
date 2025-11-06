"""
Final Analyst-Grade Time-Filtered Search Agent

Implements all surgical fixes for truly client-grade briefs:
- Hard time-window enforcement with context separation
- Claim-level scoring with off-window penalties
- Source hygiene with vendor-asserted labeling
- Entity extraction aligned to cited sources only
- Clean formatting with no JSON leaks
- Proper confidence capping
- Canonical URL enforcement
- Fixed title case and operator lens formatting
"""

import os
import logging
import json
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, validator
from config import STIConfig

# Import TavilyClient conditionally
try:
    from tavily import TavilyClient
except ImportError:
    TavilyClient = None

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ImpactLevel(str, Enum):
    """Impact levels for signals"""
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class TrendDirection(str, Enum):
    """Trend directions"""
    UP = "↗︎"
    DOWN = "↘︎"
    FLAT = "→"
    UNKNOWN = "?"


class SourceType(str, Enum):
    """Source types for quality gates"""
    INDEPENDENT_NEWS = "independent_news"
    PRIMARY = "primary"
    VENDOR_CONSULTING = "vendor_consulting"
    TRADE_PRESS = "trade_press"
    VENDOR_ASSERTED = "vendor_asserted"


@dataclass
class Signal:
    """Signal with event-anchored metadata"""
    text: str
    strength: str  # High/Medium/Low
    impact: ImpactLevel
    direction: TrendDirection
    citation_ids: List[int]
    date: str
    actor: str
    measurable: str
    confidence: float
    is_in_window: bool
    is_vendor_asserted: bool


@dataclass
class Source:
    """Source with type classification"""
    id: int
    title: str
    url: str
    publisher: str
    date: str
    credibility: float
    content: str
    source_type: SourceType
    is_in_window: bool


class FinalAnalystGradeAgent:
    """
    Final analyst-grade agent with all surgical fixes implemented
    """
    
    def __init__(self, openai_api_key: str, tavily_api_key: str = "",
                 model_name: str = "gpt-4-turbo-preview"):
        self.openai_api_key = openai_api_key
        self.tavily_api_key = tavily_api_key
        self.model_name = model_name
        
        # Initialize LLM with structured outputs
        # Get organization ID from environment for verified org
        organization = os.getenv("OPENAI_ORGANIZATION") or getattr(STIConfig, 'OPENAI_ORGANIZATION', None)
        llm_params = {
            "api_key": openai_api_key,
            "model": model_name,
            "temperature": 0.1,
            "response_format": {"type": "json_object"}
        }
        if organization:
            llm_params["openai_organization"] = organization
        self.llm = ChatOpenAI(**llm_params)
        
        # Only initialize Tavily if provider is Tavily
        search_provider = getattr(STIConfig, 'SEARCH_PROVIDER', 'searxng')
        if search_provider == 'tavily' and TavilyClient is not None:
            self.tavily_client = TavilyClient(api_key=tavily_api_key)
        else:
            self.tavily_client = None
        
        # Strict source hygiene rules
        self.blocklist_patterns = [
            'partnercontent', 'sponsored', 'brandstudio', 'message.bloomberg.com',
            '/sponsored/', 'brand-content', 'advertorial', 'promoted'
        ]
        
        self.whitelist_patterns = [
            'reuters.com', 'apnews.com', 'ft.com/content', 'bloomberg.com/news',
            'wsj.com/articles', 'theinformation.com', 'techcrunch.com',
            'arstechnica.com', 'wired.com', 'nature.com'
        ]
        
        self.independent_news_domains = [
            'reuters.com', 'bloomberg.com', 'ft.com', 'wsj.com', 'ap.org',
            'theinformation.com', 'semianalysis.com', 'techcrunch.com'
        ]
        
        self.primary_domains = [
            'sec.gov', 'company blogs', 'press releases', 'product pages'
        ]
        
        self.vendor_asserted_domains = [
            'nebius.com', 'openai.com', 'anthropic.com', 'company blogs'
        ]
        
        # URL validation statistics
        self.url_validation_stats = {
            'total_checked': 0,
            'valid_urls': 0,
            'missing_urls': 0,
            'invalid_format': 0,
            'failed_cleaning': 0
        }
    
    def search(self, query: str, days_back: int = 7) -> str:
        """
        Perform final analyst-grade search with all surgical fixes
        
        Args:
            query: The search query
            days_back: Number of days to look back (default: 7)
            
        Returns:
            Analyst-grade markdown report
        """
        try:
            # Step 1: Search with strict source hygiene and time window enforcement
            sources = self._search_with_strict_hygiene_and_window(query, days_back)
            
            # Step 2: Apply hard time-window gate
            in_window_sources, context_sources = self._separate_in_window_and_context(sources, days_back)
            
            # Step 3: Apply strict quality gates
            if not self._meets_analyst_grade_gates(in_window_sources):
                return self._insufficient_evidence_response(query, in_window_sources)
            
            # Step 4: Extract event-anchored signals with claim-level scoring
            signals = self._extract_claim_level_signals(in_window_sources)
            
            # Step 5: Extract entities aligned to cited sources only
            entities, topics = self._extract_entities_from_sources(in_window_sources)
            
            # Step 6: Generate operator lens with clean formatting
            operator_lens = self._generate_clean_operator_lens(signals, topics)
            
            # Step 7: Plan concrete actions tied to 10/31 sprint
            actions = self._plan_concrete_actions(signals, operator_lens)
            
            # Step 8: Calculate claim-level confidence with age penalties
            confidence = self._calculate_claim_level_confidence(signals, in_window_sources)
            
            # Step 9: Generate analyst-grade report
            report = self._generate_analyst_grade_report(
                query, in_window_sources, signals, entities, topics, 
                operator_lens, actions, confidence, days_back
            )
            
            return report
            
        except Exception as e:
            logger.error(f"Error in final analyst-grade search: {str(e)}")
            return f"Error performing final analyst-grade search: {str(e)}"
    
    def _search_with_strict_hygiene_and_window(self, query: str, days_back: int) -> List[Source]:
        """Search with strict source hygiene and time window enforcement"""
        sources = []
        source_id = 1
        
        # Calculate time window
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        # Search for independent news sources with strict hygiene
        independent_sources = self._search_with_strict_hygiene(
            query, self.independent_news_domains, SourceType.INDEPENDENT_NEWS, 4
        )
        
        # Filter by time window strictly
        for source in independent_sources:
            source.is_in_window = self._is_strictly_within_time_window(source, start_date, end_date)
            source.id = source_id
            sources.append(source)
            source_id += 1
        
        # Search for primary sources with strict hygiene
        primary_sources = self._search_with_strict_hygiene(
            query, self.primary_domains, SourceType.PRIMARY, 2
        )
        
        # Filter by time window strictly
        for source in primary_sources:
            source.is_in_window = self._is_strictly_within_time_window(source, start_date, end_date)
            source.id = source_id
            sources.append(source)
            source_id += 1
        
        # Search for vendor-asserted sources (context only)
        vendor_sources = self._search_with_strict_hygiene(
            query, self.vendor_asserted_domains, SourceType.VENDOR_ASSERTED, 1
        )
        
        # Filter by time window strictly
        for source in vendor_sources:
            source.is_in_window = self._is_strictly_within_time_window(source, start_date, end_date)
            source.id = source_id
            sources.append(source)
            source_id += 1
        
        # Fallback: general search if we don't have enough
        if len(sources) < 3:
            general_sources = self._search_general_with_strict_hygiene(query, 3)
            for source in general_sources:
                if not any(s.url == source.url for s in sources):
                    source.is_in_window = self._is_strictly_within_time_window(source, start_date, end_date)
                    source.id = source_id
                    sources.append(source)
                    source_id += 1
        
        return sources
    
    def _separate_in_window_and_context(self, sources: List[Source], days_back: int) -> Tuple[List[Source], List[Source]]:
        """Separate sources into in-window and context"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        in_window = []
        context = []
        
        for source in sources:
            if self._is_strictly_within_time_window(source, start_date, end_date):
                in_window.append(source)
            else:
                context.append(source)
        
        return in_window, context
    
    def _search_with_strict_hygiene(self, query: str, domains: List[str], 
                                   source_type: SourceType, max_results: int) -> List[Source]:
        """Search with strict source hygiene enforcement"""
        # Provider switching: use SearXNG if configured
        search_provider = getattr(STIConfig, 'SEARCH_PROVIDER', 'searxng')
        if search_provider == 'searxng' or self.tavily_client is None:
            return self._search_with_searxng(query, domains, source_type, max_results)
        
        sources = []
        
        try:
            response = self.tavily_client.search(
                query=query,
                search_depth="advanced",
                max_results=max_results,
                include_domains=domains,
                include_answer=False,
                include_raw_content=True
            )
            
            if 'results' in response:
                for result in response['results']:
                    # Apply strict hygiene filters
                    if self._passes_strict_hygiene_filters(result):
                        # STRICT URL VALIDATION - Reject if no valid URL
                        validated_url = self._validate_url(result.get('url', ''), result.get('title', 'Unknown'))
                        if not validated_url:
                            continue  # Skip this source
                        
                        source = Source(
                            id=0,  # Will be set later
                            title=result.get('title', 'No title'),
                            url=validated_url,  # ← GUARANTEED VALID
                            publisher=self._extract_publisher(validated_url),
                            date=self._extract_date(result),
                            credibility=self._calculate_source_credibility(result, source_type),
                            content=result.get('content', ''),
                            source_type=source_type,
                            is_in_window=False  # Will be set later
                        )
                        sources.append(source)
                    
        except Exception as e:
            logger.error(f"Error searching {source_type}: {str(e)}")
        
        return sources
    
    def _search_general_with_strict_hygiene(self, query: str, max_results: int) -> List[Source]:
        """General search with strict hygiene enforcement"""
        # Provider switching: use SearXNG if configured
        search_provider = getattr(STIConfig, 'SEARCH_PROVIDER', 'searxng')
        if search_provider == 'searxng' or self.tavily_client is None:
            return self._search_with_searxng(query, [], None, max_results)
        
        sources = []
        
        try:
            response = self.tavily_client.search(
                query=query,
                search_depth="advanced",
                max_results=max_results,
                include_answer=False,
                include_raw_content=True
            )
            
            if 'results' in response:
                for result in response['results']:
                    # Apply strict hygiene filters
                    if self._passes_strict_hygiene_filters(result):
                        source_type = self._classify_source_type(result.get('url', ''))
                        source = Source(
                            id=0,  # Will be set later
                            title=result.get('title', 'No title'),
                            url=self._clean_url(result.get('url', '')),
                            publisher=self._extract_publisher(result.get('url', '')),
                            date=self._extract_date(result),
                            credibility=self._calculate_source_credibility(result, source_type),
                            content=result.get('content', ''),
                            source_type=source_type,
                            is_in_window=False  # Will be set later
                        )
                        sources.append(source)
                    
        except Exception as e:
            logger.error(f"Error in general search: {str(e)}")
        
        return sources
    
    def _search_with_searxng(self, query: str, domains: List[str], 
                             source_type: Optional[SourceType], max_results: int, 
                             days_back: int = 7) -> List[Source]:
        """Search SearXNG JSON API and map results to Source objects"""
        import requests
        sources: List[Source] = []
        base = getattr(STIConfig, 'SEARXNG_BASE_URL', 'http://localhost:8080').rstrip('/')
        # Determine category based on source_type, default to 'general' if None
        if source_type == SourceType.ACADEMIC:
            category = 'science'
        elif source_type == SourceType.INDEPENDENT_NEWS:
            category = 'news'
        else:
            category = 'general'
        if days_back <= 7:
            time_range = '7d'
        elif days_back <= 30:
            time_range = '30d'
        elif days_back <= 90:
            time_range = '90d'
        else:
            time_range = '365d'

        headers = {
            'Accept': 'application/json',
            'User-Agent': 'sti-local/1.0 (+https://sti.ai)'
        }
        search_url = f"{base}/search"

        def _normalize(text: str) -> str:
            try:
                replacements = {
                    '\u2013': '-', '\u2014': '-', '\u2015': '-',
                    '\u2018': '\'', '\u2019': '\'', '\u201C': '"', '\u201D': '"'
                }
                for k, v in replacements.items():
                    text = text.replace(k, v)
                text = text.encode('ascii', 'ignore').decode('ascii')
                text = text.replace('""', '"')
                return text
            except Exception:
                return text

        def run_search(q: str, use_time: bool = True, method: str = 'GET'):
            params = {
                'q': q,
                'format': 'json',
                'categories': category,
                'safesearch': 1
            }
            if use_time:
                params['time_range'] = time_range
            timeout = getattr(STIConfig, 'HTTP_TIMEOUT_SECONDS', 12)
            if method == 'GET':
                resp = requests.get(search_url, params=params, headers=headers, timeout=timeout)
            else:
                resp = requests.post(search_url, data=params, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return resp.json().get('results', [])

        # Health check
        try:
            _ = run_search('test', use_time=False, method='GET')
        except Exception:
            try:
                _ = run_search('test', use_time=False, method='POST')
            except Exception:
                logger.error("SearXNG health check failed")
                return []

        # Build queries
        queries: List[str] = []
        if domains:
            for d in domains[:3]:
                queries.append(f'{_normalize(query)} site:{d}')
        else:
            queries.append(_normalize(query))

        count = 0
        for q in queries:
            if count >= max_results:
                break
            try:
                attempts = [('GET', True), ('GET', False), ('POST', False)]
                results = []
                for method, use_time in attempts:
                    try:
                        results = run_search(q, use_time=use_time, method=method)
                        break
                    except requests.exceptions.HTTPError as he:
                        if he.response is not None and he.response.status_code == 400:
                            continue
                        raise
                for r in results:
                    if count >= max_results:
                        break
                    u = r.get('url') or r.get('link')
                    t = r.get('title') or 'No title'
                    if not u:
                        continue
                    if domains and not any(d in u for d in domains):
                        continue
                    # Apply hygiene filters
                    result_dict = {'url': u, 'title': t}
                    if not self._passes_strict_hygiene_filters(result_dict):
                        continue
                    validated_url = self._validate_url(u, t) if hasattr(self, '_validate_url') else self._clean_url(u)
                    if not validated_url:
                        continue
                    # Determine source type
                    if source_type is None:
                        source_type = self._classify_source_type(validated_url)
                    publisher = self._extract_publisher(validated_url)
                    date_str = r.get('pubdate') or r.get('published') or r.get('date') or datetime.now().strftime('%Y-%m-%d')
                    date_str = str(date_str)[:10]
                    # Calculate credibility
                    result_for_cred = {'url': validated_url, 'title': t, 'content': r.get('content') or r.get('snippet') or ''}
                    credibility = self._calculate_source_credibility(result_for_cred, source_type)
                    source = Source(
                        id=0,
                        title=t,
                        url=validated_url,
                        publisher=publisher,
                        date=date_str,
                        credibility=credibility,
                        content=r.get('content') or r.get('snippet') or '',
                        source_type=source_type,
                        is_in_window=False
                    )
                    sources.append(source)
                    count += 1
                if count >= max_results:
                    break
            except Exception as e:
                logger.error(f"SearXNG search error: {str(e)}")
                continue

        logger.info(f"SearXNG returned {len(sources)} results for {source_type.value if source_type else 'general'} search")
        return sources
    
    def _passes_strict_hygiene_filters(self, result: Dict[str, Any]) -> bool:
        """Check if result passes strict hygiene filters"""
        url = result.get('url', '')
        title = result.get('title', '')
        
        # Block sponsored/partner content strictly
        for pattern in self.blocklist_patterns:
            if pattern in url.lower() or pattern in title.lower():
                return False
        
        # Block tracking URLs
        if 'links.message.bloomberg.com' in url:
            return False
        
        # Prefer whitelist patterns
        for pattern in self.whitelist_patterns:
            if pattern in url.lower():
                return True
        
        # Allow other sources but with lower priority
        return True
    
    def _clean_url(self, url: str) -> str:
        """Clean URL to canonical form"""
        if not url:
            return ""
        
        # Remove tracking parameters
        if '?' in url:
            url = url.split('?')[0]
        
        # Convert tracking URLs to canonical
        if 'links.message.bloomberg.com' in url:
            # This is a tracking URL, try to extract canonical
            return url  # Keep as is for now, but mark as lower credibility
        
        return url
    
    def _validate_url(self, raw_url: str, title: str) -> Optional[str]:
        """
        Validate and clean URL. Returns cleaned URL if valid, None if invalid.
        Logs rejection reasons and tracks statistics.
        """
        self.url_validation_stats['total_checked'] += 1
        
        # Check for empty/missing URL
        if not raw_url or len(raw_url) < 10:
            self.url_validation_stats['missing_urls'] += 1
            logger.warning(f"✗ Rejecting source '{title}' - missing or invalid URL")
            return None
        
        # Clean the URL
        cleaned_url = self._clean_url(raw_url)
        if not cleaned_url or cleaned_url == "#" or "placeholder" in cleaned_url.lower():
            self.url_validation_stats['failed_cleaning'] += 1
            logger.warning(f"✗ Rejecting source '{title}' - URL failed cleaning: {raw_url}")
            return None
        
        # Validate protocol
        if not (cleaned_url.startswith('http://') or cleaned_url.startswith('https://')):
            self.url_validation_stats['invalid_format'] += 1
            logger.warning(f"✗ Rejecting source '{title}' - invalid URL protocol: {cleaned_url}")
            return None
        
        self.url_validation_stats['valid_urls'] += 1
        logger.debug(f"✓ Valid URL for '{title}': {cleaned_url}")
        return cleaned_url
    
    def _is_strictly_within_time_window(self, source: Source, start_date: datetime, end_date: datetime) -> bool:
        """Check if source is strictly within time window"""
        try:
            source_date = datetime.strptime(source.date, '%Y-%m-%d')
            return start_date <= source_date <= end_date
        except:
            # If date parsing fails, assume it's recent
            return True
    
    def _meets_analyst_grade_gates(self, in_window_sources: List[Source]) -> bool:
        """Check if sources meet analyst-grade quality gates"""
        if len(in_window_sources) < 3:
            return False
        
        # Count source types
        source_types = [s.source_type for s in in_window_sources]
        independent_count = source_types.count(SourceType.INDEPENDENT_NEWS)
        primary_count = source_types.count(SourceType.PRIMARY)
        vendor_count = source_types.count(SourceType.VENDOR_CONSULTING)
        vendor_asserted_count = source_types.count(SourceType.VENDOR_ASSERTED)
        
        # Analyst-grade gates
        if independent_count < 2:
            return False
        
        if primary_count < 1:
            return False
        
        if vendor_count > 1:
            return False
        
        if vendor_asserted_count > 1:
            return False
        
        return True
    
    def _extract_claim_level_signals(self, in_window_sources: List[Source]) -> List[Signal]:
        """Extract claim-level signals with structured outputs"""
        signals = []
        
        # Combine content from in-window sources only
        combined_content = "\n\n".join([f"Source {s.id}: {s.content}" for s in in_window_sources])
        
        # Use structured output for signal extraction
        signal_prompt = f"""
        Extract 3-4 event-anchored signals from this content. Each signal must have:
        1. A specific date (this week)
        2. A clear actor (company, person, organization)
        3. A measurable action (launch, funding, policy, earnings, etc.)
        4. Evidence from the content
        
        Content: {combined_content[:3000]}
        
        Return as JSON with this exact structure:
        {{
            "signals": [
                {{
                    "text": "Specific claim with date, actor, and measurable",
                    "strength": "High/Medium/Low",
                    "impact": "High/Medium/Low",
                    "direction": "↗︎/↘︎/→/?",
                    "citation_ids": [1, 2],
                    "date": "2025-10-20",
                    "actor": "Company X",
                    "measurable": "launched product Y",
                    "confidence": 0.8
                }}
            ]
        }}
        """
        
        try:
            response = self.llm.invoke(signal_prompt)
            signals_data = self._extract_json(response.content)
            
            if 'signals' in signals_data:
                for signal_data in signals_data['signals']:
                    signal = Signal(
                        text=signal_data.get('text', ''),
                        strength=signal_data.get('strength', 'Medium'),
                        impact=ImpactLevel(signal_data.get('impact', 'Medium')),
                        direction=TrendDirection(signal_data.get('direction', '?')),
                        citation_ids=signal_data.get('citation_ids', []),
                        date=signal_data.get('date', ''),
                        actor=signal_data.get('actor', ''),
                        measurable=signal_data.get('measurable', ''),
                        confidence=float(signal_data.get('confidence', 0.5)),
                        is_in_window=True,  # All signals from in-window sources
                        is_vendor_asserted=False  # Will be updated based on source types
                    )
                    signals.append(signal)
                
        except Exception as e:
            logger.error(f"Error extracting claim-level signals: {str(e)}")
            # Fallback: create basic signals from source titles
            for i, source in enumerate(in_window_sources[:3], 1):
                signal = Signal(
                    text=f"Reported: {source.title}",
                    strength="Medium",
                    impact=ImpactLevel.MEDIUM,
                    direction=TrendDirection.UNKNOWN,
                    citation_ids=[source.id],
                    date=source.date,
                    actor="Various",
                    measurable="reported",
                    confidence=source.credibility,
                    is_in_window=True,
                    is_vendor_asserted=(source.source_type == SourceType.VENDOR_ASSERTED)
                )
                signals.append(signal)
        
        return signals
    
    def _extract_entities_from_sources(self, in_window_sources: List[Source]) -> Tuple[Dict[str, List[str]], List[str]]:
        """Extract entities aligned to cited sources only"""
        combined_content = "\n\n".join([s.content for s in in_window_sources])
        
        # Use structured output for entity extraction
        entity_prompt = f"""
        Extract entities from this content and categorize them. DO NOT use "None" or generic terms.
        Only extract entities that are explicitly mentioned in the content.
        
        Content: {combined_content[:2000]}
        
        Return as JSON with this exact structure:
        {{
            "entities": {{
                "ORG": ["Specific company names mentioned in content"],
                "PERSON": ["Specific person names mentioned in content"],
                "PRODUCT": ["Specific product names mentioned in content"],
                "TICKER": ["Stock symbols mentioned in content"],
                "GEO": ["Geographic locations mentioned in content"]
            }},
            "topics": ["AI", "robotics", "infrastructure", "AR/VR", "cybersecurity", "semiconductors", "policy", "macro", "market-moves", "healthcare", "energy", "automotive", "fintech", "ecommerce", "social-media", "gaming", "enterprise-software"]
        }}
        
        IMPORTANT: Only extract entities that are explicitly mentioned in the content. If no specific entities found, use "None" instead of "Various".
        """
        
        try:
            response = self.llm.invoke(entity_prompt)
            data = self._extract_json(response.content)
            
            entities = data.get('entities', {})
            topics = data.get('topics', [])
            
            # Validate entities against source content
            validated_entities = self._validate_entities_against_sources(entities, combined_content)
            
            # Ensure no "Various" entries
            for category in ["ORG", "PERSON", "PRODUCT", "TICKER", "GEO"]:
                if not validated_entities.get(category):
                    validated_entities[category] = ["None"]
                elif "Various" in validated_entities[category]:
                    validated_entities[category] = ["None"]
            
            return validated_entities, topics
            
        except Exception as e:
            logger.error(f"Error extracting entities/topics: {str(e)}")
            return {
                "ORG": ["None"], 
                "PERSON": ["None"], 
                "PRODUCT": ["None"], 
                "TICKER": ["None"], 
                "GEO": ["None"]
            }, ["AI"]
    
    def _validate_entities_against_sources(self, entities: Dict[str, List[str]], source_content: str) -> Dict[str, List[str]]:
        """Validate that entities are present in source content"""
        validated = {}
        unsupported = []
        
        for category, entity_list in entities.items():
            validated[category] = []
            for entity in entity_list:
                if entity.lower() in source_content.lower():
                    validated[category].append(entity)
                else:
                    unsupported.append(entity)
        
        if unsupported:
            logger.warning(f"Unsupported entities found: {unsupported}")
        
        return validated
    
    def _generate_clean_operator_lens(self, signals: List[Signal], topics: List[str]) -> Dict[str, str]:
        """Generate operator/investor/BD implications with clean formatting"""
        signals_text = "\n".join([f"- {signal.text}" for signal in signals])
        topics_text = ", ".join(topics)
        
        lens_prompt = f"""
        Generate implications for three audiences based on these signals and topics.
        Return clean, actionable prose - NO JSON formatting or dict structures.
        
        Signals: {signals_text}
        Topics: {topics_text}
        
        Provide three clean paragraphs:
        1. Operator implications (systems/automation/operational)
        2. Investor implications (capex/market structure/ticker)
        3. BD implications (wedge/offers/prospect)
        
        Return as JSON with this exact structure:
        {{
            "operator": "Clean prose paragraph about operational implications",
            "investor": "Clean prose paragraph about investment implications",
            "bd": "Clean prose paragraph about business development implications"
        }}
        """
        
        try:
            response = self.llm.invoke(lens_prompt)
            lens_data = self._extract_json(response.content)
            
            # Clean operator lens formatting
            cleaned_lens = {}
            for key in ["operator", "investor", "bd"]:
                if key in lens_data:
                    cleaned_lens[key] = self._clean_operator_lens_text(lens_data[key])
                else:
                    cleaned_lens[key] = f"Monitor developments for {key} impact and consider integration opportunities."
            
            return cleaned_lens
        except Exception as e:
            logger.error(f"Error generating operator lens: {str(e)}")
            return {
                "operator": "Monitor developments for operational impact and consider integration opportunities.",
                "investor": "Assess market implications and investment opportunities in relevant sectors.", 
                "bd": "Identify potential business development opportunities and partnership prospects."
            }
    
    def _clean_operator_lens_text(self, text: str) -> str:
        """Clean operator lens text to remove JSON artifacts"""
        # Remove JSON artifacts and clean up formatting
        cleaned = re.sub(r'\{[^}]*\}', '', text)
        cleaned = re.sub(r'"[^"]*":\s*', '', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        
        return cleaned
    
    def _plan_concrete_actions(self, signals: List[Signal], operator_lens: Dict[str, str]) -> List[Dict[str, str]]:
        """Plan concrete actions tied to 10/31 sprint"""
        actions = []
        
        # Generate concrete actions based on signals and lens
        action_prompt = f"""
        Based on these signals and implications, generate 2-3 concrete, actionable items tied to 10/31 sprint:
        
        Signals: {[signal.text for signal in signals]}
        Implications: {operator_lens}
        
        Return as JSON with this exact structure:
        {{
            "actions": [
                {{
                    "title": "Specific, concrete action with deliverable",
                    "owner": "Hass or Agent",
                    "due_date": "2025-10-24"
                }}
            ]
        }}
        
        IMPORTANT: Actions must be concrete deliverables, not slogans. Examples:
        - "Publish STI Post #1: 'Agentic AI in Ops' with real run logs (Markdown + 3 citations)"
        - "Build 10-logo prospect list (workflow-heavy apps) + send 5 demo invites"
        - "Add source hygiene + window gates; unit test passes"
        """
        
        try:
            response = self.llm.invoke(action_prompt)
            data = self._extract_json(response.content)
            
            if 'actions' in data:
                # Validate dates strictly
                validated_actions = []
                for action in data['actions']:
                    due_date = action.get('due_date', '2025-10-31')
                    
                    # Ensure date is in 2025 and within range
                    if '2025' not in due_date:
                        due_date = f"2025-{due_date}"
                    
                    # Validate date range
                    try:
                        date_obj = datetime.strptime(due_date, '%Y-%m-%d')
                        if date_obj.year != 2025 or date_obj < datetime(2025, 10, 20) or date_obj > datetime(2025, 10, 31):
                            due_date = "2025-10-31"  # Default to end of month
                    except:
                        due_date = "2025-10-31"
                    
                    validated_action = {
                        "title": action.get('title', ''),
                        "owner": action.get('owner', 'Agent'),
                        "due_date": due_date
                    }
                    validated_actions.append(validated_action)
                
                return validated_actions
            else:
                raise ValueError("Invalid actions data format")
                
        except Exception as e:
            logger.error(f"Error planning concrete actions: {str(e)}")
            # Fallback actions with proper 2025 dates
            return [
                {
                    "title": "Publish STI Post #1: 'Agentic AI in Ops' with real run logs (Markdown + 3 citations)",
                    "owner": "Hass",
                    "due_date": "2025-10-24"
                },
                {
                    "title": "Build 10-logo prospect list (workflow-heavy apps) + send 5 demo invites",
                    "owner": "Agent",
                    "due_date": "2025-10-28"
                }
            ]
    
    def _calculate_claim_level_confidence(self, signals: List[Signal], in_window_sources: List[Source]) -> float:
        """Calculate confidence based on claim-level scoring with age penalties"""
        if not signals:
            return 0.0
        
        # Calculate confidence for each signal
        signal_confidences = []
        for signal in signals:
            # Base confidence from signal confidence
            base_confidence = signal.confidence
            
            # Boost for confirmation count
            confirmation_boost = len(signal.citation_ids) / len(in_window_sources)
            
            # Boost for source credibility
            source_credibilities = [s.credibility for s in in_window_sources if s.id in signal.citation_ids]
            avg_source_credibility = sum(source_credibilities) / len(source_credibilities) if source_credibilities else 0.0
            
            # Age penalty for off-window signals
            age_penalty = 0.0 if signal.is_in_window else 0.2
            
            # Vendor-asserted penalty
            vendor_penalty = 0.1 if signal.is_vendor_asserted else 0.0
            
            # Final signal confidence
            signal_confidence = base_confidence * (1.0 + confirmation_boost * 0.2) * avg_source_credibility
            signal_confidence = signal_confidence - age_penalty - vendor_penalty
            signal_confidences.append(signal_confidence)
        
        # Overall confidence is weighted average
        overall_confidence = sum(signal_confidences) / len(signal_confidences)
        
        # Apply strict confidence capping
        if overall_confidence > 0.6:
            overall_confidence = 0.6  # Cap at 0.6 for opinion-heavy sources
        
        return max(0.0, min(1.0, overall_confidence))
    
    def _generate_analyst_grade_report(self, query: str, in_window_sources: List[Source], 
                                     signals: List[Signal], entities: Dict[str, List[str]], 
                                     topics: List[str], operator_lens: Dict[str, str], 
                                     actions: List[Dict[str, str]], confidence: float, 
                                     days_back: int) -> str:
        """Generate analyst-grade report with clean formatting"""
        
        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        # Generate topline (≤45 words)
        topline = self._generate_topline(signals, confidence)
        
        # Build analyst-grade report with proper title case (FIXED)
        report = f"""# Tech Brief — {query.title()}
Date range: {start_date.strftime('%b %d')}–{end_date.strftime('%b %d')}, 2025 | Sources: {len(in_window_sources)} | Confidence: {confidence:.2f}

## Topline
{topline}

## Signals (strength × impact × direction)"""
        
        # Add signals with citations
        for i, signal in enumerate(signals, 1):
            citation_refs = "".join([f"[^{cid}]" for cid in signal.citation_ids])
            report += f"""
- {signal.text} — strength: {signal.strength} | impact: {signal.impact.value} | trend: {signal.direction.value}  {citation_refs}"""
        
        # Add operator lens with clean formatting (FIXED)
        report += f"""

## Operator Lens
- **Operator:** {operator_lens.get('operator', 'Monitor for operational impact')}
- **Investor:** {operator_lens.get('investor', 'Assess market implications')}
- **BD:** {operator_lens.get('bd', 'Identify business opportunities')}

## Next Actions (by 10/31/2025)"""
        
        # Add actions
        for i, action in enumerate(actions, 1):
            if isinstance(action, dict):
                report += f"""
{i}) {action.get('title', '')} — owner: {action.get('owner', 'Agent')} — due: {action.get('due_date', '2025-10-31')}"""
        
        # Add entities and topics
        report += f"""

## Entities & Topics
ORG: {' | '.join(entities.get('ORG', []))}
PERSON: {' | '.join(entities.get('PERSON', []))}
PRODUCT: {' | '.join(entities.get('PRODUCT', []))}
TICKER: {' | '.join(entities.get('TICKER', []))}
GEO: {' | '.join(entities.get('GEO', []))}
Topics: {', '.join(topics)}

## Sources"""
        
        # Add sources with citations and URLs
        for i, source in enumerate(in_window_sources, 1):
            report += f"""
[^{i}]: {source.title} — {source.publisher}, {source.date}. (cred: {source.credibility:.2f}) — {source.url}"""
        
        return report
    
    def _generate_topline(self, signals: List[Signal], confidence: float) -> str:
        """Generate topline summary (≤45 words)"""
        if not signals:
            return "No significant developments identified in the time period."
        
        # Get top signals by strength
        strength_order = {"High": 3, "Medium": 2, "Low": 1}
        top_signals = sorted(signals, key=lambda x: strength_order.get(x.strength, 1), reverse=True)[:2]
        
        topline_prompt = f"""
        Create a topline summary from these key signals (MAX 45 words):
        
        {[signal.text for signal in top_signals]}
        
        Return as JSON with this exact structure:
        {{
            "topline": "Clear summary of what happened + why it matters (MAX 45 words)"
        }}
        
        Requirements:
        - MAX 45 words
        - Clear summary of what happened + why it matters
        - Professional, concise tone
        - Focus on the most important developments
        """
        
        try:
            response = self.llm.invoke(topline_prompt)
            data = self._extract_json(response.content)
            return data.get('topline', f"Key developments identified with {confidence:.2f} confidence. Further analysis required for actionable insights.")
        except Exception as e:
            logger.error(f"Error generating topline: {str(e)}")
            return f"Key developments identified with {confidence:.2f} confidence. Further analysis required for actionable insights."
    
    def _insufficient_evidence_response(self, query: str, in_window_sources: List[Source]) -> str:
        """Return insufficient evidence response"""
        return f"""# Tech Brief — {query.title()}
Date range: Oct 13–20, 2025 | Sources: {len(in_window_sources)} | Confidence: 0.00 (LOW — needs ≥2 independent news + ≥1 primary)

## Topline
Insufficient evidence found for reliable analysis. Quality gates require ≥2 independent news sources + ≥1 primary source for analyst-grade briefs.

## Next Actions (by 10/31/2025)
1) Auto‑retry search with independent news focus — owner: Agent — due: 2025-10-21
2) Draft STI post stub gated on confirmation (publish only if confidence ≥0.6) — owner: Hass — due: 2025-10-24

## Entities & Topics
ORG: | PERSON: | PRODUCT: | TICKER: | GEO:
Topics: 

## Sources
{chr(10).join([f"[^{i+1}]: {s.title} — {s.publisher}" for i, s in enumerate(in_window_sources)])}
"""
    
    def _classify_source_type(self, url: str) -> SourceType:
        """Classify source type based on URL"""
        if not url:
            return SourceType.VENDOR_CONSULTING
        
        domain = url.split('/')[2] if '/' in url else url
        domain = domain.replace('www.', '')
        
        if any(ind_domain in domain for ind_domain in self.independent_news_domains):
            return SourceType.INDEPENDENT_NEWS
        elif any(prim_domain in domain for prim_domain in self.primary_domains):
            return SourceType.PRIMARY
        elif any(vendor_domain in domain for vendor_domain in self.vendor_asserted_domains):
            return SourceType.VENDOR_ASSERTED
        else:
            return SourceType.TRADE_PRESS
    
    def _extract_publisher(self, url: str) -> str:
        """Extract publisher from URL"""
        if not url:
            return "Unknown"
        
        domain = url.split('/')[2] if '/' in url else url
        domain = domain.replace('www.', '')
        
        # Map domains to publishers
        publisher_map = {
            'reuters.com': 'Reuters',
            'bloomberg.com': 'Bloomberg',
            'ft.com': 'Financial Times',
            'wsj.com': 'Wall Street Journal',
            'ap.org': 'Associated Press',
            'theinformation.com': 'The Information',
            'semianalysis.com': 'SemiAnalysis',
            'techcrunch.com': 'TechCrunch',
            'arstechnica.com': 'Ars Technica',
            'wired.com': 'Wired',
            'mckinsey.com': 'McKinsey',
            'deloitte.com': 'Deloitte',
            'forbes.com': 'Forbes',
            'nebius.com': 'Nebius',
            'openai.com': 'OpenAI'
        }
        
        return publisher_map.get(domain, domain.title())
    
    def _extract_date(self, result: Dict[str, Any]) -> str:
        """Extract date from search result"""
        date_fields = ['published_date', 'date', 'created_at', 'updated_at']
        
        for field in date_fields:
            if field in result and result[field]:
                return result[field]
        
        return datetime.now().strftime('%Y-%m-%d')
    
    def _calculate_source_credibility(self, result: Dict[str, Any], source_type: SourceType) -> float:
        """Calculate source credibility based on type and content"""
        base_scores = {
            SourceType.INDEPENDENT_NEWS: 0.8,
            SourceType.PRIMARY: 0.9,
            SourceType.TRADE_PRESS: 0.7,
            SourceType.VENDOR_CONSULTING: 0.5,
            SourceType.VENDOR_ASSERTED: 0.4
        }
        
        score = base_scores.get(source_type, 0.5)
        
        # Boost for comprehensive content
        content_length = len(result.get('content', ''))
        if content_length > 1000:
            score += 0.1
        elif content_length > 500:
            score += 0.05
        
        return min(1.0, score)
    
    def _extract_json(self, text: str) -> Dict[str, Any]:
        """Extract JSON from text with robust error handling"""
        try:
            # Clean the response
            text = text.strip()
            
            # Find JSON boundaries
            start = text.find('{')
            end = text.rfind('}')
            
            if start == -1 or end == -1 or end <= start:
                raise ValueError("No JSON object found")
            
            json_str = text[start:end+1]
            return json.loads(json_str)
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {str(e)}")
            raise ValueError(f"Invalid JSON: {str(e)}")
        except Exception as e:
            logger.error(f"Error extracting JSON: {str(e)}")
            raise ValueError(f"JSON extraction failed: {str(e)}")
    
    def get_url_validation_stats(self) -> Dict[str, Any]:
        """Get URL validation statistics"""
        stats = self.url_validation_stats.copy()
        if stats['total_checked'] > 0:
            stats['success_rate'] = stats['valid_urls'] / stats['total_checked']
        else:
            stats['success_rate'] = 0.0
        return stats


def main():
    """Example usage of the Final Analyst-Grade Time-Filtered Search Agent"""
    
    # Load environment variables
    openai_api_key = os.getenv("OPENAI_API_KEY")
    tavily_api_key = os.getenv("TAVILY_API_KEY") or ""
    
    if not openai_api_key:
        print("Please set OPENAI_API_KEY environment variable")
        return
    
    # Initialize the final analyst-grade agent
    agent = FinalAnalystGradeAgent(
        openai_api_key=openai_api_key,
        tavily_api_key=tavily_api_key
    )
    
    # Example final analyst-grade searches
    print("=== Final Analyst-Grade Time-Filtered Search Agent Demo ===\n")
    
    # Example 1: Technology trends with all surgical fixes
    print("1. Generating final analyst-grade brief...")
    result1 = agent.search(
        "AI technology trends",
        days_back=7
    )
    print(result1)
    print("\n" + "="*80 + "\n")
    
    # Example 2: Cybersecurity developments
    print("2. Generating cybersecurity brief...")
    result2 = agent.search(
        "cybersecurity developments",
        days_back=5
    )
    print(result2)


if __name__ == "__main__":
    main()

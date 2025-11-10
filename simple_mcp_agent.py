"""
Simple MCP Time-Filtered Search Agent

A simplified implementation using MCP framework for time-filtered search with:
- MCP server for search functionality
- Time window enforcement
- Source hygiene and quality gates
- Structured output with confidence scoring
"""

import os
import logging
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum

from langchain_openai import ChatOpenAI
from tavily import TavilyClient
from file_utils import save_simple_report_auto
from config import STIConfig

# Configure logging - only if root logger has no handlers (avoid conflicts)
if not logging.getLogger().handlers:
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
    ACADEMIC = "academic"


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
    is_background: bool = False


class SimpleMCPTimeFilteredAgent:
    """
    Simple MCP Time-Filtered Search Agent
    """
    
    def __init__(self, openai_api_key: str, tavily_api_key: str = "",
                 model_name: str = "gpt-5-mini-2025-08-07"):
        self.openai_api_key = openai_api_key
        self.tavily_api_key = tavily_api_key
        self.model_name = model_name

        # Initialize LLM
        # Get organization ID from environment for verified org
        organization = os.getenv("OPENAI_ORGANIZATION") or getattr(STIConfig, 'OPENAI_ORGANIZATION', None)
        llm_params = {
            "api_key": openai_api_key,
            "model": model_name,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "timeout": 120.0  # 120 second timeout to prevent hanging
        }
        if organization:
            llm_params["openai_organization"] = organization
        self.llm = ChatOpenAI(**llm_params)

        # Only initialize Tavily if provider is Tavily
        search_provider = getattr(STIConfig, 'SEARCH_PROVIDER', 'searxng')
        if search_provider == 'tavily':
            from tavily import TavilyClient
            self.tavily_client = TavilyClient(api_key=tavily_api_key)
        else:
            self.tavily_client = None
        
        # Date filtering statistics
        self.date_filter_stats = {
            'total_processed': 0,
            'within_window': 0,
            'outside_window': 0,
            'parse_failed': 0
        }
        
        # URL validation statistics
        self.url_validation_stats = {
            'total_checked': 0,
            'valid_urls': 0,
            'missing_urls': 0,
            'invalid_format': 0,
            'failed_cleaning': 0
        }
        
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
    
    def search(self, query: str, days_back: int = 7) -> str:
        """
        Perform time-filtered search with strict enforcement
        
        Args:
            query: The search query
            days_back: Number of days to look back (default: 7)
            
        Returns:
            Markdown report
        """
        try:
            # Step 1: Search with time filtering
            sources = self._search_with_time_filtering(query, days_back)
            
            # Step 2: Apply quality gates
            if not self._check_quality_gates(sources):
                return self._insufficient_evidence_response(query, sources)
            
            # Step 3: Extract signals
            signals = self._extract_signals(sources)
            
            # Step 4: Generate report
            report = self._generate_report(query, sources, signals, days_back)
            
            # Automatically save the report with nested file structure
            agent_stats = {
                'date_filter_stats': self.get_date_filter_stats()
            }
            
            report_dir = save_simple_report_auto(
                query, report, days_back, agent_stats
            )
            
            return report
            
        except Exception as e:
            logger.error(f"Error in search: {str(e)}")
            return f"Error performing search: {str(e)}"
    
    def _search_with_time_filtering(self, query: str, days_back: int) -> List[Source]:
        """Search with adaptive retry loop for independent news sources"""
        sources = []
        source_id = 1
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        logger.info(f"Searching for sources within {days_back}-day window: "
                   f"{start_date.date()} to {end_date.date()}")
        
        # ADAPTIVE RETRY: Search for independent news sources
        max_retries = 3
        independent_sources = []
        for attempt in range(1, max_retries + 1):
            batch_size = 6 * attempt  # Increase batch size each retry (6, 12, 18)
            logger.info(f"Independent news search attempt {attempt}/{max_retries} "
                       f"(requesting {batch_size} results)")
            
            batch = self._search_by_domain_type(
                query, self.independent_news_domains, SourceType.INDEPENDENT_NEWS,
                max_results=batch_size, days_back=days_back
            )
            
            # Validate and collect
            for source in batch:
                if self._is_within_time_window(source, start_date, end_date):
                    source.id = source_id
                    source.is_in_window = True
                    independent_sources.append(source)
                    source_id += 1
            
            # Stop if we have enough (≥3 independent required)
            if len(independent_sources) >= 3:
                logger.info(f"✓ Found {len(independent_sources)} independent news sources")
                break
        
        sources.extend(independent_sources)
        
        # Continue with primary and vendor sources (no retry needed)
        # Search for primary sources with Tavily date filtering
        primary_sources = self._search_by_domain_type(
            query, self.primary_domains, SourceType.PRIMARY,
            max_results=4, days_back=days_back
        )
        
        for source in primary_sources:
            source.id = source_id
            # Apply time window filter
            if self._is_within_time_window(source, start_date, end_date):
                source.is_in_window = True
                sources.append(source)
                source_id += 1
        
        logger.info(f"After time window validation: {len(sources)} total sources "
                   f"(including primary)")
        
        # Search for vendor-asserted sources with Tavily date filtering
        vendor_sources = self._search_by_domain_type(
            query, self.vendor_asserted_domains, SourceType.VENDOR_ASSERTED,
            max_results=2, days_back=days_back
        )
        
        for source in vendor_sources:
            source.id = source_id
            # Apply time window filter
            if self._is_within_time_window(source, start_date, end_date):
                source.is_in_window = True
                sources.append(source)
                source_id += 1
        
        logger.info(f"Final source count: {len(sources)} sources within "
                   f"{days_back}-day window")
        
        # Diversity fallback: if publishers are not diverse enough, try targeted extra fetches
        try:
            from collections import Counter
            publishers = [s.publisher for s in sources if s.publisher]
            distinct_publishers = set(publishers)
            min_distinct = getattr(STIConfig, 'MIN_DISTINCT_PUBLISHERS_MARKET', 3)
            single_domain_cap = getattr(STIConfig, 'SINGLE_DOMAIN_MAX_FRACTION', 0.6)
            domain_counts = Counter(publishers)
            top_count = max(domain_counts.values()) if domain_counts else 0
            needs_diversity = (len(domain_counts) < min_distinct) or (top_count / max(1, len(sources)) > single_domain_cap)
            
            if needs_diversity:
                # Select underrepresented independent domains and fetch a small batch
                under_domains = [d for d in self.independent_news_domains if d not in distinct_publishers]
                extra = self._searxng_search(query, under_domains[:4], SourceType.INDEPENDENT_NEWS, max_results=6, days_back=days_back)
                for source in extra:
                    if self._is_within_time_window(source, start_date, end_date):
                        source.id = source_id
                        source.is_in_window = True
                        sources.append(source)
                        source_id += 1
                logger.info(f"Diversity fallback fetched {len(extra)} additional sources; new total: {len(sources)}")
        except Exception as e:
            logger.warning(f"Diversity fallback skipped due to error: {str(e)}")
        
        return sources
    
    def _search_by_domain_type(self, query: str, domains: List[str],
                               source_type: SourceType, max_results: int,
                               days_back: int = 7) -> List[Source]:
        """Search by domain type with provider switch (Tavily or SearXNG)"""
        search_provider = getattr(STIConfig, 'SEARCH_PROVIDER', 'searxng')
        if search_provider == 'searxng':
            return self._searxng_search(query, domains, source_type, max_results, days_back)
        
        # If provider is tavily but client not initialized, fallback to SearXNG
        if self.tavily_client is None:
            logger.warning("Tavily provider selected but client not initialized, falling back to SearXNG")
            return self._searxng_search(query, domains, source_type, max_results, days_back)
        
        sources = []
        
        # Calculate exact date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        try:
            logger.info(f"Searching {source_type.value}: requesting "
                       f"{max_results} results within {days_back}-day window")
            
            response = self.tavily_client.search(
                query=query,
                search_depth="advanced",
                max_results=max_results,
                include_domains=domains,
                include_answer=False,
                include_raw_content=True,
                time_range="week",      # Tavily built-in 7-day filter
                topic="news"            # NEW: Ensures published_date metadata
            )
            
            if 'results' in response:
                results_with_dates = 0
                for result in response['results']:
                    if self._passes_hygiene_filters(result):
                        date = self._extract_date(result)
                        
                        # STRICT MODE: Skip sources without valid dates
                        if date is None:
                            logger.warning(f"Rejecting source '{result.get('title', 'Unknown')}' - no date field from Tavily API")
                            continue
                        
                        results_with_dates += 1
                        
                        # STRICT URL VALIDATION - Reject if no valid URL
                        validated_url = self._validate_url(result.get('url', ''), result.get('title', 'Unknown'))
                        if not validated_url:
                            continue  # Skip this source
                        
                        source = Source(
                            id=0,  # Will be set later
                            title=result.get('title', 'No title'),
                            url=validated_url,  # ← GUARANTEED VALID
                            publisher=self._extract_publisher(validated_url),
                            date=date,
                            credibility=self._calculate_credibility(result, source_type),
                            content=result.get('content', ''),
                            source_type=source_type,
                            is_in_window=False  # Will be validated later
                        )
                        sources.append(source)
                        logger.info(f"✓ Accepted source '{source.title}' with valid URL: {validated_url}")
                
                logger.info(f"  Received {len(response.get('results', []))} results, "
                           f"{results_with_dates} with valid dates")
                    
        except Exception as e:
            logger.error(f"Error searching {source_type}: {str(e)}")
        
        return sources
    
    def _searxng_search(self, query: str, domains: List[str], source_type: SourceType, max_results: int, days_back: int) -> List[Source]:
        """Search SearXNG JSON API with short, per-site queries and map results to Source objects."""
        import requests
        sources: List[Source] = []
        base = getattr(STIConfig, 'SEARXNG_BASE_URL', 'http://localhost:8080').rstrip('/')
        category = 'science' if source_type == SourceType.ACADEMIC else ('news' if source_type == SourceType.INDEPENDENT_NEWS else 'general')
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
        url = f"{base}/search"

        def _normalize(text: str) -> str:
            try:
                # Replace typographic dashes/quotes with ASCII, drop non-ASCII
                replacements = {
                    '\u2013': '-', '\u2014': '-', '\u2015': '-',
                    '\u2018': '\'', '\u2019': '\'', '\u201C': '"', '\u201D': '"'
                }
                for k, v in replacements.items():
                    text = text.replace(k, v)
                text = text.encode('ascii', 'ignore').decode('ascii')
                # Reduce excessive quoting; keep phrases short
                text = text.replace('""', '"')
                return text
            except Exception:
                return text

        def run(q: str, use_time: bool = True, method: str = 'GET'):
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
                resp = requests.get(url, params=params, headers=headers, timeout=timeout)
            else:
                resp = requests.post(url, data=params, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return resp.json().get('results', [])

        # Health check: trivial query to detect JSON availability/param sensitivity
        try:
            _ = run('test', use_time=False, method='GET')
        except Exception:
            # try POST w/o time_range
            try:
                _ = run('test', use_time=False, method='POST')
            except Exception:
                logger.error("SearXNG health check failed for both GET and POST")
                return []

        # Build short queries and iterate domains to avoid long OR chains
        queries: List[str] = []
        if domains:
            # Round-robin across more domains for diversity
            max_domains = min(8, len(domains))
            for d in domains[:max_domains]:
                queries.append(f'{_normalize(query)} site:{d}')
        else:
            queries.append(_normalize(query))

        count = 0
        from collections import defaultdict
        per_domain_counts = defaultdict(int)
        per_domain_cap = max(1, max_results // 2)  # avoid domination by single domain
        for q in queries:
            if count >= max_results:
                break
            try:
                # Attempt GET with time_range; on 400 fallback strategies
                attempts = [
                    ('GET', True),
                    ('GET', False),
                    ('POST', False)
                ]
                results = []
                for method, use_time in attempts:
                    try:
                        results = run(q, use_time=use_time, method=method)
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
                    validated_url = self._validate_url(u, t)
                    if not validated_url:
                        continue
                    publisher = self._extract_publisher(validated_url)
                    # Enforce per-domain cap
                    try:
                        from urllib.parse import urlparse
                        host = urlparse(validated_url).netloc.replace('www.', '')
                        if per_domain_counts[host] >= per_domain_cap:
                            continue
                    except Exception:
                        pass
                    # STRICT: Extract and validate date - reject if missing
                    date = r.get('pubdate') or r.get('published') or r.get('date')
                    if not date:
                        # STRICT: Reject source if no date found (don't default to now())
                        logger.warning(f"✗ Rejecting source '{t}' - no publication date found")
                        continue
                    # Normalize date format
                    try:
                        # Try parsing common formats
                        for fmt in ['%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%SZ', '%m/%d/%Y', '%d/%m/%Y']:
                            try:
                                parsed_date = datetime.strptime(str(date)[:10], fmt)
                                date = parsed_date.strftime('%Y-%m-%d')
                                break
                            except ValueError:
                                continue
                        else:
                            # If no format matches, reject
                            logger.warning(f"✗ Rejecting source '{t}' - unparseable date: {date}")
                            continue
                    except Exception as e:
                        logger.warning(f"✗ Rejecting source '{t}' - date parsing error: {e}")
                        continue
                    source = Source(
                        id=0,
                        title=t,
                        url=validated_url,
                        publisher=publisher,
                        date=str(date)[:10],
                        credibility=self._calculate_credibility({'url': validated_url, 'title': t}, source_type),
                        content=r.get('content') or r.get('snippet') or '',
                        source_type=source_type,
                        is_in_window=False
                    )
                    sources.append(source)
                    try:
                        per_domain_counts[host] += 1
                    except Exception:
                        pass
                    count += 1
                if count >= max_results:
                    break
            except Exception as e:
                logger.error(f"SearXNG search error: {str(e)}")
                continue

        logger.info(f"SearXNG returned {len(sources)} results after filtering for {source_type.value}")
        return sources
    
    def _is_within_time_window(self, source: Source, start_date: datetime, end_date: datetime) -> bool:
        """Check if source is within time window - STRICT MODE: reject if date cannot be parsed"""
        self.date_filter_stats['total_processed'] += 1
        
        try:
            source_date = datetime.strptime(source.date, '%Y-%m-%d')
            is_within = start_date <= source_date <= end_date
            
            if is_within:
                self.date_filter_stats['within_window'] += 1
                logger.info(f"✓ Source '{source.title}' date {source.date} is within 7-day window")
            else:
                self.date_filter_stats['outside_window'] += 1
                days_diff = (datetime.now() - source_date).days
                logger.warning(f"✗ Source '{source.title}' date {source.date} is outside 7-day window (published {days_diff} days ago)")
            
            return is_within
        except Exception as e:
            # STRICT MODE: If date parsing fails, reject the source
            self.date_filter_stats['parse_failed'] += 1
            logger.warning(f"✗ Rejecting source '{source.title}' due to unparseable date '{source.date}': {str(e)}")
            return False
    
    def _check_quality_gates(self, sources: List[Source]) -> bool:
        """Check if sources meet quality gates with market-path diversity controls"""
        if len(sources) < 3:
            return False
        
        # Count source types
        source_types = [s.source_type for s in sources]
        independent_count = source_types.count(SourceType.INDEPENDENT_NEWS)
        
        # Primary requirement: ≥3 independent news sources
        if independent_count < 3:
            return False
        
        # Diversity: distinct publishers and single-domain cap (market-path)
        try:
            from collections import Counter
            min_distinct = getattr(STIConfig, 'MIN_DISTINCT_PUBLISHERS_MARKET', 3)
            single_domain_cap = getattr(STIConfig, 'SINGLE_DOMAIN_MAX_FRACTION', 0.6)
            publishers = [s.publisher for s in sources if s.publisher]
            domain_counts = Counter(publishers)
            if len(domain_counts) < min_distinct:
                return False
            top_count = max(domain_counts.values()) if domain_counts else 0
            if top_count / max(1, len(sources)) > single_domain_cap:
                return False
        except Exception:
            # If any issue computing diversity, don't pass silently; enforce baseline gates only
            return False
        
        return True
    
    def _extract_signals(self, sources: List[Source]) -> List[Dict[str, Any]]:
        """Extract signals from sources (backward compatible)"""
        return self._extract_signals_enhanced(sources, count=4)
    
    def _validate_source_coverage(self, signals: List[Dict], sources: List[Source]) -> bool:
        """Ensure all sources are cited at least once"""
        cited_sources = set()
        for signal in signals:
            cited_sources.update(signal.get('citation_ids', []))
        
        uncited = [s.id for s in sources if s.id not in cited_sources]
        if uncited:
            logger.warning(f"Uncited sources: {uncited}. Regenerating signals...")
            return False
        return True
    
    def _extract_signals_enhanced(self, sources: List[Source], count: int = 4) -> List[Dict[str, Any]]:
        """Extract signals from sources with configurable count and source diversity enforcement"""
        if not sources:
            return []
        
        # Combine content from sources
        combined_content = "\n\n".join([f"Source {s.id}: {s.content}" for s in sources])
        
        # Use LLM to extract signals with source diversity requirement
        signal_prompt = f"""
        Extract {count} event-anchored signals from this content. Each signal must have:
        1. A specific date (this week)
        2. A clear actor (company, person, organization)
        3. A measurable action with SPECIFIC UNITS
        4. Evidence from the content
        5. **CITE MULTIPLE SOURCES**: Ensure signals reference different sources
        
        CRITICAL: You have {len(sources)} sources available. Distribute citations across ALL sources.
        Aim for: Each source should be cited at least once.
        
        Sources available: {', '.join([f'Source {s.id}: {s.publisher}' for s in sources])}
        
        EXACT UNIT NORMALIZER: 
        - If you see "users" without units, use specific units: DAU, WAU, MAU
        - Example: "800M users" → "800M WAU" or "800M weekly active users"
        
        Content: {combined_content[:3000]}
        
        Return as JSON with this exact structure:
        {{
            "signals": [
                {{
                    "text": "Specific claim with date, actor, and measurable WITH SPECIFIC UNITS",
                    "strength": "High/Medium/Low",
                    "impact": "High/Medium/Low",
                    "direction": "↗︎/↘︎/→/?",
                    "citation_ids": [1, 2],
                    "date": "2025-10-20",
                    "actor": "Company X",
                    "measurable": "launched product Y with specific metrics and units",
                    "confidence": 0.8
                }}
            ]
        }}
        """
        
        # Retry signal extraction if coverage is poor
        max_attempts = 2
        for attempt in range(max_attempts):
            try:
                response = self.llm.invoke(signal_prompt)
                signals_data = json.loads(response.content)
                signals = signals_data.get('signals', [])
                
                # Validate source coverage
                if self._validate_source_coverage(signals, sources):
                    # Add date validation to reject future-dated signals
                    valid_signals = self._validate_signal_dates(signals)
                    
                    # Warn if we got significantly fewer signals than requested or sources available
                    # This helps catch cases where date validation filtered too many
                    min_expected = min(len(sources), count)  # Don't exceed requested count
                    if len(valid_signals) < min_expected:
                        logger.warning(
                            f"⚠️  Signal extraction: {len(valid_signals)} signals after validation "
                            f"(requested {count}, sources: {len(sources)}). "
                            f"Some signals may have been filtered by date validation."
                        )
                    
                    logger.info(f"✓ Signal extraction successful: {len(valid_signals)} signals with good source coverage")
                    return valid_signals
                else:
                    logger.info(f"Attempt {attempt + 1}: Regenerating signals for better source coverage")
                    if attempt < max_attempts - 1:
                        # Add more emphasis to source diversity in retry
                        signal_prompt += "\n\nIMPORTANT: Previous attempt had uncited sources. Ensure ALL sources are cited at least once."
                    
            except Exception as e:
                logger.error(f"Error extracting signals (attempt {attempt + 1}): {str(e)}")
                if attempt == max_attempts - 1:
                    return []
        
        return []
    
    def _validate_signal_dates(self, signals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Validate signal dates and reject future-dated signals"""
        today = datetime.now().date()
        valid_signals = []
        
        for signal in signals:
            try:
                signal_date_str = signal.get('date', '')
                if signal_date_str:
                    signal_date = datetime.strptime(signal_date_str, '%Y-%m-%d').date()
                    if signal_date <= today:
                        valid_signals.append(signal)
                    else:
                        logger.warning(f"✗ Rejected future-dated signal: '{signal.get('text', '')[:50]}...' (date: {signal_date_str})")
                else:
                    # If no date, keep the signal but log warning
                    logger.warning(f"⚠ Signal without date: '{signal.get('text', '')[:50]}...'")
                    valid_signals.append(signal)
            except ValueError as e:
                logger.warning(f"✗ Rejected signal with invalid date format: '{signal.get('text', '')[:50]}...' (date: {signal.get('date', '')}) - {str(e)}")
        
        logger.info(f"Date validation: {len(signals)} → {len(valid_signals)} signals")
        return valid_signals
    
    def _generate_report(self, query: str, sources: List[Source], signals: List[Dict[str, Any]], days_back: int) -> str:
        """Generate markdown report"""
        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        # Calculate confidence
        confidence = self._calculate_confidence(signals, sources)
        
        # Generate topline
        topline = self._generate_topline(signals, confidence)
        
        # Get date filtering statistics
        filter_stats = self.get_date_filter_stats()
        
        # Build report
        report = f"""# Tech Brief — {query.title()}
Date range: {start_date.strftime('%b %d')}–{end_date.strftime('%b %d')}, 2025 | Sources: {len(sources)} | Confidence: {confidence:.2f}
**Date Filtering:** Strict 7-day window enforced | Filter Success Rate: {filter_stats['success_rate']:.1%}

## Topline
{topline}

## Signals (strength × impact × direction)"""
        
        # Add signals
        for i, signal in enumerate(signals, 1):
            citation_refs = "".join([f"[^{cid}]" for cid in signal.get('citation_ids', [])])
            report += f"""
- {signal.get('text', '')} — strength: {signal.get('strength', 'Medium')} | impact: {signal.get('impact', 'Medium')} | trend: {signal.get('direction', '?')}  {citation_refs}"""
        
        # Add sources
        report += f"""

## Date Filtering Summary
- **Time Window:** {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}
- **Sources Processed:** {filter_stats['total_processed']}
- **Within Window:** {filter_stats['within_window']}
- **Outside Window:** {filter_stats['outside_window']}
- **Parse Failures:** {filter_stats['parse_failed']}
- **Success Rate:** {filter_stats['success_rate']:.1%}

## Sources"""
        
        for i, source in enumerate(sources, 1):
            report += f"""
[^{i}]: {source.title} — {source.publisher}, {source.date}. (cred: {source.credibility:.2f}) — {source.url}"""
        
        return report
    
    def _calculate_confidence(self, signals: List[Dict[str, Any]], sources: List[Source]) -> float:
        """Calculate confidence score with cap [0.30, 0.85]"""
        if not signals:
            return 0.30
        
        # Simple confidence calculation
        base_confidence = 0.5
        
        # Boost for multiple sources
        if len(sources) >= 3:
            base_confidence += 0.2
        
        # Boost for signal quality
        high_strength_signals = sum(1 for s in signals if s.get('strength') == 'High')
        if high_strength_signals > 0:
            base_confidence += 0.1
        
        # Apply bounds [0.30, 0.85]
        return max(0.30, min(0.85, base_confidence))
    
    def _generate_topline(self, signals: List[Dict[str, Any]], confidence: float) -> str:
        """Generate topline summary (≤45 words)"""
        if not signals:
            return "No significant developments identified in the time period."
        
        # Get top signals
        top_signals = signals[:2]
        
        topline_prompt = f"""
        Create a topline summary from these key signals (MAX 45 words):
        
        {[signal.get('text', '') for signal in top_signals]}
        
        Return as JSON with this exact structure:
        {{
            "topline": "Clear summary of what happened + why it matters (MAX 45 words)"
        }}
        """
        
        try:
            response = self.llm.invoke(topline_prompt)
            data = json.loads(response.content)
            return data.get('topline', f"Key developments identified with {confidence:.2f} confidence.")
        except Exception as e:
            logger.error(f"Error generating topline: {str(e)}")
            return f"Key developments identified with {confidence:.2f} confidence."
    
    def _insufficient_evidence_response(self, query: str, sources: List[Source]) -> str:
        """Return insufficient evidence response"""
        return f"""# Tech Brief — {query.title()}
Date range: Oct 13–20, 2025 | Sources: {len(sources)} | Confidence: 0.00 (LOW — needs ≥2 independent news + ≥1 primary)

## Topline
Insufficient evidence found for reliable analysis. Quality gates require ≥2 independent news sources + ≥1 primary source for client-ready briefs.

## Next Actions (by 10/31/2025)
1) Auto‑retry search with independent news focus — owner: Agent — due: 2025-10-21
2) Draft STI post stub gated on confirmation (publish only if confidence ≥0.6) — owner: Hass — due: 2025-10-24

## Sources
{chr(10).join([f"[^{i+1}]: {s.title} — {s.publisher}" for i, s in enumerate(sources)])}
"""
    
    def _passes_hygiene_filters(self, result: Dict[str, Any]) -> bool:
        """Check if result passes hygiene filters INCLUDING URL validation"""
        url = result.get('url', '')
        title = result.get('title', '')
        
        # NEW: Reject if no URL
        if not url or len(url) < 10:
            logger.debug(f"Rejecting '{title}' - no URL")
            return False
        
        # NEW: Reject if URL is clearly invalid
        if not (url.startswith('http://') or url.startswith('https://')):
            logger.debug(f"Rejecting '{title}' - invalid URL protocol: {url}")
            return False
        
        # Block sponsored/partner content
        for pattern in self.blocklist_patterns:
            if pattern in url.lower() or pattern in title.lower():
                return False
        
        # Block tracking URLs
        if 'links.message.bloomberg.com' in url:
            return False
        
        return True
    
    def _clean_url(self, url: str) -> str:
        """Clean URL to canonical form"""
        if not url:
            return ""
        if '?' in url:
            url = url.split('?')[0]
        return url
    
    def _is_article_url(self, url: str) -> bool:
        """
        Check if URL is a specific article (not an index/category page).
        Publisher-specific rules to reject generic paths.
        """
        import re
        from urllib.parse import urlparse
        
        url_lower = url.lower()
        
        # Publisher-specific article path patterns
        article_patterns = {
            'reuters.com': [
                r'/technology/\d{4}/\d{2}/\d{2}/',  # /technology/2025/10/13/...
                r'/article/',  # /article/...
                r'/world/',  # /world/...
                r'/business/',  # /business/...
            ],
            'bloomberg.com': [
                r'/news/articles/',  # /news/articles/...
                r'/news/features/',  # /news/features/...
            ],
            'ft.com': [
                r'/content/',  # /content/...
            ],
            'wsj.com': [
                r'/articles/',  # /articles/...
            ],
            'sec.gov': [
                r'/Archives/edgar/data/',  # SEC filings
            ],
        }
        
        # Check if URL matches any article pattern for its domain
        for domain, patterns in article_patterns.items():
            if domain in url_lower:
                return any(re.search(pattern, url_lower) for pattern in patterns)
        
        # For other domains, require path depth > 1 (reject root/index pages)
        parsed = urlparse(url)
        path_parts = [p for p in parsed.path.split('/') if p]
        return len(path_parts) > 1
    
    def _validate_url(self, raw_url: str, title: str) -> Optional[str]:
        """
        Validate and clean URL. Returns cleaned URL if valid, None if invalid.
        Rejects index pages and generic category pages.
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
        
        # NEW: Reject index/category pages (not specific articles)
        if not self._is_article_url(cleaned_url):
            self.url_validation_stats['invalid_format'] += 1
            logger.warning(f"✗ Rejecting source '{title}' - index/category page (not article): {cleaned_url}")
            return None
        
        self.url_validation_stats['valid_urls'] += 1
        logger.debug(f"✓ Valid URL for '{title}': {cleaned_url}")
        return cleaned_url
    
    def _extract_publisher(self, url: str) -> str:
        """Extract publisher from URL"""
        if not url:
            return "Unknown"
        
        domain = url.split('/')[2] if '/' in url else url
        domain = domain.replace('www.', '')
        
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
        """Extract date from search result with enhanced parsing - STRICT MODE"""
        import re
        
        # First, try explicit date fields
        date_fields = ['published_date', 'date', 'created_at', 'updated_at']
        
        for field in date_fields:
            if field in result and result[field]:
                date_str = result[field]
                # Try to parse and normalize the date
                try:
                    # Handle various date formats including RFC 2822
                    for fmt in ['%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%SZ', '%m/%d/%Y', '%d/%m/%Y', '%a, %d %b %Y %H:%M:%S %Z']:
                        try:
                            parsed_date = datetime.strptime(date_str, fmt)
                            return parsed_date.strftime('%Y-%m-%d')
                        except ValueError:
                            continue
                    # If no format matches, return as-is (will be rejected by strict filtering)
                    return date_str
                except:
                    return date_str
        
        # If no explicit date fields, try to extract from raw_content
        raw_content = result.get('raw_content', '')
        if raw_content:
            # Look for date patterns in raw_content
            date_patterns = [
                (r'(\d{1,2} \w+ \d{4})', '%d %B %Y'),  # "16 October 2025"
                (r'(\w+ \d{1,2}, \d{4})', '%B %d, %Y'),  # "October 13, 2025"
                (r'(\d{4}-\d{2}-\d{2})', '%Y-%m-%d'),  # "2025-10-13"
                (r'(\d{1,2}/\d{1,2}/\d{4})', '%m/%d/%Y'),  # "10/13/2025"
            ]
            
            for pattern, fmt in date_patterns:
                matches = re.findall(pattern, raw_content)
                if matches:
                    # Take the first match and try to parse it
                    try:
                        parsed_date = datetime.strptime(matches[0], fmt)
                        return parsed_date.strftime('%Y-%m-%d')
                    except ValueError:
                        continue
        
        # STRICT MODE: If no date found, return None to signal rejection
        return None
    
    def _calculate_credibility(self, result: Dict[str, Any], source_type: SourceType) -> float:
        """Calculate source credibility"""
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
    
    def get_date_filter_stats(self) -> Dict[str, Any]:
        """Get date filtering statistics"""
        stats = self.date_filter_stats.copy()
        if stats['total_processed'] > 0:
            stats['success_rate'] = stats['within_window'] / stats['total_processed']
            stats['parse_success_rate'] = (stats['total_processed'] - stats['parse_failed']) / stats['total_processed']
        else:
            stats['success_rate'] = 0.0
            stats['parse_success_rate'] = 0.0
        return stats
    
    def get_url_validation_stats(self) -> Dict[str, Any]:
        """Get URL validation statistics"""
        stats = self.url_validation_stats.copy()
        if stats['total_checked'] > 0:
            stats['success_rate'] = stats['valid_urls'] / stats['total_checked']
        else:
            stats['success_rate'] = 0.0
        return stats
    
    def _serialize_sources_to_json(self, sources: List[Source]) -> str:
        """Serialize sources to JSON for MCP tool consumption"""
        sources_data = []
        for source in sources:
            sources_data.append({
                "id": source.id,
                "title": source.title,
                "url": source.url,
                "publisher": source.publisher,
                "date": source.date,
                "credibility": source.credibility,
                "content": source.content,
                "source_type": source.source_type.value,
                "is_in_window": source.is_in_window,
                "is_background": source.is_background
            })
        return json.dumps(sources_data)
    
    def _serialize_signals_to_json(self, signals: List[Dict[str, Any]]) -> str:
        """Serialize signals to JSON for MCP tool consumption"""
        return json.dumps(signals)


def main():
    """Example usage of the Simple MCP Time-Filtered Search Agent"""
    
    # Load environment variables
    openai_api_key = os.getenv("OPENAI_API_KEY")
    tavily_api_key = os.getenv("TAVILY_API_KEY") or ""
    
    if not openai_api_key:
        print("Please set OPENAI_API_KEY environment variable")
        return
    
    # Initialize the simple MCP agent
    agent = SimpleMCPTimeFilteredAgent(
        openai_api_key=openai_api_key,
        tavily_api_key=tavily_api_key
    )
    
    # Example searches
    print("=== Simple MCP Time-Filtered Search Agent Demo ===\n")
    
    # Example 1: Technology trends
    print("1. Generating simple MCP time-filtered brief...")
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

"""
STI Configuration

Configuration settings for the STI Analyst-Grade Intelligence System
including report targets, quality gates, and MCP server configurations.
"""

import os
from typing import Tuple

# Load environment variables from .env file if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # dotenv not installed, skip loading
    pass


class STIConfig:
    """Configuration class for STI Intelligence System"""
    
    # Report targets (enhanced)
    TARGET_WORD_COUNT = 3350
    SIGNALS_COUNT = 6  # Up from 4
    
    # Quality gates (updated)
    CONFIDENCE_BOUNDS: Tuple[float, float] = (0.30, 0.85)
    CONFIDENCE_MAX_VENDOR = 0.70
    REQUIRE_TIME_WINDOW_STRICT = True
    REQUIRE_UNIT_NORMALIZATION = True
    REQUIRE_ENTITY_ALIGNMENT = True
    MIN_INDEPENDENT_SOURCES = 2
    MIN_PRIMARY_SOURCES = 0      # Changed from 1 to 0
    MIN_TOTAL_SOURCES = 2        # Changed from 3 to 2
    ANCHOR_COVERAGE_MIN = 0.70
    VENDOR_CAP_PCT = 0.40
    REQUIRE_ANCHORS_FOR_ASSETS = True
    
    # New section requirements
    REQUIRE_MARKET_ANALYSIS = True
    REQUIRE_TECH_DEEPDIVE = True
    REQUIRE_COMPETITIVE_ANALYSIS = True
    REQUIRE_EXPANDED_LENSES = True
    REQUIRE_EXECUTIVE_SUMMARY = True
    
    # MCP server configs
    ANALYSIS_SERVER_PATH = "servers/analysis_server.py"
    
    # Source hygiene patterns
    BLOCKLIST_PATTERNS = [
        'partnercontent', 'sponsored', 'brandstudio', 'message.bloomberg.com',
        '/sponsored/', 'brand-content', 'advertorial', 'promoted'
    ]
    
    WHITELIST_PATTERNS = [
        'reuters.com', 'apnews.com', 'ft.com/content', 'bloomberg.com/news',
        'wsj.com/articles', 'theinformation.com', 'techcrunch.com',
        'arstechnica.com', 'wired.com', 'nature.com'
    ]
    
    INDEPENDENT_NEWS_DOMAINS = [
        'reuters.com', 'bloomberg.com', 'ft.com', 'wsj.com', 'ap.org',
        'theinformation.com', 'semianalysis.com', 'techcrunch.com'
    ]
    
    PRIMARY_DOMAINS = [
        'sec.gov', 'company blogs', 'press releases', 'product pages'
    ]
    
    VENDOR_ASSERTED_DOMAINS = [
        'nebius.com', 'openai.com', 'anthropic.com', 'company blogs'
    ]
    
    ACADEMIC_DOMAINS = [
        'arxiv.org', 'scholar.google.com', 'academia.edu', 'researchgate.net',
        'ieee.org', 'acm.org', 'springer.com', 'nature.com', 'science.org',
        'dl.acm.org', 'ieeexplore.ieee.org', 'link.springer.com', 'sciencedirect.com',
        'arxiv.org/list/cs.MA',  # Multi-agent systems
        'arxiv.org/list/cs.DC',  # Distributed computing
        'arxiv.org/list/cs.SY',  # Systems and control
        'arxiv.org/list/cs.GT',  # Computer science and game theory
        'mitpress.mit.edu',      # MIT Press for foundational textbooks
        'cambridge.org',         # Cambridge University Press
        'oxfordjournals.org'     # Oxford academic journals
    ]
    
    # Report section word targets
    EXECUTIVE_SUMMARY_WORDS = 200
    TOPLINE_WORDS = 100
    SIGNALS_WORDS = 600  # 6 signals × 100 words each
    MARKET_ANALYSIS_WORDS = 500
    TECH_DEEPDIVE_WORDS = 600
    COMPETITIVE_ANALYSIS_WORDS = 500
    OPERATOR_LENS_WORDS = 400
    INVESTOR_LENS_WORDS = 400
    BD_LENS_WORDS = 400
    ACTIONS_WORDS = 200
    SOURCES_WORDS = 200
    
    # LLM settings
    DEFAULT_MODEL = "gpt-5-mini-2025-08-07"
    ADVANCED_MODEL_NAME = "gpt-5-2025-08-07"
    ADVANCED_BUDGET_PCT = 0.25
    TEMPERATURE = 0.1
    RESPONSE_FORMAT = {"type": "json_object"}
    
    # Time window settings
    DEFAULT_DAYS_BACK = 7
    MAX_DAYS_BACK = 30
    
    # Entity types for extraction
    ENTITY_TYPES = ["ORG", "PERSON", "PRODUCT", "TICKER", "GEO"]
    
    # Topic taxonomy
    TOPIC_TAXONOMY = {
        'AI': ['ai', 'artificial intelligence', 'machine learning', 'llm', 'gpt'],
        'Cybersecurity': ['security', 'cyber', 'breach', 'vulnerability'],
        'Cloud': ['cloud', 'aws', 'azure', 'gcp', 'infrastructure'],
        'Robotics': ['robot', 'automation', 'autonomous'],
        'AR/VR': ['ar', 'vr', 'augmented', 'virtual', 'metaverse'],
        'Semiconductors': ['chip', 'semiconductor', 'nvidia', 'amd', 'intel'],
        'Policy': ['regulation', 'policy', 'government', 'compliance'],
        'Markets': ['market', 'trading', 'investment', 'capital', 'funding']
    }
    
    # Publisher mapping
    PUBLISHER_MAP = {
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
        'openai.com': 'OpenAI',
        'arxiv.org': 'arXiv'
    }
    
    # Credibility scores by source type
    CREDIBILITY_SCORES = {
        'independent_news': 0.8,
        'primary': 0.9,
        'trade_press': 0.7,
        'vendor_consulting': 0.5,
        'vendor_asserted': 0.4,
        'academic': 0.85
    }
    
    # Title-Source Alignment Settings
    MIN_TITLE_RELEVANCE_SCORE = 0.6  # Minimum relevance score for sources to be included
    ENABLE_TITLE_REFINEMENT = True   # Flag to enable/disable title updates based on content
    TITLE_REFINEMENT_THRESHOLD = 0.5  # If alignment < this, refine title
    ENABLE_QUERY_REFINEMENT = True   # Flag for query expansion before search
    QUERY_REFINEMENT_TEMPERATURE = 0.3  # Temperature for query refinement LLM calls
    
    # Image generation settings
    ENABLE_IMAGE_GENERATION = True
    ENABLE_SECTION_IMAGES = True  # Enable section images in addition to hero image
    MAX_SECTION_IMAGES = 4  # Maximum section images per report (excluding hero)
    MIN_SECTION_LENGTH_FOR_IMAGE = 400  # Minimum words in section to warrant image
    DALL_E_IMAGE_SIZE = "1792x1024"  # Landscape hero images (DALL-E 3: 1024x1024, 1792x1024, 1024x1792 | gpt-image-1: 1024x1024, 1536x1024, 1024x1536)
    DALL_E_QUALITY = "standard"      # "standard" or "hd" (DALL-E 3 only)
    DALL_E_MODEL = "dall-e-3"        # OpenAI API model name for image generation (temporarily using dall-e-3 while gpt-image-1 access propagates)
    IMAGE_GENERATION_TIMEOUT = 120.0  # Timeout in seconds for image generation API calls (2 minutes)
    # OpenAI Organization ID (optional - set in .env as OPENAI_ORGANIZATION for verified org)
    # Organization Name: Smart Technology Investments
    OPENAI_ORGANIZATION = None  # Set to org_xxxxx from platform.openai.com/org-settings
    
    # Intent Classification Settings
    ENABLE_INTENT_ROUTING = True  # Flag to enable theory vs market routing
    THEORY_KEYWORDS = ['theory', 'framework', 'model', 'algorithm', 'proof', 'consensus', 
                       'control', 'coordination', 'equilibrium', 'lyapunov', 'nash', 
                       'mathematical', 'theorem', 'proposition', 'formal', 'axiom',
                       'distributed', 'decentralized', 'hierarchical', 'cooperative', 
                       'leader', 'follower', 'protocol', 'agent-based', 'theoretical', 
                       'foundations', 'first principles', 'seminal', 'survey', 'command',
                       'multi-agent', 'swarm', 'consensus', 'agreement', 'synchronization',
                       'orchestration', 'federated', 'peer-to-peer', 'distributed systems',
                       'control theory', 'game theory', 'mechanism design', 'auction theory']
    MARKET_KEYWORDS = ['startup', 'funding', 'enterprise', 'vendor', 'product', 'trend', 
                       'investment', 'ipo', 'acquisition', 'revenue', 'market', 'sales']
    
    # Academic requirements for theory queries
    MIN_ACADEMIC_SOURCES_THEORY = 3
    SEMANTIC_THRESHOLD_THEORY = 0.65
    SEMANTIC_THRESHOLD_MARKET = 0.4
    
    # Confidence penalties
    CONFIDENCE_ACADEMIC_FRACTION_TARGET = 0.3  # For theory queries, require at least 30% academic sources
    THEORY_ACADEMIC_PENALTY_WEIGHT = 1.15  # Multiplier on penalty strength for theory queries
    
    # Theory-specific time windows
    THEORY_EXTENDED_DAYS_BACK = 365  # Recent academic sweeps up to 1 year
    THEORY_FOUNDATIONAL_DAYS_BACK = 1825  # Foundational/seminal up to 5 years
    
    # Theory fallback thresholds (more lenient for foundational sources)
    SEMANTIC_THRESHOLD_FOUNDATIONAL = 0.40  # Lower threshold for foundational sources
    MIN_TITLE_RELEVANCE_SCORE_FOUNDATIONAL = 0.35  # Lower threshold for foundational sources
    
    # Sprint deadline
    SPRINT_DEADLINE = "2025-10-31"
    
    # JSON-LD schema settings
    JSON_LD_CONTEXT = "https://schema.org"
    JSON_LD_TYPE = "Report"
    ORGANIZATION_NAME = "Smart Technology Investments LLC"
    ORGANIZATION_URL = "https://sti.ai"
    
    # Search provider settings
    SEARCH_PROVIDER = 'searxng'  # 'tavily' | 'searxng'
    SEARXNG_BASE_URL = 'http://localhost:8080'
    HTTP_TIMEOUT_SECONDS = 12
    MAX_RESULTS_PER_QUERY = 10
    SCRAPE_ENABLE = True
    
    # Market-path diversity controls
    MIN_DISTINCT_PUBLISHERS_MARKET = 2     # Require at least N distinct publishers
    SINGLE_DOMAIN_MAX_FRACTION = 0.6       # No more than 60% from any single domain
    VENDOR_CAP_PCT = 0.40                  # Max share from a single vendor domain
    
    # Market title relevance threshold (slightly more permissive than theory)
    MARKET_TITLE_RELEVANCE_THRESHOLD = 0.5
    MARKET_TITLE_MIN_ALIGNMENT = 0.45
    MARKET_TITLE_MIN_MUST_KEEP = 2
    MARKET_TITLE_BANNED = [
        'ai agents', 'ai trends', 'technology update', 'ai update', 'weekly ai brief'
    ]
    
    # Google Slides API settings
    ENABLE_SLIDES_GENERATION = True  # Set to True to enable slide deck generation
    GOOGLE_SLIDES_TEMPLATE_ID = ""    # Optional: Google Drive ID of master template (if empty, creates from scratch)
    GOOGLE_DRIVE_FOLDER_ID = "1CC5RtrsizDvQfsboJvvnawsBoiv5CMSj"  # Folder ID where presentations and images are saved
    GOOGLE_LOGO_URL = ""  # Optional: URL to logo image for hero slide replacement (must be publicly accessible)
    
    # Cashmere-style enhancements
    ENABLE_LAYOUT_BASED_SLIDES = True  # Use layout-based slide creation
    ENABLE_THEME_COLORS = True         # Use theme color system (with RGB fallback)
    SLIDES_TEMPLATE_CONFIG_PATH = "slides_template_config.py"  # Template config module path
    
    # Authentication: Use OAuth 2.0 (user account) or Service Account
    # OAuth 2.0 (recommended - uses your personal storage quota)
    # SECURITY: These values MUST be read from environment variables to avoid committing secrets
    # NEVER hardcode secrets in this file. Set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET
    # in your .env file (which is gitignored). If secrets were previously committed, rotate them
    # immediately in Google Cloud Console.
    GOOGLE_OAUTH_CLIENT_ID = os.getenv('GOOGLE_OAUTH_CLIENT_ID', '')  # OAuth 2.0 Client ID from Google Cloud Console
    GOOGLE_OAUTH_CLIENT_SECRET = os.getenv('GOOGLE_OAUTH_CLIENT_SECRET', '')  # OAuth 2.0 Client Secret from Google Cloud Console
    GOOGLE_OAUTH_TOKEN_FILE = ".google_token.json"  # File to store OAuth refresh token
    
    # Service Account (has storage limitations - only works with Shared Drives)
    GOOGLE_CREDENTIALS_PATH = ""  # Path to service account JSON (leave empty to use OAuth)
    GOOGLE_USE_OAUTH = True  # Set to True to use OAuth instead of service account
    
    # Thesis path thresholds / controls
    THESIS_CRITIQUE_MIN_SCORE = 0.70
    THESIS_MAX_REPAIRS = 2
    THEORY_CONFIDENCE_CAP = 0.60
    CANONICAL_SEMANTIC_FLOOR = 0.70
    
    # Thesis anchor source settings
    THESIS_ANCHOR_DOMAINS = [
        'ieeexplore.ieee.org',  # IEEE Xplore
        'dl.acm.org',  # ACM Digital Library
        'link.springer.com',  # Springer
        'sciencedirect.com',  # ScienceDirect
        'jstor.org',  # JSTOR
        'acm.org',  # ACM publications
        'springer.com',  # Springer publications
        'mitpressjournals.org',  # MIT Press journals
        'siam.org',  # SIAM journals
        'aps.org',  # American Physical Society
    ]
    THESIS_MIN_ANCHOR_SOURCES = 5  # Minimum anchor (non-preprint) sources
    THESIS_SOURCE_DIVERSITY_TARGET = 0.40  # 40%+ anchor sources
    THESIS_SINGLE_DOMAIN_THRESHOLD = 0.80  # Flag if >80% from single domain
    ANCHOR_COVERAGE_MIN = 0.70
    REQUIRE_ANCHORS_FOR_ASSETS = True
    
    @classmethod
    def get_total_target_words(cls) -> int:
        """Calculate total target word count"""
        return (cls.EXECUTIVE_SUMMARY_WORDS + cls.TOPLINE_WORDS + 
                cls.SIGNALS_WORDS + cls.MARKET_ANALYSIS_WORDS + 
                cls.TECH_DEEPDIVE_WORDS + cls.COMPETITIVE_ANALYSIS_WORDS +
                cls.OPERATOR_LENS_WORDS + cls.INVESTOR_LENS_WORDS + 
                cls.BD_LENS_WORDS + cls.ACTIONS_WORDS + cls.SOURCES_WORDS)
    
    @classmethod
    def validate_config(cls) -> bool:
        """Validate configuration settings"""
        # Check word count targets
        total_words = cls.get_total_target_words()
        if total_words != cls.TARGET_WORD_COUNT:
            print(f"Warning: Total word count ({total_words}) doesn't match target ({cls.TARGET_WORD_COUNT})")
        
        # Check confidence bounds
        if cls.CONFIDENCE_BOUNDS[0] >= cls.CONFIDENCE_BOUNDS[1]:
            print("Error: Invalid confidence bounds")
            return False
        
        # Check source requirements (allow zero as configured targets)
        if cls.MIN_INDEPENDENT_SOURCES < 0 or cls.MIN_PRIMARY_SOURCES < 0:
            print("Error: Invalid source requirements")
            return False
        
        return True


# Validate configuration on import
if not STIConfig.validate_config():
    print("Configuration validation failed!")
else:
    print("✅ STI Configuration loaded successfully")
    print(f"📊 Target word count: {STIConfig.get_total_target_words()}")
    print(f"🎯 Signals count: {STIConfig.SIGNALS_COUNT}")
    print(f"📈 Confidence bounds: {STIConfig.CONFIDENCE_BOUNDS}")

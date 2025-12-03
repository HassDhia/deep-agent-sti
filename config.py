"""
STI Configuration (Operator-Focused)

Minimal configuration surface for the signal-driven Brand Collab Lab workflow.
Values are intentionally lightweight so the agent can focus on operator outcomes
instead of academic routing or thesis scaffolding.
"""

import json
import os
from typing import Dict, List, Tuple

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


class STIConfig:
    """Operator-first configuration used across the runtime."""

    BRAND_TAGLINE = "Signal-Driven Brand Collaborations"
    DEFAULT_MODEL = os.getenv("STI_MODEL", "gpt-5-mini-2025-08-07")
    RESPONSE_FORMAT = {"type": "json_object"}
    MODEL_TEMPERATURE = float(os.getenv("STI_MODEL_TEMPERATURE", "0.15"))

    # Search and source controls
    SEARCH_PROVIDER = os.getenv("STI_SEARCH_PROVIDER", "searxng")
    SEARXNG_BASE_URL = os.getenv("SEARXNG_BASE_URL", "http://localhost:8080")
    HTTP_TIMEOUT_SECONDS = int(os.getenv("STI_HTTP_TIMEOUT", "12"))
    MAX_RESULTS_PER_QUERY = int(os.getenv("STI_MAX_RESULTS", "12"))
    MAX_SOURCE_COUNT = int(os.getenv("STI_MAX_SOURCES", "9"))
    MIN_OPERATOR_SIGNALS = int(os.getenv("STI_MIN_SIGNALS", "5"))
    DEFAULT_DAYS_BACK = int(os.getenv("STI_DAYS_BACK", "7"))
    MAX_DAYS_BACK = int(os.getenv("STI_MAX_DAYS", "21"))
    SOURCE_MIN_TOTAL = int(os.getenv("STI_SOURCE_MIN_TOTAL", "7"))
    SOURCE_MIN_CORE = int(os.getenv("STI_SOURCE_MIN_CORE", "3"))
    SOURCE_MIN_UNIQUE_DOMAINS = int(os.getenv("STI_SOURCE_MIN_UNIQUE", "3"))
    SOURCE_MIN_DATA_HEAVY = int(os.getenv("STI_SOURCE_MIN_DATA", "1"))
    SOURCE_SOFT_FLOOR = int(os.getenv("STI_SOURCE_SOFT_FLOOR", "5"))
    SOURCE_HARD_FLOOR = int(os.getenv("STI_SOURCE_HARD_FLOOR", "3"))
    SOURCE_MIN_IN_WINDOW = int(os.getenv("STI_SOURCE_MIN_IN_WINDOW", "3"))
    SOURCE_MIN_BACKGROUND = int(os.getenv("STI_SOURCE_MIN_BACKGROUND", "1"))
    SOURCE_MAX_DOMAIN_RATIO = float(os.getenv("STI_SOURCE_MAX_DOMAIN_RATIO", "0.6"))
    SEARCH_QUERY_AXES = [
        axis.strip()
        for axis in os.getenv(
            "STI_SEARCH_AXES",
            ",".join(
                [
                    "{query}",
                    "{query} collaboration activation foot traffic",
                    "{query} early window share exclusive drops",
                    "{query} tariff outlook margin pressure",
                ]
            ),
        ).split(",")
        if axis.strip()
    ]
    SEARXNG_CATEGORY_STEPS = [
        ["news"],
        ["news", "general"],
        ["news", "general", "science"],
    ]
    _axes_by_kind_raw = os.getenv(
        "STI_SEARCH_AXES_BY_KIND",
        json.dumps(
            {
                "store_as_studio": [
                    "{query}",
                    "{query} retail foot traffic activation",
                    "{query} flagship pop up in-store media",
                    "{query} experiential store studio collab",
                ],
                "pricing": [
                    "{query}",
                    "{query} margin pressure discounting elasticity",
                    "{query} promotion CPA blended margin",
                    "{query} retailer pricing test data",
                ],
                "collaboration": [
                    "{query}",
                    "{query} co-branded activation case study",
                    "{query} partnership foot traffic uplift",
                ],
            }
        ),
    )
    try:
        SEARCH_QUERY_AXES_BY_KIND: Dict[str, List[str]] = {
            key: [
                axis for axis in value if isinstance(axis, str) and axis.strip()
            ]
            for key, value in (json.loads(_axes_by_kind_raw) or {}).items()
        }
    except Exception:
        SEARCH_QUERY_AXES_BY_KIND = {}
    AXIS_HEALTH_PATH = os.getenv("STI_AXIS_HEALTH_PATH", "sti_reports/axis_health.json")
    AXIS_HEALTH_LOW_THRESHOLD = float(os.getenv("STI_AXIS_HEALTH_LOW_THRESHOLD", "0.15"))
    DIVERSITY_PROBES = [
        probe.strip()
        for probe in os.getenv(
            "STI_DIVERSITY_PROBES",
            ",".join(
                [
                    "{query} mastercard spendingpulse data",
                    "{query} nrf retail report",
                    "{query} visa retail momentum index",
                    "{query} deloitte retail study",
                ]
            ),
        ).split(",")
        if probe.strip()
    ]

    # Presentation
    MARKDOWN_HTML_TEMPLATE = os.getenv(
        "STI_MARKDOWN_HTML_TEMPLATE", "templates/article_minimal.html"
    )
    REPORT_RENDERERS = [
        renderer.strip()
        for renderer in os.getenv(
            "STI_REPORT_RENDERERS", "market_path_markdown,market_path_pdf"
        ).split(",")
        if renderer.strip()
    ]
    DARK_MODE_BACKGROUND = "#050709"
    ACCENT_COLOR = "#66d9ff"
    BODY_FONT = "'Space Grotesk', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    OPERATOR_VOICE_RULES = [
        "Write in short 2-4 sentence bursts.",
        "Eliminate corporate filler and buzzwords.",
        "Tie every insight to an operator move or measurable outcome.",
    ]
    MARKET_REPORT_META_PROMPT = (
        "You are the STI Operator-Grade Intelligence Engine.\n\n"
        "VOICE AND STYLE\n"
        "- Write for senior operators (Heads of Retail, CMOs, CFOs, Property, Partnerships).\n"
        "- No em dashes.\n"
        "- No marketing fluff or self-promotion about STI or \"this report\".\n"
        "- Prefer short, direct sentences; avoid long multi-clause chains.\n"
        "- Plain language over clever phrasing.\n"
        "- Every line should help someone decide what to test, measure, or stop doing.\n\n"
        "STRUCTURE\n"
        "- Follow the structure and JSON schema defined in the tool-specific prompt.\n"
        "- Do NOT add extra sections like Executive Take, Mini Case Story, or Closing Frame unless the tool explicitly asks for them.\n"
        "- Do NOT use arrows like \"->\" in any output.\n\n"
        "OUTPUT TEST\n"
        "1. Compress complexity without losing key mechanisms.\n"
        "2. Surface operator leverage and tradeoffs.\n"
        "3. Provide moves or metrics that can be acted on within one or two planning cycles.\n\n"
        "FAIL CONDITIONS\n"
        "- Rambling narrative, unsupported abstraction, self-referential commentary, or mood statements.\n"
        "- Sentences that do not change how an operator would think or act.\n\n"
        "FINAL FEELING\n"
        "The reader should walk away thinking, \"I know what this means for my next test.\""
    )

    REPORT_STRUCTURE: List[Tuple[str, str]] = [
        ("executive_summary", "Executive Summary"),
        ("signal_map", "Signal Map"),
        ("deep_analysis", "Deep Analysis"),
        ("pattern_matches", "Historical & Contemporary Pattern Matches"),
        ("brand_outcomes", "Brand & Operator Outcomes"),
        ("activation_kit", "Activation Kit"),
        ("risk_radar", "Risk Radar"),
        ("future_outlook", "Future Outlook"),
    ]

    SIGNAL_FAMILIES = ["Market", "Technology", "Cultural", "Behavioral"]
    ACTIVATION_PILLARS = [
        "Operator Workflow",
        "Studio Collaboration",
        "Retail & Hospitality Activation",
    ]
    IMAGE_BRIEF_TARGETS = ["hero", "signal_map", "case_studies"]

    SOURCE_DOMAIN_WEIGHTS = {
        "reuters.com": 0.95,
        "apnews.com": 0.9,
        "bloomberg.com": 0.9,
        "ft.com": 0.88,
        "wsj.com": 0.88,
        "nytimes.com": 0.9,
        "washingtonpost.com": 0.85,
        "nrf.com": 0.95,
        "deloitte.com": 0.92,
        "mastercard.com": 0.92,
        "adobe.com": 0.92,
        "placer.ai": 0.9,
        "sensormatic.com": 0.85,
        "retaildive.com": 0.8,
        "retailtouchpoints.com": 0.78,
        "modernretail.co": 0.78,
        "wwd.com": 0.8,
        "forbes.com": 0.65,
        "businessinsider.com": 0.65,
    }
    DEFAULT_SOURCE_WEIGHT = 0.6
    SOURCE_DOMAIN_GRADES = {
        "A": {
            "nrf.com",
            "deloitte.com",
            "mastercard.com",
            "adobe.com",
            "placer.ai",
            "sensormatic.com",
            "reuters.com",
            "apnews.com",
            "bloomberg.com",
            "ft.com",
            "wsj.com",
            "nytimes.com",
            "washingtonpost.com",
        },
        "B": {
            "retaildive.com",
            "retailtouchpoints.com",
            "modernretail.co",
            "wwd.com",
            "techcrunch.com",
            "theinformation.com",
            "semianalysis.com",
            "businessoffashion.com",
        },
        "C": {
            "forbes.com",
            "businessinsider.com",
            "usatoday.com",
            "local10.com",
            "nbcnewyork.com",
            "timeout.com",
        },
    }
    SOURCE_BLOCKLIST = {
        "msn.com",
        "news.yahoo.com",
        "news.google.com",
        "pressreader.com",
        "theguardian.com",
        "telegraph.co.uk",
        "standard.co.uk",
    }
    SOURCE_GRADE_FALLBACK = "C"
    SIGNAL_MAX_COUNT = int(os.getenv("STI_SIGNAL_MAX", "6"))
    US_REGION_HINTS = [
        "us",
        "u.s.",
        "american",
        "united states",
        "us-based",
        "black friday",
        "thanksgiving",
    ]
    SIGNAL_MIN_STRENGTH = float(os.getenv("STI_SIGNAL_MIN_STRENGTH", "0.75"))
    SIGNAL_MIN_US_FIT = float(os.getenv("STI_SIGNAL_MIN_US_FIT", "0.8"))
    SIGNAL_MIN_SUPPORT = int(os.getenv("STI_SIGNAL_MIN_SUPPORT", "2"))
    SIGNAL_REQUIRE_CORE_SUPPORT = os.getenv("STI_SIGNAL_REQUIRE_CORE_SUPPORT", "true").lower() != "false"
    SIGNAL_SUPPORT_COVERAGE_MIN = float(os.getenv("STI_SIGNAL_SUPPORT_COVERAGE_MIN", "0.5"))
    TOP_SIGNAL_DOMAIN_CHECK_COUNT = int(os.getenv("STI_TOP_SIGNAL_DOMAIN_CHECK_COUNT", "3"))
    SIGNAL_REQUIRE_DATA_HEAVY_TOP = os.getenv("STI_SIGNAL_REQUIRE_DATA_HEAVY_TOP", "true").lower() != "false"
    SIGNAL_TARGET_COUNT = int(os.getenv("STI_SIGNAL_TARGET", "6"))
    TOP_OPERATOR_MOVE_COUNT = 3
    QUALITY_THRESHOLD = float(os.getenv("STI_SOURCE_QUALITY", "0.7"))
    ACTIVATION_THRESHOLDS = {
        "mini_burst": {"cpa": 0.8, "redemption": 0.15},
        "staged_discount": {"margin_delta_bps": -100, "repeat_rate_delta": 0.0},
    }
    MAX_ACTIVATION_PLAYS = int(os.getenv("STI_ACTIVATION_MAX", "3"))
    TARGET_READ_TIME_MINUTES = int(os.getenv("STI_TARGET_READ_MINUTES", "15"))

    # Image generation
    ENABLE_IMAGE_GENERATION = os.getenv("STI_ENABLE_IMAGES", "true").lower() == "true"
    ENABLE_SECTION_IMAGES = True
    MAX_SECTION_IMAGES = 2
    MIN_SECTION_LENGTH_FOR_IMAGE = 200
    DALL_E_MODEL = os.getenv("STI_IMAGE_MODEL", "gpt-image-1-mini")
    DALL_E_IMAGE_SIZE = os.getenv("STI_IMAGE_SIZE", "1536x1024")
    IMAGE_GENERATION_TIMEOUT = float(os.getenv("STI_IMAGE_TIMEOUT", "120"))
    OPENAI_ORGANIZATION = os.getenv("OPENAI_ORGANIZATION")

    SOCIAL_DISCLOSURE = (
        "Signals validated inside the current window unless marked. "
        "Reach out to Brand Collab Lab for operator instrumentation."
    )

    OUTPUT_FILES = [
        "intelligence_report.md",
        "market_path_report.md",
        "market_path_report.pdf",
        "intelligence_report.jsonld",
        "metadata.json",
    ]

    REPORT_CONTRACT = {
        "title_prefix": "Signal Report — ",
        "sections": [
            "Executive Summary",
            "Signal Map",
            "Quant Anchors",
            "Measurement Plan",
            "Deep Analysis",
            "Historical & Contemporary Pattern Matches",
            "Brand & Operator Outcomes",
            "Activation Kit — Brand Collab Lab Handoff",
            "Risk Radar",
            "Future Outlook",
            "Sources",
        ],
        "read_time_target": TARGET_READ_TIME_MINUTES,
        "word_target": 2600,
        "image_targets": {"min": 3, "max": 5},
        "cta": {
            "primary": "Talk to Brand Collab Lab",
            "activation": "Want this play translated for your brand? → /collab-lab",
        },
    }

    @classmethod
    def operator_sections(cls) -> List[Tuple[str, str]]:
        return cls.REPORT_STRUCTURE

    @classmethod
    def section_keys(cls) -> List[str]:
        return [section for section, _ in cls.REPORT_STRUCTURE]

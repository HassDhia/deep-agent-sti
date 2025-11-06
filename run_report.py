#!/usr/bin/env python3
"""
Simple CLI wrapper for STI Enhanced Intelligence System
Usage: python3 run_report.py "cryptocurrency markets" [--days 7] [--debug]
"""

import argparse
import logging
import os
import sys

# Configure logging FIRST, before any other imports that might set it
logging.basicConfig(
    level=logging.INFO,  # Default to INFO
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

from dotenv import load_dotenv
from enhanced_mcp_agent import EnhancedSTIAgent
from config import STIConfig

def enable_debug_logging():
    """Enable DEBUG level for all loggers"""
    # Set root logger to DEBUG
    logging.getLogger().setLevel(logging.DEBUG)
    # Update all existing loggers to DEBUG
    for logger_name in logging.Logger.manager.loggerDict:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.DEBUG)

def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description='Generate STI intelligence reports with custom queries'
    )
    parser.add_argument(
        'query',
        type=str,
        help='Search query (e.g., "cryptocurrency markets", "AI technology trends")'
    )
    parser.add_argument(
        '--days',
        type=int,
        default=7,
        help='Number of days to look back (default: 7)'
    )
    parser.add_argument(
        '--html',
        action='store_true',
        help='Generate HTML version of report (default: True)'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging (very verbose output)'
    )
    
    args = parser.parse_args()
    
    # Load environment variables first (needed for imports)
    load_dotenv()
    
    # Set logging level to DEBUG if flag is provided
    # This must happen after imports because modules configure logging on import
    if args.debug:
        enable_debug_logging()
        print("🐛 Debug logging enabled - verbose output will be shown")
        print("=" * 70)
    openai_api_key = os.getenv("OPENAI_API_KEY")
    tavily_api_key = os.getenv("TAVILY_API_KEY")
    
    if not openai_api_key:
        print("❌ Error: Missing OPENAI_API_KEY")
        print("Please set OPENAI_API_KEY in your .env file")
        sys.exit(1)
    
    # Only require Tavily key if Tavily is the selected provider
    search_provider = getattr(STIConfig, 'SEARCH_PROVIDER', 'searxng')
    if search_provider == 'tavily' and not tavily_api_key:
        print("❌ Error: Missing TAVILY_API_KEY (required when SEARCH_PROVIDER='tavily')")
        print("Set TAVILY_API_KEY in your .env file or switch to SearXNG in config.py")
        sys.exit(1)
    
    # Pass empty string if not needed
    if not tavily_api_key:
        tavily_api_key = ""
    
    # Initialize agent
    print(f"🚀 STI Enhanced Intelligence System")
    print(f"📊 Query: '{args.query}'")
    print(f"📅 Time window: Past {args.days} days")
    print("=" * 70)
    
    agent = EnhancedSTIAgent(
        openai_api_key=openai_api_key,
        tavily_api_key=tavily_api_key
    )
    
    # Re-enable debug logging after agent initialization (in case new loggers were created)
    if args.debug:
        enable_debug_logging()
    
    # Generate report
    print("\n🔍 Generating intelligence report...")
    markdown_report, json_ld_artifact = agent.search(args.query, days_back=args.days)
    
    # Display summary
    print("\n" + "=" * 70)
    print("🎉 REPORT GENERATED SUCCESSFULLY!")
    print("=" * 70)
    print(f"📊 Confidence: {json_ld_artifact.get('aggregateRating', {}).get('ratingValue', 'N/A')}")
    print(f"📝 Word Count: {json_ld_artifact.get('wordCount', 'N/A')}")
    print(f"📁 Sources: {len(json_ld_artifact.get('hasPart', []))}")
    print(f"💾 Files saved in: sti_reports/")
    print("📱 Social media content generated (3 formats)")
    print("\nCheck the sti_reports directory for your complete intelligence report.")

if __name__ == "__main__":
    main()


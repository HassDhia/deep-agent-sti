#!/usr/bin/env python3
"""
Simple CLI wrapper for STI Enhanced Intelligence System
Usage: python3 run_report.py "cryptocurrency markets" [--days 7] [--debug]
"""

import argparse
import logging
import os
import random
import sys
from datetime import datetime

# Configure logging FIRST, before any other imports that might set it
logging.basicConfig(
    level=logging.INFO,  # Default to INFO
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

from dotenv import load_dotenv
from enhanced_mcp_agent import EnhancedSTIAgent
from config import STIConfig
from file_utils import save_run_manifest

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
        '--budget-advanced',
        type=int,
        default=0,
        help='Token budget reserved for premium model usage (default: 0)'
    )
    parser.add_argument(
        '--seed',
        type=int,
        default=42,
        help='Random seed for reproducibility (default: 42)'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging (very verbose output)'
    )
    
    args = parser.parse_args()
    
    # Load environment variables first (needed for imports)
    load_dotenv()
    
    random.seed(args.seed)
    try:
        import numpy as _np

        _np.random.seed(args.seed)
    except Exception:
        pass

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
    # Call agent.search with updated arguments and handle new status/output structure
    markdown_report, json_ld_artifact, run_summary = agent.search(
        args.query,
        days_back=args.days,
        seed=args.seed,
        budget_advanced=args.budget_advanced,
    )

    status = getattr(agent, "last_run_status", {}) or {}
    if not status.get("quality_gates_passed", True):
        logging.error("Quality gates failed; aborting publish.")
        sys.exit(2)

    if status.get("asset_gated", False):
        logging.info("Some downstream assets were skipped due to gating policies.")

    report_dir = status.get("report_dir")
    manifest = status.get("run_manifest")
    if report_dir and manifest:
        try:
            save_run_manifest(report_dir, manifest)
        except Exception as manifest_err:
            logging.error("Failed to persist run manifest: %s", manifest_err)
    
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

    run_summary = run_summary or {}
    artifacts = run_summary.get('artifacts', {})
    report_dir = artifacts.get('report_dir')
    model_versions = {
        'primary': getattr(agent, 'model_name', 'unknown'),
        'advanced': getattr(STIConfig, 'ADVANCED_MODEL_NAME', None),
    }

    if report_dir:
        manifest = {
            'query': args.query,
            'days': args.days,
            'seed': args.seed,
            'budget_advanced': args.budget_advanced,
            'generated_at': datetime.utcnow().isoformat() + 'Z',
            'models': model_versions,
            'metrics': run_summary.get('metrics', {}),
            'confidence_breakdown': run_summary.get('confidence_breakdown', {}),
            'premium': run_summary.get('premium', {}),
            'artifacts': artifacts,
        }
        save_run_manifest(report_dir, manifest)
        print(f"🧾 Manifest saved to: {report_dir}/manifest.json")
    else:
        print("⚠️ Report directory missing from run summary; manifest not saved.")

    breakdown = run_summary.get('confidence_breakdown', {})
    if breakdown:
        print(f"🔎 Confidence Breakdown: {breakdown}")

    metrics = run_summary.get('metrics', {})
    anchor_cov = metrics.get('anchor_coverage')
    if anchor_cov is not None:
        print(f"📚 Anchor Coverage: {anchor_cov:.2f}")
    quant_flags = metrics.get('quant_flags', 0)
    if quant_flags:
        print(f"🧮 Math Guard warnings: {quant_flags}")

    gate_failures = []
    anchor_threshold = getattr(STIConfig, 'ANCHOR_COVERAGE_MIN', 0.70)
    if run_summary.get('intent') == 'theory' and anchor_cov is not None and anchor_cov < anchor_threshold:
        gate_failures.append(
            f"Anchor coverage {anchor_cov:.2f} below threshold {anchor_threshold:.2f} for thesis path"
        )
    if quant_flags:
        gate_failures.append(f"{quant_flags} unresolved math guard warning(s)")

    premium_info = run_summary.get('premium', {})
    requested = set(premium_info.get('requested', []))
    executed = premium_info.get('executed', {}) or {}
    for task in requested:
        if not executed.get(task, False):
            gate_failures.append(f"Premium task '{task}' requested but not executed")

    if gate_failures:
        print("\n❌ Quality gates failed:")
        for failure in gate_failures:
            print(f"  - {failure}")
        sys.exit(2)
    else:
        print("\n✅ Quality gates passed.")

if __name__ == "__main__":
    main()


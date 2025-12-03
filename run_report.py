#!/usr/bin/env python3
"""
CLI entrypoint for the operator-only STI workflow.
"""

from __future__ import annotations

import argparse
import logging
import os
import random
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

from config import STIConfig
from enhanced_mcp_agent import EnhancedSTIAgent
from file_utils import file_manager
from logging_utils import capture_terminal_output, log_exception, setup_run_logging
from social_media_agent import SocialMediaAgent


def enable_debug_logging() -> None:
    logging.getLogger().setLevel(logging.DEBUG)
    for logger_name in logging.Logger.manager.loggerDict:
        logging.getLogger(logger_name).setLevel(logging.DEBUG)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate signal-driven operator reports.")
    parser.add_argument("query", type=str, help="Search query/topic.")
    parser.add_argument("--days", type=int, default=STIConfig.DEFAULT_DAYS_BACK, help="Days back to search.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility.")
    parser.add_argument("--skip-social", action="store_true", help="Skip social content generation.")
    parser.add_argument("--debug", action="store_true", help="Enable verbose logging.")
    parser.add_argument(
        "--trace",
        action="store_true",
        help="Emit step-by-step pipeline traces (prompts, search payloads, MCP responses).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    load_dotenv()

    if not os.getenv("OPENAI_API_KEY"):
        print("❌ Missing OPENAI_API_KEY. Set it in your environment or .env file.")
        sys.exit(1)

    random.seed(args.seed)

    report_dir = file_manager.create_report_directory("operator", args.query, args.days)
    run_logger, log_path = setup_run_logging(report_dir, args.query)

    with capture_terminal_output(log_path):
        if args.debug:
            enable_debug_logging()
            run_logger.debug("Debug logging enabled.")

        print("🚀 STI Operator Briefing")
        print(f"📊 Query: {args.query}")
        print(f"📅 Window: Past {args.days} days")
        print("=" * 60)

        try:
            agent = EnhancedSTIAgent(openai_api_key=os.getenv("OPENAI_API_KEY"), trace_mode=args.trace)
            report = agent.generate_report(args.query, args.days)
        except Exception as exc:
            log_exception(run_logger, exc, context="generate_report", query=args.query, days_back=args.days)
            print("❌ Report generation failed. Check logs for details.")
            sys.exit(1)

        try:
            report_dir_actual = file_manager.save_enhanced_report(report, generate_html=True, report_dir=report_dir)
        except Exception as exc:
            log_exception(run_logger, exc, context="save_enhanced_report", query=args.query)
            print("❌ Failed to persist report artifacts.")
            sys.exit(1)

        if not args.skip_social:
            try:
                social_agent = SocialMediaAgent(os.getenv("OPENAI_API_KEY"), STIConfig.DEFAULT_MODEL)
                social_payload = social_agent.generate_all_formats(
                    report.get("markdown", ""), {"confidence": report["confidence"]["score"], **report}
                )
                file_manager.save_social_media_content(report_dir_actual, social_payload)
            except Exception as exc:
                log_exception(run_logger, exc, context="social_media_generation", query=args.query)

        print("\n✅ Report ready.")
        print(f"📁 Output directory: {report_dir_actual}")
        confidence = report.get("confidence", {}).get("score", 0.0)
        print(f"🧭 Confidence: {confidence:.2f}")


if __name__ == "__main__":
    main()

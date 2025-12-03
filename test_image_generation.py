#!/usr/bin/env python3
"""
Smoke tests for the image generation + HTML pipeline.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Dict, Any

from config import STIConfig
from html_converter_agent import HTMLConverterAgent
from image_generator import ImageGenerator


def load_report_bundle(report_dir: Path) -> Dict[str, Any]:
    bundle = {}
    with open(report_dir / "metadata.json", encoding="utf-8") as fh:
        metadata = json.load(fh)
    with open(report_dir / "intelligence_report.md", encoding="utf-8") as fh:
        bundle["markdown"] = fh.read()
    with open(report_dir / "intelligence_report.jsonld", encoding="utf-8") as fh:
        bundle["json_ld"] = json.load(fh)
    bundle.update(
        {
            "title": metadata.get("title"),
            "query": metadata.get("query"),
            "time_window": metadata.get("time_window", {}),
            "executive_summary": metadata.get("executive_summary", ""),
            "highlights": metadata.get("highlights", []),
            "confidence": metadata.get("confidence", {}),
        }
    )
    for name in ("sources", "signals", "sections"):
        path = report_dir / f"{name}.json"
        if path.exists():
            with open(path, encoding="utf-8") as fh:
                bundle[name] = json.load(fh)
    briefs_path = report_dir / "images" / "briefs.json"
    if briefs_path.exists():
        with open(briefs_path, encoding="utf-8") as fh:
            bundle["image_briefs"] = json.load(fh)
    return bundle


def test_configuration() -> bool:
    print("Checking image configuration…")
    fields = [
        ("ENABLE_IMAGE_GENERATION", STIConfig.ENABLE_IMAGE_GENERATION),
        ("DALL_E_MODEL", STIConfig.DALL_E_MODEL),
        ("DALL_E_IMAGE_SIZE", STIConfig.DALL_E_IMAGE_SIZE),
    ]
    ok = True
    for key, value in fields:
        status = "✅" if value not in (None, "") else "❌"
        print(f" {status} {key}: {value}")
        ok = ok and value not in (None, "")
    if not os.getenv("OPENAI_API_KEY"):
        print(" ❌ OPENAI_API_KEY missing")
        ok = False
    return ok


def test_image_generator_init() -> bool:
    print("Initializing ImageGenerator…")
    generator = ImageGenerator()
    if not generator.client:
        print(" ❌ OpenAI client not configured (set OPENAI_API_KEY)")
        return False
    print(" ✅ Client ready")
    return True


def test_html_conversion(report_dir: Path) -> bool:
    bundle = load_report_bundle(report_dir)
    converter = HTMLConverterAgent()
    html = converter.convert(bundle, str(report_dir))
    if "Signal Map" in html and "Activation Kit" in html:
        print(f" ✅ HTML generated ({len(html)} chars)")
        return True
    print(" ❌ HTML missing expected sections")
    return False


def main() -> int:
    reports_dir = Path("sti_reports")
    if not reports_dir.exists():
        print("No reports found. Run `python run_report.py \"query\"` first.")
        return 1
    report_dirs = sorted(
        [p for p in reports_dir.iterdir() if p.is_dir() and "sti_operator_output" in p.name],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not report_dirs:
        print("No operator report directories found.")
        return 1
    latest = report_dirs[0]
    print(f"Using latest report: {latest.name}")

    results = {
        "config": test_configuration(),
        "generator": test_image_generator_init(),
        "html": test_html_conversion(latest),
    }
    for name, result in results.items():
        print(f"{'✅' if result else '❌'} {name}")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())


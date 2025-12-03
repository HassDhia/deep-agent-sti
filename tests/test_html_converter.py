import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-key")

from enhanced_mcp_agent import EnhancedSTIAgent, SourceRecord
from html_converter_agent import HTMLConverterAgent
from image_generator import TEMPLATE_VERSION
from renderers.context import build_market_path_context
from renderers.market_path_markdown import MarketPathMarkdownRenderer
from renderers.market_path_pdf import MarketPathPDFRenderer
from renderers.legacy_html import LegacyHTMLRenderer
from metrics import known_metric_ids
from visual_lint import lint_visual_stats


def sample_report_bundle():
    return {
        "title": "Signal Report — Retail Collabs",
        "query": "retail collaborations",
        "time_window": {"start": "2024-05-01", "end": "2024-05-07", "days": 7},
        "read_time_minutes": 12,
        "spec_version": "v1",
        "spec_notes": [],
        "evidence_note": "Directional evidence: 9 sources • 9 domains • 4 in-window / 5 background • support coverage 75%",
        "evidence_regime": "directional",
        "executive_summary": "Operators are borrowing drop mechanics to unlock new guest value.",
        "highlights": ["Hospitality behaves like streetwear.", "Studios lean into tactile proof."],
        "top_operator_moves": [
            "Lock two pilot sites",
            "Wire QR to POS",
            "Stage one live atelier",
        ],
        "fast_path": {"sections": ["executive_summary", "highlights", "top_operator_moves", "play_summary"]},
        "fast_stack": {
            "headline": "Holiday demand compresses into two windows",
            "why_now": "Studios use pop-ups to defend margin",
            "next_30_days": "Lock the early-access pilots and instrumentation",
        },
        "spine": {
            "what": "Signals show drop mechanics in retail",
            "so_what": "Success = guardrailed measurement",
            "now_what": "Run the two-arm pilot",
        },
        "play_summary": [
            {"label": "Early-access window", "success": "Footfall uplift ≥1.10×"},
            {"label": "Bundle vs markdown", "success": "Event CPA ≤0.80×"},
        ],
        "signals": [
            {
                "category": "Market",
                "name": "Hotel drops mimic streetwear",
                "description": "Operators are turning suites into capsules with precise release windows.",
                "operator_move": "Prototype capsules.",
                "operator_scan": "Test hotel capsules in NYC",
                "spine_hook": "Hotels run streetwear-grade drops",
                "time_horizon": "now",
                "citations": [1],
                "strength": 0.82,
                "US_fit": 0.78,
                "on_spine": True,
            },
            {
                "category": "Culture",
                "name": "Studios lean into tactile proof",
                "description": "Studios are staging live ateliers for loyalty spikes.",
                "operator_move": "Stage live ateliers.",
                "operator_scan": "Run live ateliers in flagships",
                "spine_hook": "Studios prove loyalty with tactile events",
                "time_horizon": "6-week",
                "citations": [1],
                "strength": 0.84,
                "US_fit": 0.8,
                "on_spine": True,
            },
        ],
        "sources": [{"id": 1, "publisher": "Reuters", "title": "Hospitality Trend", "date": "2024-05-05", "url": "https://example.com"}],
        "quant": {
            "spine_hook": "Success shows up in guarded CPA + share lifts",
            "measurement_plan": [
            {
                "metric": "foot_traffic_uplift",
                "expression": "+12%",
                "owner": "Retail Ops",
                "timeframe": "Nov window",
                "why_it_matters": "Proves the window concentrates demand",
            },
            {
                "metric": "early_window_share",
                "expression": "22-28%",
                "owner": "Merch",
                "timeframe": "Week -1 to 0",
                "why_it_matters": "Ensures buyers grow faster than promo intensity",
            },
            ],
            "anchors": [
                {
                    "headline": "Event CPA at 0.78x baseline",
                    "status": "observed",
                    "band": "base",
                    "owner": "Finance",
                    "expression": "CPA running 0.78× baseline",
                    "source_ids": [1],
                },
            ],
        },
        "pilot_spec": {
            "scenario": "creator_residency_flagship",
            "store_count": 1,
            "store_type": "flagship",
            "duration_weeks": 4,
            "window": "Nov pilot window",
            "primary_move": "a creator residency swap for one markdown weekend",
            "owner_roles": ["Head of Retail", "Head of Partnerships", "Head of Marketing", "Finance"],
            "location_radius_miles": 5,
            "key_metrics": ["foot_traffic_uplift", "early_window_share", "event_cpa"],
        },
        "metric_spec": {
            "foot_traffic_uplift": {
                "label": "Local Flagship Footfall",
                "target_range": [10, 15],
                "unit": "% vs baseline",
                "stage": "target",
                "owner": "Store ops",
                "target_text": "10–15% vs baseline week",
                "notes": "base guardrail",
            },
            "early_window_share": {
                "label": "Share Of Transactions In First 48 Hours",
                "target_range": [12, 15],
                "unit": "% of weekly transactions",
                "stage": "observed",
                "owner": "Merch + Analytics",
                "target_text": "12–15% of weekly transactions",
                "notes": "observed",
            },
            "event_cpa": {
                "label": "Event CPA",
                "target_range": [0, 0.8],
                "unit": "× baseline",
                "stage": "guardrail",
                "owner": "Finance",
                "target_text": "≤0.80× baseline",
                "notes": "guardrail",
            },
        },
        "role_actions": {
            "Head of Retail": "Stand up the 4-week residency in the flagship and insist on daily guardrail readouts.",
            "Head of Partnerships": "Curate the creator roster within five miles and co-script content + inventory windows.",
            "Finance": "Block scale unless Local Flagship Footfall, early-window share, and event CPA stay inside guardrails.",
        },
        "executive_letter": {
            "subtitle": "Turning holiday experiments into loyalty gains",
            "tldr": "We can trade one markdown window for a loyalty-rich pop-up sprint if we approve a two-week test now.",
            "sections": [
                {"name": "What we are seeing", "body": "Retailers are compressing holiday demand into two precise windows and measuring footfall daily. Loyalty enrollments spike when pop-ups add instant digital rewards."},
                {"name": "The move", "body": "Run an early-access A/B plus a pop-up loyalty funnel backed by BNPL and instant rewards. Keep the test tight with daily readouts and predefined kill switches."},
                {"name": "Size of prize", "body": "Targets stay disciplined: **10–15%** footfall lift (stretch ≥ **25%**), **20–30%** early-window share, event CPA ≤ **0.8×** baseline, QR redemption ≥ **5%** of footfall within 30 days."},
                {"name": "Risks", "body": "Noise from short windows, reward system failures, or negative BNPL economics. We mitigate with holdouts, canary tech rollouts, and net-contrib monitoring."},
                {"name": "Decision requested", "body": "Approve the two-week test, assign a single sponsor across Retail/Marketing/Finance, and authorize Brand Collab Lab plus analytics to instrument and report daily."}
            ],
            "bullets_investable": [
                "Holiday demand is compressing into two short windows with measurable lift",
                "Pop-ups now outperform permanent markdowns for loyalty acquisition",
                "Instant rewards plus BNPL let us hold margin while growing members"
            ],
            "bullets_targets": [
                "Footfall +10–15% (stretch ≥25%) during the two-week window",
                "Early-window share from 12–15% baseline to 20–30% of transactions",
                "Event CPA ≤0.80× baseline with QR/instant rewards ≥5% within 30 days"
            ],
            "primary_cta": "Approve the focused holiday test with a single sponsor and daily instrumentation.",
            "email_subject": "Proposal: Holiday pop-up test to trade markdowns for loyalty and better unit economics"
        },
        "letter_bullets": {
            "investable": [
                "Holiday demand is compressing into two measurable windows",
                "Pop-ups beat permanent markdowns for loyalty acquisition",
                "Instant rewards plus BNPL let us defend margin"
            ],
            "targets": [
                "Footfall +10–15% (stretch ≥25%) within the two-week window",
                "Early-window share to 20–30% of transactions over the window",
                "Event CPA ≤0.80× baseline, QR/redemption ≥5% inside 30 days"
            ]
        },
        "letter_primary_cta": "Approve the focused holiday test with a single sponsor.",
        "letter_email_subject": "Proposal: Holiday pop-up test to trade markdowns for loyalty",
        "letter_primary_cta_link": "https://example.com/cta",
        "letter_subtitle": "Turning short holiday windows into measurable loyalty",
        "letter_tldr": "Let’s swap one markdown window for a loyalty-heavy pop-up test and measure the economics in two weeks.",
        "sections": {
            "deep_analysis": {
                "sections": [
                    {
                        "title": "Systems shift",
                        "spine_position": "what",
                        "priority": 1,
                        "scan_line": "Pop-ups borrow drop math",
                        "insight": "Operators lean on scarcity.",
                        "operator_note": "Instrument loyalty spans.",
                        "instrument_next": "Instrument uplift vs promo share.",
                    }
                ]
            },
            "pattern_matches": [
                {
                    "label": "Streetwear capsules",
                    "then": "2017 sneaker drops primed guests for scarce windows.",
                    "now": "Studios re-use the cadence inside hotels.",
                    "operator_leap": "Borrow the cadence.",
                }
            ],
            "brand_outcomes": [
                {
                    "title": "Higher repeat visits",
                    "description": "Temporal scarcity drives new guests.",
                    "impact": "Repeat visits",
                    "time_horizon": "next 90 days",
                    "owner": "Retail ops",
                }
            ],
            "activation_kit": [
                {
                    "display": {
                        "pillar": "Operator Workflow",
                        "play_name": "Tiered access lobby lab",
                        "card_title": "Lobby lab",
                        "persona": "GM",
                        "best_fit": "Hotels with excess lobby space",
                        "not_for": "Teams without QR",
                        "thresholds_summary": "CPA ≤0.8× + redemption ≥5%",
                        "why_now": "Signals 1 + 2 show appetite.",
                        "proof_point": "Signals 1 + 2 show appetite.",
                        "time_horizon": "immediate",
                        "placement_options": ["Lobby", "Penthouse"],
                    },
                    "ops": {
                        "operator_owner": "GM",
                        "collaborator": "Local atelier",
                        "collab_type": "brand↔operator",
                        "thresholds": {"cpa": "≤0.8×", "redemption": ">=5%"},
                        "prerequisites": ["QR → POS"],
                        "target_map": [{"org_type": "Hotel", "role": "GM", "why_now": "Empty lobbies"}],
                        "cadence": [
                            {"day": "0", "subject": "Kickoff", "narrative": "Share guardrails", "cta": "Approve pilot"},
                            {"day": "3", "subject": "Instrumentation", "narrative": "Confirm QR to POS", "cta": "Send dashboard"},
                            {"day": "7", "subject": "Go/No-Go", "narrative": "Confirm staffing", "cta": "Launch lobby lab"},
                        ],
                        "zero_new_sku": True,
                        "ops_drag": "low",
                    },
                }
            ],
            "risk_radar": [
                {
                    "risk_name": "Over-exposure",
                    "scan_line": "Risk: too many drops",
                    "trigger": "Too many drops",
                    "detection": "Declining open rates",
                    "mitigation": "Throttle releases",
                    "severity": 2,
                    "likelihood": 2,
                }
            ],
            "future_outlook": [
                {
                    "horizon": "6-month",
                    "headline": "Studios run nightly residencies",
                    "scan_line": "If true, residencies scale within six months",
                    "description": "Studios test residency formats.",
                    "operator_watch": "Nights sold",
                    "collaboration_upside": "Shared rev",
                    "confidence": 0.7,
                }
            ],
        },
        "confidence": {"score": 0.72, "breakdown": {"source_diversity": 0.8, "signal_density": 1.0, "activation_readiness": 0.5, "pattern_depth": 0.5}},
        "markdown": "# mock markdown",
        "json_ld": {"@context": "https://schema.org"},
        "image_briefs": {"hero": "Moody lobby scene", "signal_map": "Neon nodes", "case_studies": ["Studio residency", "Hospitality drop"]},
    }


def test_market_path_markdown_renderer(tmp_path):
    bundle = sample_report_bundle()
    (tmp_path / "intelligence_report.html").write_text("<html></html>", encoding="utf-8")
    renderer = MarketPathMarkdownRenderer()
    files = renderer.render(bundle, str(tmp_path))
    assert files
    output = Path(files[0]).read_text(encoding="utf-8")
    assert "Concretely, I'd run" in output
    assert "In practice this only works if a few teams move in step." in output
    assert "**Why this works**" in output
    assert "## " not in output
    assert "\n|" not in output
    assert "_Decision Map_" not in output
    assert "_Measurement Spine_" not in output
    assert "_Sources & Confidence_" in output
    assert "[Read HTML intelligence report](intelligence_report.html)" in output
    assert "Intelligence report" in output
    for metric_id in bundle["pilot_spec"]["key_metrics"]:
        label = bundle["metric_spec"][metric_id]["label"]
        assert label in output
    for phrase in ["Retail needs to", "Partnerships needs to", "Finance needs to"]:
        assert phrase in output
    assert "Head of Retail" not in output
    banned_tokens = [
        "foot_traffic_uplift",
        "early_window_share",
        "buyer_activity_share",
        "event_cpa",
        "qr_redemption",
        "-> tracks",
        "-> Mandate",
        "| base |",
        "| stretch |",
        "behavioral signal:",
        "Signal:",
        "(M",
        "Second-order:",
        "Event CPA Ratio",
        "Redemption percent",
        " 1 2 ",
    ]
    banned_tokens.extend(sorted(known_metric_ids()))
    for token in banned_tokens:
        assert token not in output
    assert "_Evidence:_" not in output
    assert "twelve stores" not in output.lower()
    assert "Treat this as a directional read." in output
    assert "Evidence:" not in output
    assert "Evidence Directional evidence" in output
    assert "Local Flagship Footfall" in output
    for metric_id in bundle["pilot_spec"]["key_metrics"]:
        label = bundle["metric_spec"][metric_id]["label"]
        assert label in output


def test_market_path_pdf_renderer(tmp_path):
    bundle = sample_report_bundle()
    (tmp_path / "intelligence_report.html").write_text("<html></html>", encoding="utf-8")
    renderer = MarketPathPDFRenderer()
    files = renderer.render(bundle, str(tmp_path))
    pdf_path = Path(files[0])
    assert pdf_path.exists()
    header = pdf_path.read_bytes()[:4]
    assert header == b"%PDF"


def test_markdown_html_renderer_outputs_both_files(tmp_path):
    bundle = sample_report_bundle()
    intel_md_path = tmp_path / "intelligence_report.md"
    market_md_path = tmp_path / "market_path_report.md"
    intel_md_original = "# Retail Signal\n\n## Signal Map\n\nContent."
    market_md_original = "# Market Path Brief\n\n## Signal Map\n\nMore content."
    intel_md_path.write_text(intel_md_original, encoding="utf-8")
    market_md_path.write_text(market_md_original, encoding="utf-8")
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    manifest = [
        {"type": "hero", "image": "images/hero.png", "prompt": "Hero prompt."},
        {"type": "section", "section": "Signal Map", "image": "images/signal.png", "prompt": "Signal prompt."},
        {"type": "section", "section": "Case Study 1", "image": "images/case1.png", "prompt": "Case prompt."},
    ]
    briefs = {
        "hero": {"alt": "Hero alt", "core_tension": "Hero caption"},
        "signal_map": {"alt": "Signal alt", "structure": "Concentric layout"},
        "case_studies": [{"alt": "Case alt", "scene": "Case scene"}],
    }
    (images_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (images_dir / "briefs.json").write_text(json.dumps(briefs), encoding="utf-8")
    renderer = LegacyHTMLRenderer()
    files = renderer.render(bundle, str(tmp_path))
    assert len(files) == 2
    intel_html_path = Path(tmp_path / "intelligence_report.html")
    market_html = Path(tmp_path / "market_path_report.html")
    assert intel_html_path.exists() and market_html.exists()
    html_output = market_html.read_text(encoding="utf-8")
    assert "Market-Path collaboration brief" in html_output
    assert "Visual Notes" in html_output
    assert "images/hero.png" in html_output
    assert "Signal alt" in html_output
    assert "Window" in html_output
    assert "2024-05-01 → 2024-05-07" in html_output
    assert "<table" not in html_output
    assert "Decision Map" not in html_output
    banned_tokens = [
        "foot_traffic_uplift",
        "early_window_share",
        "buyer_activity_share",
        "event_cpa",
        "qr_redemption",
        "-> tracks",
        "-> Mandate",
        "| base |",
        "| stretch |",
        "behavioral signal:",
        "Signal:",
    ]
    for token in banned_tokens:
        assert token not in html_output
    intel_html_output = intel_html_path.read_text(encoding="utf-8")
    for token in banned_tokens:
        assert token not in intel_html_output
    assert intel_md_path.read_text(encoding="utf-8") == intel_md_original
    assert market_md_path.read_text(encoding="utf-8") == market_md_original
    stats_path = tmp_path / "visual_stats.json"
    assert stats_path.exists()
    stats_payload = json.loads(stats_path.read_text(encoding="utf-8"))
    assert "signal_map" in stats_payload.get("anchors_with_images", [])
    assert stats_payload.get("required_anchors") == ["signal_map"]
    manifest = json.loads((tmp_path / "images" / "manifest.json").read_text(encoding="utf-8"))
    new_entries = [entry for entry in manifest if "template_version" in entry]
    if new_entries:
        assert all(entry.get("template_version") == TEMPLATE_VERSION for entry in new_entries)


def test_html_renderer_renders_gallery_with_single_section_image(tmp_path):
    bundle = sample_report_bundle()
    intel_md_path = tmp_path / "intelligence_report.md"
    intel_md_path.write_text("# Retail Signal\n\n## Signal Map\n\nContent.\n\n### Case Moves\n\nBody text.", encoding="utf-8")
    market_md_path = tmp_path / "market_path_report.md"
    market_md_path.write_text("# Market Path\n\n## Signal Map\n\nContent.", encoding="utf-8")
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    manifest = [
        {"type": "hero", "image": "images/hero.png", "prompt": "Hero prompt."},
        {"type": "section", "section": "Signal Map", "image": "images/signal.png", "prompt": "Signal prompt."},
        {"type": "section", "section": "Case Study 1", "image": "images/case1.png", "prompt": "Case prompt."},
    ]
    briefs = {
        "hero": {"alt": "Hero alt", "core_tension": "Hero caption"},
        "signal_map": {"alt": "Signal alt", "structure": "Concentric layout"},
        "case_studies": [{"alt": "Case alt", "scene": "Case scene"}],
    }
    (images_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (images_dir / "briefs.json").write_text(json.dumps(briefs), encoding="utf-8")
    renderer = LegacyHTMLRenderer()
    renderer.render(bundle, str(tmp_path))
    intel_html = Path(tmp_path / "intelligence_report.html").read_text(encoding="utf-8")
    assert "Visual Notes" in intel_html
    assert "images/case1.png" in intel_html


def test_html_renderer_inlines_figures_for_anchors(tmp_path):
    bundle = sample_report_bundle()
    intel_md_path = tmp_path / "intelligence_report.md"
    intel_md_path.write_text(
        "# Retail Signal\n\nIntro paragraph.\n\n## Signal Map\n\n<!-- image:signal_map -->\n\n"
        "## Case Work\n\n### Flagship content sessions that drive footfall and assets\n"
        "<!-- image:case_study_1 -->\n\nClosing thoughts.",
        encoding="utf-8",
    )
    market_md_path = tmp_path / "market_path_report.md"
    market_md_path.write_text("# Market Path\n\n## Signal Map\n\nContent.", encoding="utf-8")
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    manifest = [
        {"type": "hero", "image": "images/hero.png", "prompt": "Hero prompt."},
        {"type": "section", "section": "Signal Map", "image": "images/signal.png", "prompt": "Signal prompt."},
        {"type": "section", "section": "Case Study 1", "image": "images/case1.png", "prompt": "Case prompt."},
    ]
    briefs = {
        "hero": {"alt": "Hero alt", "core_tension": "Hero caption"},
        "signal_map": {"alt": "Signal alt", "structure": "Concentric layout", "metric_focus": ["footfall_lift"]},
        "case_studies": [
            {
                "alt": "Case alt",
                "scene": "Case scene",
                "anchor_section": "mini_case_story",
                "metric_focus": ["event_cpa"],
            }
        ],
    }
    (images_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (images_dir / "briefs.json").write_text(json.dumps(briefs), encoding="utf-8")
    renderer = LegacyHTMLRenderer()
    renderer.render(bundle, str(tmp_path))
    intel_html = Path(tmp_path / "intelligence_report.html").read_text(encoding="utf-8")
    assert "inline-visual" in intel_html
    assert "images/signal.png" in intel_html
    assert "images/case1.png" in intel_html
    assert "Visual Notes" not in intel_html
    assert "Foot-traffic uplift" in intel_html
    assert "Focus: Foot-traffic uplift" in intel_html
    assert "Signal Map" in intel_html


def test_market_path_context_includes_typst_visuals(tmp_path):
    bundle = sample_report_bundle()
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    manifest = [
        {"type": "hero", "image": "images/hero.png", "prompt": "Hero prompt."},
        {"type": "section", "section": "Signal Map", "image": "images/signal.png", "prompt": "Signal prompt."},
        {"type": "section", "section": "Case Study 1", "image": "images/case1.png", "prompt": "Case prompt."},
    ]
    briefs = {
        "hero": {"alt": "Hero alt", "core_tension": "Hero caption", "anchor_section": "header"},
        "signal_map": {
            "alt": "Signal alt",
            "structure": "Concentric layout",
            "metric_focus": ["footfall_lift"],
            "anchor_section": "signals_and_thesis",
        },
        "case_studies": [
            {
                "alt": "Case alt",
                "scene": "Case scene",
                "anchor_section": "mini_case_story",
                "metric_focus": ["event_cpa"],
            }
        ],
    }
    (images_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (images_dir / "briefs.json").write_text(json.dumps(briefs), encoding="utf-8")
    context = build_market_path_context(bundle, report_dir=str(tmp_path))
    visuals = context.get("typst_visuals", {})
    assert "signals_and_thesis" in visuals
    assert "Foot-traffic uplift" in visuals["signals_and_thesis"]
    assert "image(" in visuals["signals_and_thesis"]


def test_visual_lint_passes_when_all_required_slots_render(tmp_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    manifest = [
        {"type": "section", "section": "Signal Map", "image": "images/signal.png", "prompt": "Signal prompt."},
    ]
    briefs = {
        "signal_map": {"alt": "Signal alt", "structure": "Concentric layout", "metric_focus": ["footfall_lift"]},
        "case_studies": [],
    }
    (images_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (images_dir / "briefs.json").write_text(json.dumps(briefs), encoding="utf-8")
    converter = HTMLConverterAgent()
    images = converter.build_image_context(str(tmp_path), {})
    markdown_text = "# Report\n\n## Signal Map\n\n<!-- image:signal_map -->"
    converter.convert_markdown_article(markdown_text, title="Test", metadata={}, images=images)
    stats = converter.last_visual_stats
    assert stats["anchors_with_images"] == ["signal_map"]
    assert lint_visual_stats(stats) == []


def test_legacy_renderer_fails_without_signal_map_visual(tmp_path):
    bundle = sample_report_bundle()
    intel_md_path = tmp_path / "intelligence_report.md"
    intel_md_path.write_text("# Retail Signal\n\nContent without signal map.", encoding="utf-8")
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    manifest = [
        {"type": "hero", "image": "images/hero.png", "prompt": "Hero prompt."},
    ]
    briefs = {"hero": {"alt": "Hero alt", "core_tension": "Hero caption"}}
    (images_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (images_dir / "briefs.json").write_text(json.dumps(briefs), encoding="utf-8")
    renderer = LegacyHTMLRenderer()
    with pytest.raises(RuntimeError):
        renderer.render(bundle, str(tmp_path))


def _visual_qc_path() -> Path:
    return Path(__file__).resolve().parents[1] / "visual_qc.py"


def _visual_template_audit_path() -> Path:
    return Path(__file__).resolve().parents[1] / "visual_template_audit.py"


def test_visual_qc_cli_pass(tmp_path):
    stats = {
        "anchors_found": ["signal_map"],
        "anchors_with_images": ["signal_map"],
        "anchors_missing_images": [],
        "images_without_anchor": [],
        "gallery_size": 0,
        "required_anchors": ["signal_map"],
    }
    (tmp_path / "visual_stats.json").write_text(json.dumps(stats), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(_visual_qc_path()), str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "Visual QA OK" in result.stdout


def test_visual_qc_cli_errors(tmp_path):
    stats = {
        "anchors_found": [],
        "anchors_with_images": [],
        "anchors_missing_images": [],
        "images_without_anchor": [],
        "gallery_size": 0,
        "required_anchors": ["signal_map"],
    }
    (tmp_path / "visual_stats.json").write_text(json.dumps(stats), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(_visual_qc_path()), str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "ERROR" in result.stdout


def test_visual_template_audit_cli(tmp_path):
    bundle = sample_report_bundle()
    intel_md_path = tmp_path / "intelligence_report.md"
    intel_md_path.write_text("# Retail Signal\n\n## Signal Map\n\nContent.", encoding="utf-8")
    (tmp_path / "images").mkdir()
    manifest = [
        {
            "type": "hero",
            "slot": "hero",
            "anchor_section": "header",
            "template": "hero_decision_window",
            "template_version": TEMPLATE_VERSION,
            "context": {},
            "metric_focus": [],
            "alt": "Hero alt",
            "image": "images/hero.png",
        }
    ]
    (tmp_path / "images" / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    ok = subprocess.run(
        [sys.executable, str(_visual_template_audit_path()), str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert ok.returncode == 0
    manifest[0]["template_version"] = "old"
    (tmp_path / "images" / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    bad = subprocess.run(
        [sys.executable, str(_visual_template_audit_path()), str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert bad.returncode == 1
    assert "ERROR" in bad.stdout


def test_market_path_context_uses_metric_spec():
    bundle = sample_report_bundle()
    context = build_market_path_context(bundle)
    anchors = context["measurement"].get("anchors")
    assert anchors
    assert anchors[0]["metric"] == "Local Flagship Footfall"
    assert "10" in anchors[0]["value"]


def test_market_path_context_directional_evidence_line():
    bundle = sample_report_bundle()
    bundle["evidence_note"] = "Evidence leans on coverage."
    bundle["evidence_regime"] = "directional"
    context = build_market_path_context(bundle)
    assert context["narrative"].get("evidence_line", "") == "Treat this as a directional read."
    bundle["evidence_regime"] = "healthy"
    context = build_market_path_context(bundle)
    evidence_line = context["narrative"].get("evidence_line", "")
    assert evidence_line == ""


def test_spec_notes_stored_outside_public_copy():
    bundle = sample_report_bundle()
    bundle["spec_notes"] = ["key_metric event_cpa missing from metric_spec"]
    context = build_market_path_context(bundle)
    assert "Spec still" not in context["narrative"].get("standfirst", "")
    assert "key_metric event_cpa" in context.get("spec_note", "")


def test_spec_version_guard():
    bundle = sample_report_bundle()
    bundle["spec_version"] = "v2"
    with pytest.raises(ValueError):
        build_market_path_context(bundle)


def test_context_exposes_spec_ok_flag():
    bundle = sample_report_bundle()
    context = build_market_path_context(bundle)
    assert context.get("spec_ok") is True


def test_agent_strips_arrow_scaffolding():
    agent = EnhancedSTIAgent("test")
    messy = "Headline -> tracks early_window_share -> Mandate instrumentation"
    cleaned = agent._strip_headings(messy)
    assert "->" not in cleaned


def test_pilot_spec_coherence_flags_unknown_roles():
    agent = EnhancedSTIAgent("test")
    pilot_spec = {
        "store_count": 1,
        "duration_weeks": 4,
        "owner_roles": ["Head of Retail", "Finance"],
        "key_metrics": ["event_cpa"],
    }
    metric_spec = {
        "event_cpa": {
            "label": "Event CPA",
            "target_range": [0, 0.8],
            "unit": "× baseline",
            "stage": "guardrail",
            "owner": "Finance",
            "target_text": "≤0.80× baseline",
            "notes": "guardrail",
        }
    }
    role_actions = {"Chief of Staff": "Run the pilot"}
    issues = agent._pilot_spec_coherence(pilot_spec, metric_spec, role_actions)
    assert any("role_action Chief of Staff" in issue for issue in issues)


def test_agent_markdown_rewrites_schema_tokens():
    agent = EnhancedSTIAgent("test")
    bundle = sample_report_bundle()
    quant = bundle["quant"]
    signals = [
        {
            "id": "S1",
            "category": "Market",
            "name": "Signal name",
            "description": "foot_traffic_uplift replaces blunt discounts.",
            "operator_move": "Do the pilot",
            "operator_scan": "Watch early_window_share",
            "time_horizon": "now",
            "citations": [1],
            "on_spine": True,
        }
    ]
    sections = {
        "deep_analysis": {
            "sections": [
                {
                    "title": "Systems",
                    "scan_line": "foot_traffic_uplift beats blanket",
                    "insight": "event_cpa guardrails keep the win real.",
                    "operator_note": "Guardrail event_cpa",
                    "instrument_next": "Log foot_traffic_uplift vs event_cpa",
                }
            ]
        },
        "pattern_matches": [],
        "brand_outcomes": [],
        "activation_kit": [],
    }
    sources = [
        SourceRecord(
            id=1,
            title="Source",
            url="https://example.com",
            publisher="Example",
            date="2024-01-01",
            snippet="Snippet",
            content="Content",
            credibility=0.8,
        )
    ]
    banned_tokens = [
        "foot_traffic_uplift",
        "early_window_share",
        "event_cpa",
        "-> tracks",
        "-> Mandate",
        "behavioral signal:",
    ]
    banned_tokens.extend(sorted(known_metric_ids()))
    markdown = agent._build_markdown(
        query=bundle["query"],
        title=bundle["title"],
        exec_summary=bundle["executive_summary"],
        highlights=bundle["highlights"],
        top_moves=bundle["top_operator_moves"],
        play_summary=bundle["play_summary"],
        fast_path=bundle["fast_path"],
        fast_stack=bundle["fast_stack"],
        spine=bundle["spine"],
        signals=signals,
        sections=sections,
        sources=sources,
        quant_payload=quant,
        appendix=[],
        pilot_spec=bundle["pilot_spec"],
        metric_spec=bundle["metric_spec"],
        role_actions=bundle["role_actions"],
    )
    measurement_slice = ""
    if "## Measurement Spine" in markdown:
        measurement_slice = markdown.split("## Measurement Spine", 1)[1]
        if "## Deep Analysis" in measurement_slice:
            measurement_slice = measurement_slice.split("## Deep Analysis", 1)[0]
    deep_slice = ""
    if "## Deep Analysis" in markdown:
        deep_slice = markdown.split("## Deep Analysis", 1)[1]
        if "## Pattern Matches" in deep_slice:
            deep_slice = deep_slice.split("## Pattern Matches", 1)[0]
    for token in banned_tokens:
        assert token not in measurement_slice
        assert token not in deep_slice

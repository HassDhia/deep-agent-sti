import json
import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("STI_DETERMINISTIC", "1")

import enhanced_mcp_agent as agent_mod
from enhanced_mcp_agent import EnhancedSTIAgent, SourceRecord


def _json(payload):
    return json.dumps(payload, ensure_ascii=False)


@pytest.fixture
def stub_agent(monkeypatch):
    class StubAgent(EnhancedSTIAgent):
        def __init__(self) -> None:
            super().__init__("test-key")

        def _build_scope(self, query: str, days_back: int):
            return {
                "query": query,
                "time_window": {"days": days_back},
                "window_label": "Nov 01 – Nov 07",
                "unified_target_pack": {"foot_traffic_uplift": {"goal": "+10%"}},
                "approach_hints": ["comparison move"],
                "search_shaped_variants": ["how to run pilots"],
            }

        def _collect_sources(self, query: str, days_back: int, scope: dict):
            sources = []
            for idx in range(1, 7):
                sources.append(
                    SourceRecord(
                        id=idx,
                        title=f"Retail shift {idx}",
                        url=f"https://example.com/retail/{idx}",
                        publisher="Retail Dive",
                        date="2024-05-05",
                        snippet=f"Retailers test new plays {idx}",
                        content="Retailers test new plays with measurable lift.",
                        credibility=0.8,
                    )
                )
            return sources

    def fake_signal_map(*_args, **_kwargs):
        return _json(
            {
                "signals": [
                    {
                        "id": "S1",
                        "category": "Market",
                        "name": "Drop mechanics",
                        "description": "Operators borrow drop logic.",
                        "operator_move": "Test the play.",
                        "operator_scan": "Watch foot traffic",
                        "spine_hook": "Operators run scarcity windows",
                        "time_horizon": "now",
                        "citations": [1],
                        "strength": 0.9,
                        "US_fit": 0.9,
                        "on_spine": True,
                    }
                ],
                "appendix": [],
                "operator_job_story": "How to grow value without burning promo cash.",
                "search_shaped_variants": ["how to grow value"],
            }
        )

    def fake_quant(*_args, **_kwargs):
        return _json(
            {
                "spine_hook": "Guardrails keep the win real.",
                "anchors": [
                    {
                        "headline": "Foot traffic uplift",
                        "topic": "foot_traffic",
                        "value_low": 10,
                        "value_high": 15,
                        "unit": "%",
                        "status": "target",
                        "band": "base",
                        "owner": "Analytics",
                        "expression": "Foot traffic between 10 and 15%",
                        "source_ids": [1],
                        "applies_to_signals": ["S1"],
                    }
                ],
                "measurement_plan": [
                    {
                        "metric": "Foot traffic uplift",
                        "expression": "Track uplift vs baseline",
                        "owner": "Analytics",
                        "timeframe": "Two-week window",
                        "why_it_matters": "Shows real demand",
                    }
                ],
            }
        )

    def fake_exec_summary(*_args, **_kwargs):
        return _json(
            {
                "executive_summary": "Operators are compressing demand into precise windows.",
                "highlights": ["Signals show scarcity works."],
                "top_operator_moves": ["Stand up the drop test."],
                "hook_line": "Scarcity windows defend margin.",
                "fast_path": {"sections": ["executive_summary", "highlights", "top_operator_moves"]},
                "fast_stack": {
                    "headline": "Demand compresses",
                    "why_now": "Operators see holiday shifts",
                    "next_30_days": "Lock the pilot",
                },
                "play_summary": [],
            }
        )

    def fake_image_briefs(*_args, **_kwargs):
        return _json({"image_briefs": {}})

    def fake_operator_specs(*_args, **_kwargs):
        return _json(
            {
                "pilot_spec": {"store_count": 2, "duration_weeks": 4, "owner_roles": ["Head of Retail", "Finance"]},
                "metric_spec": {"foot_traffic_uplift": {"label": "Foot traffic uplift", "target_text": "+10%"}},
                "role_actions": {"Head of Retail": "Run the pilot"},
            }
        )

    def fake_deep_analysis(*_args, **_kwargs):
        return _json(
            {
                "deep_analysis": {
                    "sections": [
                        {
                            "title": "Systems shift",
                            "spine_position": "what",
                            "priority": 1,
                            "scan_line": "Drop math goes retail",
                            "insight": "Operators see real lift.",
                            "operator_note": "Instrument the pilot.",
                            "instrument_next": "Instrument foot_traffic_uplift",
                            "citations": [1],
                        }
                    ],
                    "summary": "Operators are shifting to drop cadence.",
                }
            }
        )

    def fake_simple_list(key):
        return _json({key: []})

    monkeypatch.setattr(agent_mod, "generate_signal_map", fake_signal_map)
    monkeypatch.setattr(agent_mod, "generate_quant_blocks", fake_quant)
    monkeypatch.setattr(agent_mod, "write_executive_summary", fake_exec_summary)
    monkeypatch.setattr(agent_mod, "generate_image_briefs", fake_image_briefs)
    monkeypatch.setattr(agent_mod, "generate_operator_specs", fake_operator_specs)
    monkeypatch.setattr(agent_mod, "generate_deep_analysis", fake_deep_analysis)
    monkeypatch.setattr(agent_mod, "generate_pattern_matches", lambda *a, **k: fake_simple_list("pattern_matches"))
    monkeypatch.setattr(agent_mod, "generate_brand_outcomes", lambda *a, **k: fake_simple_list("brand_outcomes"))
    monkeypatch.setattr(agent_mod, "generate_activation_kit", lambda *a, **k: fake_simple_list("activation_kit"))
    monkeypatch.setattr(agent_mod, "generate_risk_radar", lambda *a, **k: fake_simple_list("risk_radar"))
    monkeypatch.setattr(agent_mod, "generate_future_outlook", lambda *a, **k: fake_simple_list("future_outlook"))
    monkeypatch.setattr(agent_mod, "generate_comparison_map", lambda *a, **k: _json({"approach_map": []}))
    monkeypatch.setattr(agent_mod, "generate_image_prompt_bundle", lambda *a, **k: _json({"images": []}))
    monkeypatch.setattr(EnhancedSTIAgent, "_evidence_regime", lambda self, stats: "healthy")

    return StubAgent()


def test_generate_report_survives_quant_contract_failure(stub_agent, monkeypatch):
    monkeypatch.setattr(agent_mod, "lint_quant_blocks", lambda *_args, **_kwargs: ["quant error"])
    report = stub_agent.generate_report("retail collabs")
    assert report["contract_status"]["quant"] == "invalid_fallback"
    assert report["executive_letter_markdown"]


def test_generate_report_repairs_operator_specs(stub_agent, monkeypatch):
    monkeypatch.setattr(agent_mod, "lint_operator_specs", lambda *_args, **_kwargs: ["owner_roles invalid"])
    report = stub_agent.generate_report("retail collabs")
    assert report["contract_status"]["operator_specs"] == "invalid_repaired"
    assert report["executive_letter_markdown"]


def test_starved_regime_returns_minimal_bundle(stub_agent, monkeypatch):
    monkeypatch.setattr(EnhancedSTIAgent, "_evidence_regime", lambda self, stats: "starved")
    report = stub_agent.generate_report("retail collabs")
    assert report["letter_status"] == "fallback_starved"
    assert report["signals"] == []
    assert report["contract_status"]["evidence_regime"] == "starved"

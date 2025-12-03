import os

os.environ.setdefault("OPENAI_API_KEY", "test-key")

from enhanced_mcp_agent import EnhancedSTIAgent


def test_window_label_formatting():
    agent = EnhancedSTIAgent(openai_api_key="test-key")
    window = {"start": "2025-11-24", "end": "2025-12-01"}
    label = agent._window_label(window)
    assert label == "Nov 24 – Dec 01, 2025"


def test_apply_window_label_overrides_pilot_window():
    agent = EnhancedSTIAgent(openai_api_key="test-key")
    bundle = {"pilot_spec": {"window": "Nov24-Dec01_2025_early_window"}}
    agent._apply_window_label(bundle, "Nov 24 – Dec 01, 2025")
    assert bundle["pilot_spec"]["window"] == "Nov 24 – Dec 01, 2025"
    assert bundle["pilot_spec"]["window_label"] == "Nov 24 – Dec 01, 2025"

from analysis_contracts import lint_quant_blocks
from quant_normalization import normalize_quant_blocks_payload


def _valid_quant_payload():
    return {
        "spine_hook": "How we know the plan is working.",
        "anchors": [
            {
                "id": "Q1",
                "headline": "Early-window share holds 20-30%",
                "topic": "Buyer mix",
                "value_low": 20.0,
                "value_high": 30.0,
                "unit": "%",
                "status": "target",
                "band": "base",
                "owner": "Analytics",
                "expression": "Daily buyer share between 20 and 30 percent",
                "source_ids": [1, 2],
                "applies_to_signals": ["S1", "S2"],
            }
        ],
        "measurement_plan": [
            {
                "id": "M1",
                "metric": "Buyer share vs promo intensity",
                "expression": "Track early-window share alongside promo depth",
                "owner": "Analytics",
                "timeframe": "Nov 24 – Dec 01",
                "status": "plan",
                "why_it_matters": "Shows whether we moved demand without deeper promos.",
            }
        ],
        "coverage": 0.75,
    }


def test_lint_quant_blocks_accepts_valid_payload():
    payload = _valid_quant_payload()
    assert lint_quant_blocks(payload) == []


def test_lint_quant_blocks_flags_placeholder_text():
    payload = _valid_quant_payload()
    payload["anchors"][0]["headline"] = "Plain-English label"
    errors = lint_quant_blocks(payload)
    assert any("placeholder" in err for err in errors)


def test_lint_quant_blocks_flags_snake_case_leak():
    payload = _valid_quant_payload()
    payload["anchors"][0]["headline"] = "early_window_share spike"
    errors = lint_quant_blocks(payload)
    assert any("snake_case" in err for err in errors)


def test_normalize_quant_blocks_rewrites_metric_ids():
    payload = _valid_quant_payload()
    payload["anchors"][0]["topic"] = "early_window_share"
    payload["anchors"][0]["expression"] = "Keep purchase_date aligned with early_window_share"
    payload["measurement_plan"][0]["metric"] = "event_cpa"
    normalized = normalize_quant_blocks_payload(payload)
    errors = lint_quant_blocks(normalized)
    assert all("snake_case" not in err for err in errors)
    assert "early_window_share" not in normalized["anchors"][0]["topic"]
    assert "event_cpa" not in normalized["measurement_plan"][0]["metric"]


def test_lint_quant_blocks_allows_snake_case_in_structural_fields():
    payload = _valid_quant_payload()
    payload["anchors"][0]["applies_to_signals"] = ["early_window_share", "buyer_activity"]
    errors = lint_quant_blocks(payload)
    assert not any("applies_to_signals" in err for err in errors)

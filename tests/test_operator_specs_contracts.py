from analysis_contracts import lint_operator_specs
from operator_specs_normalization import normalize_operator_specs


def _valid_operator_specs_payload():
    return {
        "pilot_spec": {
            "scenario": "holiday_early_window_pilot",
            "store_count": 4,
            "store_type": "flagship",
            "duration_weeks": 2,
            "window": "Nov 24 – Dec 01, 2025",
            "primary_move": "Shift demand into the early window without deeper promos.",
            "owner_roles": ["Head of Retail", "Head of Partnerships", "Finance"],
            "key_metrics": ["early_window_share", "event_cpa"],
        },
        "metric_spec": {
            "early_window_share": {
                "label": "Early-window buyer share",
                "target_range": [20.0, 30.0],
                "unit": "%",
                "stage": "target",
                "owner": "Analytics",
                "target_text": "Keep early-window buyers between 20 and 30 percent of holiday buyers.",
            },
            "event_cpa": {
                "label": "Event CPA vs baseline",
                "target_range": [0.0, 0.8],
                "unit": "x baseline",
                "stage": "guardrail",
                "owner": "Performance marketing",
                "target_text": "Hold event CPA at or below 0.80× baseline.",
            },
        },
        "role_actions": {
            "Head of Retail": ["Run the four-store pilot and confirm POS and staffing guardrails."],
            "Head of Partnerships": ["Lock one collaborator per store and align on shared QR flows."],
            "Finance": ["Approve spend contingent on event CPA staying within guardrails."],
        },
    }


def test_lint_operator_specs_accepts_valid_payload():
    payload = _valid_operator_specs_payload()
    assert lint_operator_specs(payload) == []


def test_lint_operator_specs_flags_missing_metric_for_key_metric():
    payload = _valid_operator_specs_payload()
    payload["metric_spec"].pop("event_cpa")
    errors = lint_operator_specs(payload)
    assert any("event_cpa" in err for err in errors)


def test_normalized_target_text_stays_clean():
    payload = _valid_operator_specs_payload()
    payload["metric_spec"]["early_window_share"]["target_text"] = "Track early_window_share tightly."
    normalized = normalize_operator_specs(payload)
    assert "early_window_share" not in normalized["metric_spec"]["early_window_share"]["target_text"]


def test_normalizer_converts_single_numeric_target_range_to_pair():
    payload = _valid_operator_specs_payload()
    payload["metric_spec"]["event_cpa"]["target_range"] = 0.8
    normalized = normalize_operator_specs(payload)
    assert normalized["metric_spec"]["event_cpa"]["target_range"] == [0.8, 0.8]
    assert lint_operator_specs(normalized) == []


def test_normalizer_converts_string_target_range_to_pair():
    payload = _valid_operator_specs_payload()
    payload["metric_spec"]["early_window_share"]["target_range"] = "20"
    normalized = normalize_operator_specs(payload)
    assert normalized["metric_spec"]["early_window_share"]["target_range"] == [20.0, 20.0]
    assert lint_operator_specs(normalized) == []


def test_linter_still_flags_non_numeric_target_range():
    payload = _valid_operator_specs_payload()
    payload["metric_spec"]["early_window_share"]["target_range"] = "keep flat"
    normalized = normalize_operator_specs(payload)
    errors = lint_operator_specs(normalized)
    assert any("target_range must be a numeric [low, high] list" in err for err in errors)


def test_normalizer_wraps_role_actions_string_into_list():
    payload = _valid_operator_specs_payload()
    payload["role_actions"]["Head of Retail"] = "Run the pilot and report foot traffic."
    normalized = normalize_operator_specs(payload)
    assert normalized["role_actions"]["Head of Retail"] == ["Run the pilot and report foot traffic."]
    assert lint_operator_specs(normalized) == []


def test_lint_operator_specs_ignores_snake_case_in_store_type():
    payload = _valid_operator_specs_payload()
    payload["pilot_spec"]["store_type"] = "flagship_community"
    errors = lint_operator_specs(payload)
    assert not any("store_type" in err for err in errors)

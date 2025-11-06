from gates import value_of_information


def test_value_of_information_triggers_expected_tasks():
    metrics = {"anchor_coverage": 0.6, "quant_flags": 2, "confidence": 0.6}
    tasks = value_of_information(metrics, "theory")
    assert "evidence_alignment" in tasks
    assert "math_guard" in tasks
    assert "adversarial_review" in tasks
    assert "decision_playbooks" in tasks


def test_value_of_information_market_path():
    metrics = {"anchor_coverage": 0.85, "quant_flags": 0, "confidence": 0.8}
    tasks = value_of_information(metrics, "market")
    assert tasks == []


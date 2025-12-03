from confidence import ConfidenceBreakdown, headline


def test_headline_balances_metrics():
    breakdown = ConfidenceBreakdown(
        average_strength=0.82,
        coverage=0.75,
        quant_support=0.5,
        contradiction_penalty=0.9,
    )
    assert headline(breakdown) == round(
        0.4 * 0.82 + 0.3 * 0.75 + 0.2 * 0.5 + 0.1 * 0.9, 3
    )


def test_clamps_values():
    breakdown = ConfidenceBreakdown(
        average_strength=1.4,
        coverage=-0.2,
        quant_support=0.25,
        contradiction_penalty=1.2,
    )
    score = headline(breakdown)
    assert 0.0 <= score <= 1.0

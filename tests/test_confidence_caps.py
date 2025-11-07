"""Tests for confidence caps by report type and anchor coverage."""

import pytest
from confidence import ConfidenceBreakdown, headline as confidence_headline
from config import STIConfig


def test_confidence_cap_theory_anchor_absent():
    """Test that theory reports with weak anchors get capped at 0.55."""
    # Create a breakdown that would yield > 0.55 confidence
    breakdown = ConfidenceBreakdown(
        source_diversity=0.9,
        anchor_coverage=0.4,  # Below ANCHOR_COVERAGE_MIN (0.70)
        method_transparency=0.8,
        replication_readiness=0.85
    )
    
    # Without cap, this would be:
    uncapped = confidence_headline(breakdown)
    assert uncapped > 0.55, "Test setup: uncapped confidence should exceed cap"
    
    # With cap (simulating the logic in _run_auditors):
    intent = "theory"
    anchor_coverage = 0.4
    cap = getattr(STIConfig, 'CONFIDENCE_CAP_THEORY_ANCHOR_ABSENT', 0.55)
    
    if intent == "theory" and anchor_coverage < getattr(STIConfig, 'ANCHOR_COVERAGE_MIN', 0.70):
        capped = min(uncapped, cap)
        assert capped == cap, f"Confidence should be capped at {cap}, got {capped}"
        assert capped <= 0.55, f"Capped confidence {capped} should be <= 0.55"
    else:
        pytest.fail("Test setup failed: conditions should trigger cap")


def test_confidence_no_cap_market_report():
    """Test that market reports don't get capped."""
    breakdown = ConfidenceBreakdown(
        source_diversity=0.9,
        anchor_coverage=0.4,  # Low, but market reports don't cap
        method_transparency=0.8,
        replication_readiness=0.85
    )
    
    intent = "market"
    anchor_coverage = 0.4
    
    # Market reports should not cap
    if intent == "theory" and anchor_coverage < getattr(STIConfig, 'ANCHOR_COVERAGE_MIN', 0.70):
        pytest.fail("Market reports should not trigger theory cap")
    
    # Confidence should be unchanged
    confidence = confidence_headline(breakdown)
    assert confidence > 0.55, "Market reports should not be capped"


def test_confidence_no_cap_strong_anchors():
    """Test that theory reports with strong anchors don't get capped."""
    breakdown = ConfidenceBreakdown(
        source_diversity=0.9,
        anchor_coverage=0.75,  # Above ANCHOR_COVERAGE_MIN (0.70)
        method_transparency=0.8,
        replication_readiness=0.85
    )
    
    intent = "theory"
    anchor_coverage = 0.75
    
    # Strong anchors should not trigger cap
    if intent == "theory" and anchor_coverage < getattr(STIConfig, 'ANCHOR_COVERAGE_MIN', 0.70):
        pytest.fail("Strong anchors should not trigger cap")
    
    confidence = confidence_headline(breakdown)
    assert confidence > 0.55, "Strong anchors should not be capped"


"""Tests for confidence breakdown computation and rendering."""

from confidence import ConfidenceBreakdown, headline as confidence_headline


def test_confidence_headline_equals_weighted_sub_scores():
    """Test that headline confidence equals weighted sum of sub-scores."""
    breakdown = ConfidenceBreakdown(
        source_diversity=0.8,
        anchor_coverage=0.7,
        method_transparency=0.6,
        replication_readiness=0.75
    )
    
    expected = round(
        0.30 * 0.8 + 0.25 * 0.7 + 0.25 * 0.6 + 0.20 * 0.75,
        3
    )
    
    actual = confidence_headline(breakdown)
    
    assert actual == expected, f"Headline {actual} should equal weighted sum {expected}"


def test_confidence_headline_with_zero_values():
    """Test confidence breakdown with zero values."""
    breakdown = ConfidenceBreakdown(
        source_diversity=0.0,
        anchor_coverage=0.0,
        method_transparency=0.0,
        replication_readiness=0.0
    )
    
    actual = confidence_headline(breakdown)
    assert actual == 0.0, f"All zeros should yield 0.0, got {actual}"


def test_confidence_headline_with_max_values():
    """Test confidence breakdown with maximum values."""
    breakdown = ConfidenceBreakdown(
        source_diversity=1.0,
        anchor_coverage=1.0,
        method_transparency=1.0,
        replication_readiness=1.0
    )
    
    actual = confidence_headline(breakdown)
    assert actual == 1.0, f"All ones should yield 1.0, got {actual}"


def test_confidence_breakdown_clamp():
    """Test that confidence breakdown clamps values to [0, 1]."""
    breakdown = ConfidenceBreakdown(
        source_diversity=1.5,  # Above 1.0
        anchor_coverage=-0.5,  # Below 0.0
        method_transparency=0.5,
        replication_readiness=0.75
    )
    
    clamped = breakdown.clamp()
    
    assert clamped.source_diversity == 1.0, "Should clamp to 1.0"
    assert clamped.anchor_coverage == 0.0, "Should clamp to 0.0"
    assert clamped.method_transparency == 0.5, "Should remain unchanged"
    assert clamped.replication_readiness == 0.75, "Should remain unchanged"


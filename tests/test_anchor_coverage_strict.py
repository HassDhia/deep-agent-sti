"""Tests for strict anchor coverage computation."""

import pytest
from servers.anchors import EvidenceAnchor, _is_strict_anchor, align_claims_to_evidence


def test_strict_anchor_with_doi_and_approved_domain():
    """Test that anchors with DOI and approved domain are marked as strict."""
    anchor = EvidenceAnchor(
        doi="10.1234/example.doi",
        title="Test Paper",
        url="https://ieeexplore.ieee.org/document/12345678"
    )
    assert _is_strict_anchor(anchor) is True


def test_strict_anchor_arxiv_not_strict():
    """Test that arXiv anchors are not marked as strict."""
    anchor = EvidenceAnchor(
        doi="10.1234/example.doi",
        title="Test Paper",
        url="https://arxiv.org/abs/1234.5678"
    )
    assert _is_strict_anchor(anchor) is False


def test_strict_anchor_no_doi():
    """Test that anchors without DOI are not strict."""
    anchor = EvidenceAnchor(
        doi=None,
        title="Test Paper",
        url="https://ieeexplore.ieee.org/document/12345678"
    )
    assert _is_strict_anchor(anchor) is False


def test_anchor_coverage_strict_computation():
    """Test that align_claims_to_evidence computes both any and strict coverage."""
    claims = [
        {"text": "Claim 1", "id": "c1"},
        {"text": "Claim 2", "id": "c2"},
    ]
    
    sources = [
        {
            "url": "https://ieeexplore.ieee.org/document/12345678",
            "title": "IEEE Paper",
            "doi": "10.1109/example.2024.12345678"
        },
        {
            "url": "https://arxiv.org/abs/1234.5678",
            "title": "arXiv Paper",
            "doi": "10.1234/arxiv.1234.5678"
        }
    ]
    
    ledger = align_claims_to_evidence(claims, sources)
    
    assert "anchor_coverage_any" in ledger
    assert "anchor_coverage_strict" in ledger
    assert ledger["anchor_coverage_any"] > 0  # Should have some anchors
    # Strict coverage may be 0 if arXiv anchors don't count
    assert ledger["anchor_coverage_strict"] >= 0
    assert ledger["anchor_coverage_strict"] <= ledger["anchor_coverage_any"]


def test_anchor_coverage_with_only_arxiv():
    """Test that with only arXiv anchors, strict coverage is 0 but any > 0."""
    claims = [
        {"text": "Claim 1", "id": "c1"},
    ]
    
    sources = [
        {
            "url": "https://arxiv.org/abs/1234.5678",
            "title": "arXiv Paper",
            "doi": "10.1234/arxiv.1234.5678"
        }
    ]
    
    ledger = align_claims_to_evidence(claims, sources)
    
    assert ledger["anchor_coverage_any"] > 0
    assert ledger["anchor_coverage_strict"] == 0.0  # arXiv should not count as strict


"""Tests for quant monotonicity linter integration."""

import pytest
from servers.quant import suggest_patch_for_vignette, QuantWarning


def test_monotonicity_warnings_in_patch():
    """Test that monotonicity warnings are included in quant patch."""
    # Normal parameters should not trigger warnings
    params = {
        "TPR": 0.9,
        "FPR": 0.1,
        "base_rate": 0.5,
        "mu": 1.0,
        "alpha": 1.0,
        "tau": 1.0
    }
    
    patch = suggest_patch_for_vignette(params)
    
    # Check that warnings list exists
    assert hasattr(patch, 'warnings')
    assert isinstance(patch.warnings, list)
    
    # With normal parameters, should not have monotonicity warnings
    # (may have other warnings from sanity checks)
    mono_warnings = [w for w in patch.warnings if w.code == "MONOTONICITY"]
    # PPV and Poisson hazard are monotonic, so should not generate warnings
    assert len(mono_warnings) == 0


def test_quant_patch_includes_warnings():
    """Test that quant patch includes warnings from both sanity and monotonicity checks."""
    params = {
        "TPR": 0.9,
        "FPR": 0.1,
        "base_rate": 0.5,
        "mu": 1.0,
        "alpha": 1.0,
        "tau": 1.0,
        "p_conn": 1.0,
        "kappa": 1.0
    }
    
    patch = suggest_patch_for_vignette(params)
    
    # Should have warnings attribute
    assert hasattr(patch, 'warnings')
    # Warnings should be a list of QuantWarning objects
    assert all(isinstance(w, QuantWarning) for w in patch.warnings)


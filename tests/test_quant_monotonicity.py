"""Tests for quant monotonicity linter."""

import pytest
from servers.quant import monotonicity_linter, QuantWarning


def test_monotonicity_increasing():
    """Test that increasing function passes increasing check."""
    def increasing_fn(x, **kwargs):
        return x * 2
    
    warning = monotonicity_linter(
        increasing_fn,
        "x",
        {"x": (0.0, 10.0)},
        "increasing"
    )
    assert warning is None, "Increasing function should pass increasing check"


def test_monotonicity_decreasing():
    """Test that decreasing function passes decreasing check."""
    def decreasing_fn(x, **kwargs):
        return 10.0 - x
    
    warning = monotonicity_linter(
        decreasing_fn,
        "x",
        {"x": (0.0, 10.0)},
        "decreasing"
    )
    assert warning is None, "Decreasing function should pass decreasing check"


def test_monotonicity_u_shaped():
    """Test that U-shaped function passes U-shaped check."""
    def u_shaped_fn(x, **kwargs):
        return (x - 5.0) ** 2
    
    warning = monotonicity_linter(
        u_shaped_fn,
        "x",
        {"x": (0.0, 10.0)},
        "u_shaped"
    )
    assert warning is None, "U-shaped function should pass U-shaped check"


def test_monotonicity_violation():
    """Test that non-monotonic function fails monotonic check."""
    def non_monotonic_fn(x, **kwargs):
        return (x - 5.0) ** 2  # U-shaped, not monotonic
    
    warning = monotonicity_linter(
        non_monotonic_fn,
        "x",
        {"x": (0.0, 10.0)},
        "monotonic"
    )
    assert warning is not None, "Non-monotonic function should fail monotonic check"
    assert warning.code == "MONOTONICITY", "Warning should have MONOTONICITY code"


def test_monotonicity_increasing_violation():
    """Test that non-increasing function fails increasing check."""
    def decreasing_fn(x, **kwargs):
        return 10.0 - x
    
    warning = monotonicity_linter(
        decreasing_fn,
        "x",
        {"x": (0.0, 10.0)},
        "increasing"
    )
    assert warning is not None, "Decreasing function should fail increasing check"
    assert warning.code == "MONOTONICITY", "Warning should have MONOTONICITY code"


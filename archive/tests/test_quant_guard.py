import math

from servers.quant import sanity, ppv, poisson_hazard, suggest_patch_for_vignette


def test_prob_ranges_and_base_rate():
    warnings = sanity({"TPR": 0.9, "FPR": 0.08})
    assert any(w.code == "MISSING" for w in warnings)


def test_ppv_monotonicity():
    assert ppv(0.9, 0.1, 0.5) > ppv(0.9, 0.2, 0.5)


def test_poisson_hazard_bounds():
    probability = poisson_hazard(12.6, 6.0)
    assert math.isclose(probability, max(0.0, min(1.0, probability)))


def test_patch_has_equations_and_example():
    patch = suggest_patch_for_vignette(
        {
            "mu": 120,
            "alpha": 0.7,
            "tau": 0.25,
            "p_conn": 0.6,
            "TPR": 0.9,
            "FPR": 0.08,
            "base_rate": 0.05,
            "p_loss": 0.35,
            "f": 1 / 30,
            "w_k": 0.02,
        }
    )
    assert patch.latex_equations
    assert patch.examples


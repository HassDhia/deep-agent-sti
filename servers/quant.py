"""Math guard utilities for STI vignettes and quantitative sections."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Dict, List


@dataclass
class QuantWarning:
    code: str
    message: str


@dataclass
class QuantPatch:
    latex_equations: List[str]
    examples: List[Dict[str, float]]
    warnings: List[QuantWarning]


def poisson_hazard(rate_per_hour: float, hours: float, m: int = 1) -> float:
    """Probability of ≥ m events within the given horizon."""

    lam_t = max(0.0, rate_per_hour) * max(0.0, hours)
    if m <= 1:
        return 1.0 - math.exp(-lam_t)

    tail = 0.0
    for k in range(m):
        try:
            term = math.exp(-lam_t) * (lam_t**k) / math.factorial(k)
        except OverflowError:
            term = 0.0
        tail += term
    return 1.0 - tail


def ppv(tpr: float, fpr: float, base_rate: float, p_loss: float = 0.0) -> float:
    """Positive predictive value with loss-adjusted TPR."""

    tpr_eff = tpr * (1.0 - p_loss)
    numerator = tpr_eff * base_rate
    denominator = numerator + fpr * (1.0 - base_rate)
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def sanity(params: Dict[str, Any]) -> List[QuantWarning]:
    """Return warnings if quantitative parameters are out of bounds."""

    warnings: List[QuantWarning] = []

    def warn(code: str, message: str) -> None:
        warnings.append(QuantWarning(code=code, message=message))

    for key, value in params.items():
        if any(key.lower().startswith(prefix) for prefix in ("p_", "prob", "tpr", "fpr", "base_rate")):
            try:
                val = float(value)
            except (TypeError, ValueError):
                warn("TYPE", f"{key} must be numeric")
                continue
            if not 0.0 <= val <= 1.0:
                warn("RANGE", f"{key}={val} outside [0, 1]")

    if "mu" in params:
        try:
            if float(params["mu"]) < 0.0:
                warn("RANGE", "mu must be non-negative")
        except (TypeError, ValueError):
            warn("TYPE", "mu must be numeric")

    if ("TPR" in params or "tpr" in params or "FPR" in params or "fpr" in params) and "base_rate" not in params:
        warn("MISSING", "base_rate required when using TPR/FPR")

    return warnings


def suggest_patch_for_vignette(params: Dict[str, Any], horizon_hours: float = 6.0) -> QuantPatch:
    """Return recommended equations and worked example for a vignette."""

    alerts = sanity(params)

    mu = float(params.get("mu", 0.0))
    alpha = float(params.get("alpha", 1.0))
    tau = float(params.get("tau", 1.0))
    p_conn = float(params.get("p_conn", 1.0))
    kappa = float(params.get("kappa", 1.0))
    lam = mu * alpha * tau * p_conn * kappa
    p_fail = poisson_hazard(lam, horizon_hours, m=int(params.get("m", 1)))

    tpr = float(params.get("TPR") or params.get("tpr", 0.0))
    fpr = float(params.get("FPR") or params.get("fpr", 0.0))
    base_rate = float(params.get("base_rate", 0.0))
    p_loss = float(params.get("p_loss", 0.0))
    f_reports_per_sec = float(params.get("f", 1 / 30))
    w_k = float(params.get("w_k", 0.0))

    precision = ppv(tpr, fpr, base_rate, p_loss=p_loss)
    reports_per_hr = f_reports_per_sec * 3600.0
    noise_mass = max(0.0, (1.0 - precision) * reports_per_hr)
    lam_false = noise_mass * w_k
    p_false_kinetic = 1.0 - math.exp(-lam_false)

    latex_equations = [
        r"\lambda = \mu \cdot \alpha \cdot \tau \cdot p_{\text{conn}} \cdot \kappa",
        r"P_{\text{fail}}(T; m) = 1 - \sum_{k=0}^{m-1} e^{-\lambda T} \frac{(\lambda T)^k}{k!}",
        r"\text{PPV} = \frac{\text{TPR}(1-p_{\text{loss}})\pi}{\text{TPR}(1-p_{\text{loss}})\pi + \text{FPR}(1-\pi)}",
        r"\lambda_{\text{false-kinetic}} = (1-\text{PPV}) f 3600 w_k",
        r"P_{\text{false-kinetic}} = 1 - e^{-\lambda_{\text{false-kinetic}}}",
    ]

    example = {
        "lambda_per_hr": round(lam, 6),
        "p_fail_T": round(p_fail, 6),
        "ppv": round(precision, 6),
        "reports_per_hr": round(reports_per_hr, 3),
        "lambda_false_kinetic": round(lam_false, 6),
        "p_false_kinetic": round(p_false_kinetic, 6),
    }

    return QuantPatch(latex_equations=latex_equations, examples=[example], warnings=alerts)


def patch_to_dict(patch: QuantPatch) -> Dict[str, Any]:
    return {
        "latex_equations": patch.latex_equations,
        "examples": patch.examples,
        "warnings": [asdict(warning) for warning in patch.warnings],
    }



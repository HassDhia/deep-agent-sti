from typing import Any, Dict, List

from quant_normalization import _replace_metric_tokens
import re

_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


def normalize_role_actions(role_actions: Any) -> Dict[str, List[str]]:
    normalized: Dict[str, List[str]] = {}
    if not isinstance(role_actions, dict):
        return normalized
    for role, actions in role_actions.items():
        if isinstance(actions, str):
            normalized[role] = [_replace_metric_tokens(actions)]
        elif isinstance(actions, list):
            normalized[role] = [
                _replace_metric_tokens(str(action)) for action in actions if isinstance(action, (str, int, float))
            ]
    return normalized


def normalize_operator_specs(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return payload

    pilot_spec = payload.get("pilot_spec")
    if isinstance(pilot_spec, dict):
        for key in ("window", "primary_move"):
            if key in pilot_spec:
                pilot_spec[key] = _replace_metric_tokens(pilot_spec.get(key, ""))
        payload["pilot_spec"] = pilot_spec

    metric_spec = payload.get("metric_spec")
    if isinstance(metric_spec, dict):
        for spec in metric_spec.values():
            if not isinstance(spec, dict):
                continue
            for key in ("label", "unit", "target_text"):
                if key in spec:
                    spec[key] = _replace_metric_tokens(spec.get(key, ""))
            if "target_range" in spec:
                spec["target_range"] = _normalize_target_range(spec.get("target_range"))
        payload["metric_spec"] = metric_spec

    role_actions = payload.get("role_actions")
    payload["role_actions"] = normalize_role_actions(role_actions)

    return payload


def _normalize_target_range(raw: Any) -> Any:
    """Canonicalize target_range to [low, high] numeric values when possible."""
    if isinstance(raw, list):
        numeric = [float(val) for val in raw if isinstance(val, (int, float))]
        if len(numeric) == 1:
            return [numeric[0], numeric[0]]
        if len(numeric) >= 2:
            return [numeric[0], numeric[1]]
        return raw
    if isinstance(raw, (int, float)):
        value = float(raw)
        return [value, value]
    if isinstance(raw, str):
        matches = _NUMBER_RE.findall(raw)
        numeric = [float(match) for match in matches]
        if len(numeric) == 1:
            return [numeric[0], numeric[0]]
        if len(numeric) >= 2:
            return [numeric[0], numeric[1]]
        return raw
    return raw

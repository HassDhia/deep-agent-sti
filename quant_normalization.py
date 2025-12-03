import re
from typing import Any, Dict, List

from metrics import friendly_metric_label, known_metric_ids

SNAKE_CASE_PATTERN = re.compile(r"\b([a-z0-9]+(?:_[a-z0-9]+)+)\b")
METRIC_ID_SET = set(known_metric_ids())


def _humanize_token(token: str) -> str:
    label = friendly_metric_label(token)
    if label and label != token:
        return label
    if token in METRIC_ID_SET:
        return token.replace("_", " ")
    return token.replace("_", " ")


def _replace_metric_tokens(text: Any) -> Any:
    if not isinstance(text, str):
        return text

    def _sub(match: re.Match) -> str:
        token = match.group(1)
        return _humanize_token(token)

    return SNAKE_CASE_PATTERN.sub(_sub, text)


def normalize_quant_blocks_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Return payload with metric ids in human-facing fields rewritten as friendly labels."""
    if not isinstance(payload, dict):
        return payload

    anchors = payload.get("anchors") or []
    for anchor in anchors:
        if not isinstance(anchor, dict):
            continue
        for key in ("headline", "topic", "expression"):
            if key in anchor:
                anchor[key] = _replace_metric_tokens(anchor.get(key, ""))

    plan = payload.get("measurement_plan") or []
    for item in plan:
        if not isinstance(item, dict):
            continue
        for key in ("metric", "expression", "why_it_matters"):
            if key in item:
                item[key] = _replace_metric_tokens(item.get(key, ""))

    if "spine_hook" in payload:
        payload["spine_hook"] = _replace_metric_tokens(payload.get("spine_hook", ""))

    return payload

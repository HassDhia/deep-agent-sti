import re
from typing import Any, Dict, List, Tuple

SNAKE_CASE_PATTERN = re.compile(r"\b[a-z0-9]+(?:_[a-z0-9]+)+\b")
PLACEHOLDER_STRINGS = {
    "Plain-English label",
    "Example topic",
    "Example expression",
    "Example metric",
    "Example owner",
    "Example timeframe",
}


def _walk_strings(node: Any, path: str = "") -> List[Tuple[str, str]]:
    results: List[Tuple[str, str]] = []
    if isinstance(node, str):
        results.append((path, node))
    elif isinstance(node, list):
        for idx, value in enumerate(node):
            child_path = f"{path}[{idx}]" if path else f"[{idx}]"
            results.extend(_walk_strings(value, child_path))
    elif isinstance(node, dict):
        for key, value in node.items():
            child_path = f"{path}.{key}" if path else key
            results.extend(_walk_strings(value, child_path))
    return results


def _contains_placeholder(text: str) -> bool:
    return any(placeholder in text for placeholder in PLACEHOLDER_STRINGS)


def _find_illegal_snake_case(text: str) -> List[str]:
    return [token for token in SNAKE_CASE_PATTERN.findall(text)]


def lint_quant_blocks(payload: Dict[str, Any]) -> List[str]:
    """Return a list of contract violations for generate_quant_blocks."""

    errors: List[str] = []

    if not isinstance(payload, dict):
        return ["Quant blocks payload must be a dictionary."]

    for key in ("spine_hook", "anchors", "measurement_plan", "coverage"):
        if key not in payload:
            errors.append(f"Missing top-level key: {key}")

    spine_hook = payload.get("spine_hook")
    if not isinstance(spine_hook, str) or not spine_hook.strip():
        errors.append("spine_hook must be a non-empty string.")

    coverage = payload.get("coverage")
    if not isinstance(coverage, (int, float)):
        errors.append("coverage must be a numeric value between 0.0 and 1.0.")
    else:
        coverage_value = float(coverage)
        if not (0.0 <= coverage_value <= 1.0):
            errors.append(f"coverage must be between 0.0 and 1.0 (got {coverage_value}).")

    anchors = payload.get("anchors", [])
    if not isinstance(anchors, list):
        errors.append("anchors must be a list.")
        anchors = []
    if len(anchors) == 0:
        errors.append("anchors must contain at least one entry.")
    if len(anchors) > 4:
        errors.append(f"anchors must contain ≤4 entries (got {len(anchors)}).")

    for idx, anchor in enumerate(anchors):
        anchor_path = f"anchors[{idx}]"
        if not isinstance(anchor, dict):
            errors.append(f"{anchor_path} must be an object.")
            continue
        required_anchor_fields = [
            "id",
            "headline",
            "topic",
            "value_low",
            "value_high",
            "unit",
            "status",
            "band",
            "owner",
            "expression",
            "source_ids",
            "applies_to_signals",
        ]
        for field in required_anchor_fields:
            if field not in anchor:
                errors.append(f"{anchor_path}.{field} is missing.")
        value_low = anchor.get("value_low")
        value_high = anchor.get("value_high")
        if not isinstance(value_low, (int, float)) or not isinstance(value_high, (int, float)):
            errors.append(f"{anchor_path}.value_low and value_high must be numeric.")
        elif value_low > value_high:
            errors.append(f"{anchor_path}.value_low ({value_low}) > value_high ({value_high}).")
        status = anchor.get("status")
        if status not in {"observed", "target"}:
            errors.append(f"{anchor_path}.status must be 'observed' or 'target' (got {status}).")
        band = anchor.get("band")
        if band not in {"base", "stretch"}:
            errors.append(f"{anchor_path}.band must be 'base' or 'stretch' (got {band}).")
        source_ids = anchor.get("source_ids")
        if not isinstance(source_ids, list) or not all(isinstance(val, int) for val in source_ids):
            errors.append(f"{anchor_path}.source_ids must be a list of integers.")
        signal_ids = anchor.get("applies_to_signals")
        if not isinstance(signal_ids, list) or not all(isinstance(val, str) for val in signal_ids):
            errors.append(f"{anchor_path}.applies_to_signals must be a list of strings.")

    measurement_plan = payload.get("measurement_plan", [])
    if not isinstance(measurement_plan, list):
        errors.append("measurement_plan must be a list.")
        measurement_plan = []
    if len(measurement_plan) > 4:
        errors.append(f"measurement_plan must contain ≤4 entries (got {len(measurement_plan)}).")

    for idx, item in enumerate(measurement_plan):
        item_path = f"measurement_plan[{idx}]"
        if not isinstance(item, dict):
            errors.append(f"{item_path} must be an object.")
            continue
        required_plan_fields = [
            "id",
            "metric",
            "expression",
            "owner",
            "timeframe",
            "status",
            "why_it_matters",
        ]
        for field in required_plan_fields:
            if field not in item:
                errors.append(f"{item_path}.{field} is missing.")
        status = item.get("status")
        if status not in {"plan", "observed", "target"}:
            errors.append(f"{item_path}.status must be 'plan', 'observed', or 'target' (got {status}).")
        if not isinstance(item.get("why_it_matters"), str) or not item.get("why_it_matters"):
            errors.append(f"{item_path}.why_it_matters must be a non-empty string.")

    human_suffixes = (
        ".headline",
        ".topic",
        ".expression",
        ".metric",
        ".why_it_matters",
        "spine_hook",
    )
    for path, text in _walk_strings(payload):
        if not isinstance(text, str):
            continue
        if not any(path.endswith(suffix) for suffix in human_suffixes):
            continue
        if _contains_placeholder(text):
            errors.append(f"{path} contains placeholder text: {text!r}")
        snake_tokens = _find_illegal_snake_case(text)
        if snake_tokens:
            errors.append(f"{path} contains snake_case tokens that look like internal ids: {snake_tokens}")

    return errors


OPERATOR_REQUIRED_ROLES = {"Head of Retail", "Head of Partnerships", "Finance"}


def _is_operator_human_field(path: str) -> bool:
    if not path:
        return False
    clean_path = path.split("[", 1)[0]
    if clean_path.endswith(".primary_move") or clean_path.endswith(".window"):
        return True
    if ".metric_spec." in clean_path and clean_path.endswith(".target_text"):
        return True
    if clean_path.startswith("role_actions."):
        return True
    return False


def lint_operator_specs(payload: Dict[str, Any]) -> List[str]:
    """Return a list of contract violations for generate_operator_specs."""

    errors: List[str] = []

    if not isinstance(payload, dict):
        return ["Operator specs payload must be a dictionary."]

    for key in ("pilot_spec", "metric_spec", "role_actions"):
        if key not in payload:
            errors.append(f"Missing top-level key: {key}")

    pilot_spec = payload.get("pilot_spec") or {}
    metric_spec = payload.get("metric_spec") or {}
    role_actions = payload.get("role_actions") or {}

    if not isinstance(pilot_spec, dict):
        errors.append("pilot_spec must be an object.")
    else:
        required_fields = [
            "scenario",
            "store_count",
            "store_type",
            "duration_weeks",
            "window",
            "primary_move",
            "owner_roles",
            "key_metrics",
        ]
        for field in required_fields:
            if field not in pilot_spec:
                errors.append(f"pilot_spec.{field} is missing.")

        scenario = pilot_spec.get("scenario")
        if not isinstance(scenario, str):
            errors.append("pilot_spec.scenario must be a string.")
        elif not SNAKE_CASE_PATTERN.fullmatch(scenario):
            errors.append(f"pilot_spec.scenario should be snake_case (got {scenario!r}).")

        store_count = pilot_spec.get("store_count")
        if not isinstance(store_count, int) or store_count <= 0:
            errors.append("pilot_spec.store_count must be a positive integer.")

        duration_weeks = pilot_spec.get("duration_weeks")
        if not isinstance(duration_weeks, int) or duration_weeks <= 0:
            errors.append("pilot_spec.duration_weeks must be a positive integer.")

        window = pilot_spec.get("window")
        if not isinstance(window, str) or not window.strip():
            errors.append("pilot_spec.window must be a non-empty string.")

        primary_move = pilot_spec.get("primary_move")
        if not isinstance(primary_move, str) or not primary_move.strip():
            errors.append("pilot_spec.primary_move must be a non-empty string.")

        owner_roles = pilot_spec.get("owner_roles")
        if not isinstance(owner_roles, list) or not all(isinstance(role, str) for role in owner_roles or []):
            errors.append("pilot_spec.owner_roles must be a list of strings.")
        elif not (2 <= len(owner_roles) <= 4):
            errors.append("pilot_spec.owner_roles must contain between 2 and 4 entries.")

        key_metrics = pilot_spec.get("key_metrics")
        if not isinstance(key_metrics, list) or not all(isinstance(metric, str) for metric in key_metrics or []):
            errors.append("pilot_spec.key_metrics must be a list of metric id strings.")
        elif not key_metrics:
            errors.append("pilot_spec.key_metrics must not be empty.")

    if not isinstance(metric_spec, dict):
        errors.append("metric_spec must be an object keyed by metric ids.")
        metric_spec = {}
    else:
        key_metrics = pilot_spec.get("key_metrics") if isinstance(pilot_spec, dict) else []
        for metric_id in key_metrics or []:
            if metric_id not in metric_spec:
                errors.append(f"metric_spec missing entry for key metric id {metric_id!r}.")

        for metric_id, spec in metric_spec.items():
            path = f"metric_spec.{metric_id}"
            if not isinstance(spec, dict):
                errors.append(f"{path} must be an object.")
                continue
            required_fields = ["label", "target_range", "unit", "stage", "owner", "target_text"]
            for field in required_fields:
                if field not in spec:
                    errors.append(f"{path}.{field} is missing.")
            target_range = spec.get("target_range")
            if not (
                isinstance(target_range, list)
                and len(target_range) == 2
                and all(isinstance(val, (int, float)) for val in target_range)
            ):
                errors.append(f"{path}.target_range must be a numeric [low, high] list.")
            stage = spec.get("stage")
            if stage not in {"target", "observed", "guardrail"}:
                errors.append(f"{path}.stage must be 'target', 'observed', or 'guardrail' (got {stage!r}).")
            if not isinstance(spec.get("label"), str) or not spec.get("label"):
                errors.append(f"{path}.label must be a non-empty string.")
            if not isinstance(spec.get("owner"), str) or not spec.get("owner"):
                errors.append(f"{path}.owner must be a non-empty string.")
            if not isinstance(spec.get("target_text"), str) or not spec.get("target_text"):
                errors.append(f"{path}.target_text must be a non-empty string.")

    if not isinstance(role_actions, dict):
        errors.append("role_actions must be an object mapping roles to action lists.")
        role_actions = {}
    else:
        missing_roles = sorted(OPERATOR_REQUIRED_ROLES - set(role_actions.keys()))
        if missing_roles:
            errors.append(f"role_actions missing required roles: {missing_roles}")
        for role, actions in role_actions.items():
            path = f"role_actions.{role}"
            if not isinstance(actions, list) or not all(isinstance(action, str) for action in actions):
                errors.append(f"{path} must be a list of strings.")
                continue
            for idx, action in enumerate(actions):
                if not action.strip():
                    errors.append(f"{path}[{idx}] must be a non-empty string.")

    for path, text in _walk_strings(payload):
        if not isinstance(text, str):
            continue
        if not _is_operator_human_field(path):
            continue
        if _contains_placeholder(text):
            errors.append(f"{path} contains placeholder text: {text!r}")
        snake_tokens = _find_illegal_snake_case(text)
        if snake_tokens:
            errors.append(f"{path} contains snake_case tokens that look like internal ids: {snake_tokens}")

    return errors


__all__ = ["lint_quant_blocks", "lint_operator_specs"]

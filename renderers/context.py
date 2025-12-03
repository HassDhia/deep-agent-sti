"""Helpers for building shared Market-Path dossier context."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from config import STIConfig
from html_converter_agent import HTMLConverterAgent
from metrics import anchor_stage, friendly_metric_label, friendly_metric_name


CONTROL_CHAR_RE = re.compile(r"[\x00-\x09\x0B-\x1F\x7F]")
SCHEMA_TOKEN_FIXES = [
    (re.compile(r"(?i)_and_"), " and "),
    (re.compile(r"(?i)_pct\b"), " percent"),
    (re.compile(r"(?i)_rel\b"), " relative"),
    (re.compile(r"(?i)_rel_"), " relative "),
]
ACRONYM_FIXES = {
    "qr": "QR",
    "cpa": "CPA",
    "cpm": "CPM",
    "sku": "SKU",
}

logger = logging.getLogger(__name__)


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "True" if value else ""
    if isinstance(value, (list, tuple, set)):
        parts = [_clean_text(part) for part in value]
        joined = " ".join(part for part in parts if part)
        return joined.strip()
    text = str(value).strip()
    if not text:
        return ""
    text = CONTROL_CHAR_RE.sub(" ", text)
    text = re.sub(r"\(M\d+\)", "", text)
    text = re.sub(r"(?i)\bmetric\s+(?=[A-Z])", "", text)
    for pattern, replacement in SCHEMA_TOKEN_FIXES:
        text = pattern.sub(replacement, text)
    text = text.replace("_", " ")
    text = re.sub(r"(?i)\bpct\b", " percent", text)
    text = re.sub(r"(?i)\brel\b", " relative", text)
    text = re.sub(r"(?i)\bvs\b", " vs", text)

    def _restore_acronyms(match: re.Match) -> str:
        return ACRONYM_FIXES.get(match.group(0).lower(), match.group(0).upper())

    if ACRONYM_FIXES:
        pattern = r"\b(" + "|".join(re.escape(key) for key in ACRONYM_FIXES.keys()) + r")\b"
        text = re.sub(pattern, _restore_acronyms, text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _sentence(value: Any) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    if text[-1] in ".!?":
        return text
    return f"{text}."


def _paragraph(*parts: str) -> str:
    sentences = [part.strip() for part in parts if part and part.strip()]
    return " ".join(sentences)


def _list_sentence(items: List[str]) -> str:
    chunks = [item for item in items if item]
    if not chunks:
        return ""
    if len(chunks) == 1:
        return chunks[0]
    if len(chunks) == 2:
        return f"{chunks[0]} and {chunks[1]}"
    return ", ".join(chunks[:-1]) + f", and {chunks[-1]}"


def _metric_value_text(entry: Dict[str, Any]) -> str:
    target_range = entry.get("target_range")
    unit = _clean_text(entry.get("unit"))
    if isinstance(target_range, list) and len(target_range) == 2:
        low, high = target_range
        try:
            low_val = float(low)
            high_val = float(high)
        except (TypeError, ValueError):
            low_val = None
            high_val = None
        if low_val is not None and high_val is not None:
            if low_val == high_val:
                value_text = f"{low_val:g}"
            else:
                value_text = f"{low_val:g}–{high_val:g}"
            return f"{value_text}{(' ' + unit) if unit else ''}".strip()
    return _clean_text(entry.get("target_text") or entry.get("value") or "Target TBD")


def _measurement_from_spec(
    metric_spec: Dict[str, Dict[str, Any]],
    quant: Dict[str, Any],
    time_window: Dict[str, Any],
) -> Dict[str, Any]:
    measurement = {"anchors": [], "plan": []}
    if metric_spec:
        for metric_id, entry in metric_spec.items():
            measurement["anchors"].append(
                {
                    "metric": entry.get("label") or friendly_metric_label(metric_id),
                    "value": _metric_value_text(entry),
                    "owner": _clean_text(entry.get("owner")),
                    "stage": _clean_text(entry.get("stage")) or "target",
                    "notes": _clean_text(entry.get("notes")),
                }
            )
    if not measurement["anchors"]:
        for anchor in quant.get("anchors", []):
            label = anchor.get("headline") or anchor.get("label") or anchor.get("metric") or "Metric"
            topic = anchor.get("topic") or anchor.get("metric") or label
            friendly_metric = friendly_metric_label(topic)
            value_text = anchor.get("expression") or anchor.get("value") or ""
            if anchor.get("value_low") is not None and anchor.get("value_high") is not None:
                unit = _clean_text(anchor.get("unit") or "")
                low = anchor.get("value_low")
                high = anchor.get("value_high")
                if low == high:
                    value_text = f"{low}{(' ' + unit) if unit else ''}".strip()
                else:
                    value_text = f"{low}–{high}{(' ' + unit) if unit else ''}".strip()
            stage = anchor_stage(label)
            owner = _clean_text(anchor.get("owner"))
            notes = []
            band = _clean_text(anchor.get("band"))
            if band and band.lower() not in {"base", "default"}:
                notes.append(f"{band} band")
            topic_label = _clean_text(anchor.get("topic"))
            if topic_label and topic_label.lower() not in friendly_metric.lower():
                notes.append(topic_label)
            measurement["anchors"].append(
                {
                    "metric": friendly_metric,
                    "value": _clean_text(value_text or "target TBD"),
                    "owner": owner,
                    "stage": stage,
                    "notes": ", ".join(notes),
                }
            )
    for plan in quant.get("measurement_plan", []):
        measurement["plan"].append(
            {
                "metric": _clean_text(plan.get("metric") or "Metric"),
                "expression": _clean_text(plan.get("expression") or plan.get("value") or "Target TBD"),
                "owner": _clean_text(plan.get("owner") or "Owner TBD"),
                "timeframe": _clean_text(plan.get("timeframe") or time_window.get("label") or "Window"),
                "why": _clean_text(plan.get("why_it_matters") or plan.get("notes") or ""),
            }
        )
    return measurement


def _action_text(value: Any) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    text = re.sub(r"(?i)\bbehavioral signal:\s*", "", text)
    text = re.sub(r"(?i)\bsignal:\s*", "", text)
    return text


def _display_title(raw_title: str) -> str:
    if not raw_title:
        return "Market-Path Report"
    return re.sub(r"^signal report\s+—\s+", "", raw_title, flags=re.IGNORECASE).strip() or raw_title.strip()


def _first_sentence(text: str) -> str:
    if not text:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return parts[0].strip()


def _time_window_label(window: Dict[str, Any]) -> str:
    label = _clean_text(window.get("label"))
    if label:
        return label
    start = _clean_text(window.get("start", ""))
    end = _clean_text(window.get("end", ""))
    if start and end:
        return f"{start} -> {end}"
    return start or end or "Active window"


def _summarize_sources(sources: List[Dict[str, Any]], limit: int = 4) -> List[str]:
    summaries: List[str] = []
    for source in sources[:limit]:
        publisher = _clean_text(source.get("publisher") or source.get("domain") or "Source")
        date = _clean_text(source.get("date"))
        title = _clean_text(source.get("title"))
        summaries.append(f"{publisher} ({date}): {title}")
    return summaries


def _pilot_sentences(
    pilot_spec: Dict[str, Any],
    metric_spec: Dict[str, Dict[str, Any]],
    goal_text: str = "",
) -> List[str]:
    if not pilot_spec:
        base = _sentence("Concretely, run a short pilot inside a few representative sites and hold everything else steady.")
        goal = _sentence(goal_text or "The aim is to see if that pilot can replace a markdown weekend with something stickier.")
        return [base, goal]
    count = pilot_spec.get("store_count")
    duration = pilot_spec.get("duration_weeks")
    store_type_label = _clean_text(pilot_spec.get("store_type") or "flagship") or "flagship"
    window = _clean_text(pilot_spec.get("window") or pilot_spec.get("window_label") or "the pilot window")
    move_raw = _clean_text(pilot_spec.get("primary_move") or "run the pilot")
    location = pilot_spec.get("location_radius_miles")
    if not count:
        count_text = "a handful of"
    elif count == 1:
        count_text = "one"
    else:
        count_text = str(int(count)) if isinstance(count, (int, float)) and float(count).is_integer() else str(count)
    label_lower = store_type_label.lower()
    if label_lower.endswith(("stores", "doors", "sites", "locations")):
        store_phrase = store_type_label
    else:
        store_phrase = f"{store_type_label} stores"
    duration_phrase = f"{int(duration)}-week" if isinstance(duration, (int, float)) and duration else "short"
    window_phrase = f"from {window}" if window else "during the pilot window"
    run_components = [f"Concretely, I'd run a {duration_phrase} test in {count_text} {store_phrase} {window_phrase}"]
    if move_raw:
        move_clause = move_raw.rstrip(".")
        lower_move = move_clause.lower()
        prefix = ""
        if lower_move.startswith("run "):
            move_clause = move_clause[4:]
            prefix = "run "
        elif lower_move.startswith(("a ", "an ", "the ")):
            prefix = "run "
        move_clause = move_clause.strip()
        if move_clause:
            clause_body = move_clause[0].lower() + move_clause[1:] if move_clause else ""
            run_components.append(f"and in those doors we'd {prefix}{clause_body}")
    if location:
        try:
            radius = int(float(location))
        except (TypeError, ValueError):
            radius = None
        if radius:
            run_components.append(
                f"and we keep the footprint tight by inviting people within {radius} miles so everyone sees the same drop cadence"
            )
    run_sentence = _sentence(" ".join(part for part in run_components if part))
    goal_sentence = _clean_text(goal_text)
    if not goal_sentence:
        goal_sentence = move_raw
    sentences = [run_sentence]
    if goal_sentence:
        sentences.append(_sentence(goal_sentence))
    return [line for line in sentences if line]


def _imperative_line(text: str) -> str:
    clean = _clean_text(text)
    if not clean:
        return ""
    clause = clean.rstrip(".")
    if clause:
        clause = clause[0].lower() + clause[1:]
    return _sentence(f"I'm asking you to {clause}")


def _role_label(role: str) -> str:
    label = _clean_text(role)
    lowered = label.lower()
    for prefix in ("head of ", "vp of ", "svp of ", "director of "):
        if lowered.startswith(prefix):
            return label[len(prefix):].strip() or label
    return label or "Operations"


def _role_action_sentences(role: str, instruction: Any) -> List[str]:
    clean = _clean_text(instruction)
    if not clean:
        return []
    parts = re.split(r"(?<=[.!?])\s+", clean)
    subject = _role_label(role)
    sentences: List[str] = []
    idx = 0
    for part in parts:
        clause = part.strip().rstrip(".")
        if not clause:
            continue
        clause = clause[0].lower() + clause[1:] if clause else clause
        if idx == 0:
            sentences.append(_sentence(f"{subject} needs to {clause}"))
        else:
            sentences.append(_sentence(f"{subject} also {clause}"))
        idx += 1
    return sentences


def _role_actions_story(role_actions: Dict[str, Any]) -> str:
    if not role_actions:
        return ""
    sentences = [_sentence("In practice this only works if a few teams move in step.")]
    used: List[str] = []
    priority = ["Head of Retail", "Head of Partnerships", "Finance"]
    for role in priority:
        if role not in role_actions:
            continue
        sentences.extend(_role_action_sentences(role, role_actions[role]))
        used.append(role)
    for role, instruction in role_actions.items():
        if role in used:
            continue
        sentences.extend(_role_action_sentences(role, instruction))
        used.append(role)
        if len(sentences) >= 8:
            break
    return _paragraph(*[s for s in sentences if s])


def _if_then_guardrail(clauses: List[str]) -> str:
    if not clauses:
        return _sentence("If the core guardrails drift, you pause and reset.")
    focus: List[str] = []
    for clause in clauses[:3]:
        clean = clause.rstrip(".").strip()
        if clean:
            focus.append(clean)
    if not focus:
        return _sentence("If the guardrails slip, you stop and revert.")
    if len(focus) == 1:
        return _sentence(f"If {focus[0]}, you keep running; once it drifts, you pause and reset.")
    if len(focus) == 2:
        return _sentence(
            f"If {focus[0]} and {focus[1]}, you keep running; as soon as either breaks, you pause and revert."
        )
    return _sentence(
        f"If {focus[0]}, {focus[1]}, and {focus[2]}, you keep running; the minute any of them slip, you stop and go back to baseline."
    )


def _clean_exec_take(text: str) -> str:
    if not text:
        return ""
    cleaned = _clean_text(text)
    if not cleaned:
        return ""
    cleaned = re.sub(r"\s*->\s*tracks[^\n]*", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*->\s*mandate[^\n]*", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip()


def _build_exec_take(bundle: Dict[str, Any], signals: List[Dict[str, Any]], quant: Dict[str, Any]) -> str:
    highlights = bundle.get("highlights") or []
    exec_summary = bundle.get("executive_summary", "")
    top_moves = bundle.get("top_operator_moves") or []
    anchors = quant.get("anchors") or []

    fast_stack = bundle.get("fast_stack") or {}
    what = _clean_text(
        fast_stack.get("headline")
        or (highlights[0] if highlights else _first_sentence(exec_summary))
    )
    if not what and signals:
        what = _clean_text(signals[0].get("text") or signals[0].get("description"))
    why = ""
    if anchors:
        label = anchors[0].get("label") or anchors[0].get("metric")
        value = anchors[0].get("value") or anchors[0].get("expression")
        why = f"{_clean_text(label)} tracks {_clean_text(value)}"
    elif len(highlights) > 1:
        why = _clean_text(highlights[1])
    action = _clean_text(
        fast_stack.get("next_30_days")
        or (top_moves[0] if top_moves else bundle.get("letter_primary_cta") or "Stand up the measurement run")
    )
    return _clean_exec_take(f"{what} -> {why or 'Confidence shifts to measured operators'} -> {action}")


def _mechanism_rows(sections: Dict[str, Any], signals: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    deep = sections.get("deep_analysis") if isinstance(sections, dict) else None
    deep_sections = deep.get("sections", []) if isinstance(deep, dict) else []
    for item in deep_sections:
        insight = _clean_text(item.get("insight"))
        sentences = re.split(r"(?<=[.!?])\s+", insight) if insight else []
        cause = _clean_text(item.get("title") or (sentences[0] if sentences else "Structural shift"))
        effect = _clean_text(sentences[0] if sentences else insight)
        second = _clean_text(sentences[1] if len(sentences) > 1 else item.get("operator_note"))
        constraint = _clean_text(item.get("operator_note") or (sentences[2] if len(sentences) > 2 else "Requires disciplined guardrails."))
        rows.append(
            {
                "cause": cause or "Inputs move",
                "effect": effect or "Demand concentrates in short windows.",
                "second_order": second or "Operators must show quant support fast.",
                "constraint": constraint,
            }
        )
    if not rows and signals:
        signal = signals[0]
        rows.append(
            {
                "cause": _clean_text(signal.get("name") or "Primary signal"),
                "effect": _clean_text(signal.get("text") or "Demand consolidates."),
                "second_order": "Operators that react first gain collaboration leverage.",
                "constraint": "Hold measurement guardrails to avoid false positives.",
            }
        )
    return rows


def _operator_moves(bundle: Dict[str, Any], sections: Dict[str, Any]) -> Dict[str, List[str]]:
    activation = sections.get("activation_kit") if isinstance(sections, dict) else []
    future = sections.get("future_outlook") if isinstance(sections, dict) else []
    moves = {
        "immediate": [],
        "positioning": [],
        "compounding": [],
    }

    for move in bundle.get("top_operator_moves") or []:
        if len(moves["immediate"]) < 3:
            moves["immediate"].append(_clean_text(move))

    for play in activation or []:
        display = play.get("display", {})
        play_name = _clean_text(
            display.get("card_title") or display.get("play_name") or play.get("pillar") or "Activation play"
        )
        proof = _clean_text(
            display.get("proof_point") or play.get("description") or play.get("operator_note")
        )
        summary = f"{play_name}: {proof or 'Tie directly to signals and quant'}"
        if len(moves["positioning"]) < 3:
            moves["positioning"].append(summary)

    for horizon in future or []:
        headline = _clean_text(horizon.get("headline"))
        desc = _clean_text(horizon.get("description"))
        if headline or desc:
            moves["compounding"].append(f"{headline or 'Future state'}: {desc or 'Compounding upside for disciplined operators.'}")
        if len(moves["compounding"]) >= 3:
            break

    for key, fallback in [
        ("immediate", "Stand up early-window tests with measurement mirroring this bundle."),
        ("positioning", "Codify the collaboration brief so partners plug directly into the window."),
        ("compounding", "Instrument loyalty plus share gains so small wins compound."),
    ]:
        if not moves[key]:
            moves[key].append(fallback)
    return moves


def _risk_rows(sections: Dict[str, Any]) -> List[Dict[str, str]]:
    risks = []
    for risk in sections.get("risk_radar", []) if isinstance(sections, dict) else []:
        risks.append(
            {
                "name": _clean_text(risk.get("risk_name") or "Risk"),
                "trigger": _clean_text(risk.get("trigger") or "Trigger unknown"),
                "detection": _clean_text(risk.get("detection") or "Instrument leading signals."),
                "mitigation": _clean_text(risk.get("mitigation") or "Throttle exposure."),
            }
        )
    if not risks:
        risks.append(
            {
                "name": "Signal drift",
                "trigger": "Operators chase low-quality suppliers.",
                "detection": "Measurement stops beating baseline.",
                "mitigation": "Fall back to the guardrails and re-center on quantified demand.",
            }
        )
    return risks


def _case_story(bundle: Dict[str, Any], sections: Dict[str, Any]) -> str:
    patterns = sections.get("pattern_matches") if isinstance(sections, dict) else []
    if patterns:
        match = patterns[0]
        then_line = _clean_text(match.get("then") or match.get("summary"))
        now_line = _clean_text(match.get("now") or "Operators see a parallel now.")
        leap = _clean_text(match.get("operator_leap"))
        return "\n".join(
            [
                f"Then: {then_line}" if then_line else "",
                f"Now: {now_line}" if now_line else "",
                f"Operator move: {leap or 'Move fast with structured pilots.'}",
            ]
        ).strip()
    deep = sections.get("deep_analysis", {}) if isinstance(sections, dict) else {}
    deep_sections = deep.get("sections", []) if isinstance(deep, dict) else []
    if deep_sections:
        sec = deep_sections[0]
        insight = _clean_text(sec.get("insight"))
        return f"{insight} Teams treated that as a script and shifted budget toward the measured window."
    summary = _clean_text(bundle.get("executive_summary"))
    return f"{summary} Operators proved it with instrumentation in two-week sprints."


def _guardrails_text(bundle: Dict[str, Any], time_window: Dict[str, Any]) -> List[str]:
    prereqs = [_clean_text(p) for p in (bundle.get("prerequisites") or []) if _clean_text(p)]
    guardrails = []
    window_label = _time_window_label(time_window)
    if window_label:
        guardrails.append(f"keep it inside {window_label}")
    region = _clean_text(bundle.get("region") or (bundle.get("qa", {}) or {}).get("scope", {}).get("target_region"))
    if region:
        guardrails.append(f"stay focused on {region}")
    if prereqs:
        guardrails.append(f"have {', '.join(prereqs)} ready before day one")
    best_fit = _clean_text(bundle.get("best_fit"))
    if best_fit:
        guardrails.append(f"this works best for {best_fit}")
    not_for = _clean_text(bundle.get("not_for"))
    if not_for:
        guardrails.append(f"skip it for {not_for}")
    return guardrails


def _comparison_blocks(report_bundle: Dict[str, Any]) -> Dict[str, List[Dict[str, str]]]:
    comparison = report_bundle.get("comparison_map") or {}
    approach_rows: List[Dict[str, str]] = []
    for entry in (comparison.get("approach_map") or [])[:3]:
        metrics = entry.get("key_metrics")
        metrics_label = ""
        if isinstance(metrics, list):
            metrics_label = ", ".join([_clean_text(m) for m in metrics if _clean_text(m)])
        elif metrics:
            metrics_label = _clean_text(metrics)
        approach_rows.append(
            {
                "name": _clean_text(entry.get("approach_name") or "Approach"),
                "best_for": _clean_text(entry.get("who_it_is_for") or entry.get("best_for") or ""),
                "strengths": _clean_text(entry.get("strengths") or ""),
                "failure": _clean_text(entry.get("failure_modes") or ""),
                "choose": _clean_text(entry.get("when_to_choose") or ""),
                "avoid": _clean_text(entry.get("when_not_to_choose") or ""),
                "metrics": metrics_label,
            }
        )
    buyer_rows: List[Dict[str, str]] = []
    for entry in (comparison.get("buyer_guide") or [])[:4]:
        buyer_rows.append(
            {
                "option": _clean_text(entry.get("option_name") or "Option"),
                "best_for": _clean_text(entry.get("best_for") or ""),
                "not_for": _clean_text(entry.get("not_for") or ""),
                "shape": _clean_text(entry.get("commercial_shape") or ""),
                "proof": _clean_text(entry.get("proof_needed_before_scaling") or ""),
                "sti_fit": _clean_text(entry.get("where_STI_fits") or ""),
            }
        )
    return {"approaches": approach_rows, "buyers": buyer_rows}


def _confidence_line(confidence: Dict[str, Any]) -> str:
    if not confidence:
        return "Confidence: Medium. Strength depends on the next readout."
    band = _clean_text(confidence.get("band") or "Medium")
    score = confidence.get("score")
    reason = _clean_text(confidence.get("display") or "")
    if score is not None:
        base = f"Confidence: {band} ({score:.2f})."
    else:
        base = f"Confidence: {band}."
    if reason:
        base += f" {reason}"
    return base


def _watch_metrics(
    measurement: Dict[str, Any],
    metric_spec: Optional[Dict[str, Dict[str, Any]]],
    pilot_spec: Optional[Dict[str, Any]],
) -> List[str]:
    watch: List[str] = []
    metric_spec = metric_spec or {}
    pilot_spec = pilot_spec or {}
    key_metrics = pilot_spec.get("key_metrics") if isinstance(pilot_spec, dict) else None
    if key_metrics:
        for metric_id in key_metrics:
            entry = metric_spec.get(metric_id)
            if not entry:
                continue
            label = entry.get("label") or friendly_metric_label(metric_id)
            target = _metric_value_text(entry)
            owner = _clean_text(entry.get("owner"))
            stage = (entry.get("stage") or "").lower()
            prefix = label
            if stage == "guardrail":
                prefix = f"{label} guardrail"
            elif stage == "stretch":
                prefix = f"Stretch {label}"
            elif stage == "observed":
                prefix = f"Observed {label}"
            details: List[str] = []
            if owner:
                details.append(owner)
            notes = _clean_text(entry.get("notes"))
            if notes:
                details.append(notes)
            if target:
                line = f"{prefix} stays at {target}"
            else:
                line = prefix
            if details:
                line = f"{line} ({'; '.join(details)})"
            watch.append(line)
            if len(watch) >= 3:
                return watch
    for anchor in measurement.get("anchors", []):
        metric = friendly_metric_label(anchor.get("metric"))
        value = _clean_text(anchor.get("value"))
        stage = (anchor.get("stage") or "").lower()
        owner = _clean_text(anchor.get("owner"))
        notes = _clean_text(anchor.get("notes"))
        if not metric and not value:
            continue
        label = metric or "Metric"
        if stage == "stretch":
            label = f"stretch {label}"
        elif stage == "guardrail":
            label = f"{label} guardrail"
        elif stage == "observed":
            label = f"{label} observed"
        line = label
        if value:
            line = f"{label} stays at {value}"
        details: List[str] = []
        if notes:
            details.append(notes)
        if owner:
            details.append(owner)
        if details:
            line = f"{line} ({'; '.join(details)})"
        watch.append(line)
        if len(watch) >= 3:
            return watch
    for plan in measurement.get("plan", []):
        metric = friendly_metric_label(plan.get("metric"))
        expression = _clean_text(plan.get("expression"))
        timeframe = _clean_text(plan.get("timeframe"))
        if not metric and not expression:
            continue
        line = metric
        if expression:
            line = f"{metric} trending toward {expression}"
        if timeframe:
            line = f"{line} ({timeframe})"
        why = _clean_text(plan.get("why"))
        if why:
            line = f"{line} — {why}"
        watch.append(line)
        if len(watch) >= 3:
            break
    return watch


def _human_metric_clause(metric_id: str, entry: Optional[Dict[str, Any]]) -> str:
    if not entry:
        return ""
    label = (entry.get("label") or friendly_metric_label(metric_id) or "Metric").strip()
    label_text = label.strip()
    target_text = _clean_text(entry.get("target_text"))
    if target_text:
        detail = target_text.replace("%", " percent")
        if detail and not detail[0].isalpha():
            return f"{label_text} stays at {detail}"
        return detail
    value_text = _metric_value_text(entry)
    detail = value_text.replace("%", " percent") if value_text else ""
    detail = detail.replace(" X ", " × ").replace(" x ", " × ") if detail else ""
    if detail:
        return f"{label_text} stays at {detail}"
    return label_text


def _guardrail_clauses(
    pilot_spec: Optional[Dict[str, Any]],
    metric_spec: Optional[Dict[str, Dict[str, Any]]],
) -> List[str]:
    pilot_spec = pilot_spec or {}
    metric_spec = metric_spec or {}
    clauses: List[str] = []
    key_metrics = pilot_spec.get("key_metrics") if isinstance(pilot_spec, dict) else None
    metric_ids = key_metrics or list(metric_spec.keys())
    for metric_id in metric_ids:
        entry = metric_spec.get(metric_id)
        clause = _human_metric_clause(metric_id, entry)
        clause = clause.rstrip(".") if clause else ""
        if clause:
            clauses.append(clause)
        if len(clauses) >= 3:
            break
    return clauses


def _final_cleanup(text: str) -> str:
    clean = (text or "").strip()
    if not clean:
        return ""
    clean = re.sub(r"\s+", " ", clean)
    clean = re.sub(r"(?i)foot traffic uplift percent", "foot traffic uplift", clean)
    clean = re.sub(r"(?i)event cpa ratio", "event CPA", clean)
    clean = re.sub(r"(?i)qr redemption percent", "QR redemption rate", clean)
    clean = re.sub(r"(?i)qr redemption rate among footfall", "QR redemption rate", clean)
    clean = re.sub(r"(?i)co-launchs", "co-launches", clean)
    clean = re.sub(r"(?i)\bpercent\b", "percent", clean)
    clean = re.sub(r"(?i)(\d+)\s+(\d+)\s*%", r"\1–\2%", clean)
    clean = re.sub(r"(?i)(\d+)\s+(\d+)\s+percent", r"\1–\2 percent", clean)
    clean = re.sub(r"(?i)0\.\s*8\s*[xX]\s+baseline", "0.8× baseline", clean)
    clean = re.sub(r"(?i)0\.8\s*[xX]\s+baseline", "0.8× baseline", clean)
    clean = re.sub(r"(?i)1\s+2\s+(creator(?:s)?|brand\s+collabs?)", r"one or two \1", clean)
    clean = re.sub(r"\s×\s", " × ", clean)
    clean = re.sub(r"\.\.(?!\w)", ".", clean)
    clean = clean.replace(" ;", ";")
    clean = re.sub(r"Second-order:\s*", "Second-order ", clean)
    return clean.strip()


def _guardrail_sentence(guardrails: List[str]) -> str:
    entries = [entry.rstrip(".").strip() for entry in guardrails if entry]
    if not entries:
        return ""
    joined = _list_sentence(entries)
    if not joined:
        return ""
    sentence = joined[0].upper() + joined[1:] if joined else joined
    return _sentence(sentence)


def _world_shift_paragraph(
    fast_stack: Dict[str, Any],
    spine: Dict[str, Any],
    case_line: str,
    exclude: Optional[Set[str]] = None,
) -> str:
    lines: List[str] = []
    exclude = {line for line in (exclude or set()) if line}
    world = fast_stack.get("why_now") or spine.get("what")
    if world:
        sentence = _sentence(world)
        if sentence and sentence not in exclude and sentence not in lines:
            lines.append(sentence)
    so_what = spine.get("so_what")
    if so_what and so_what != world:
        sentence = _sentence(so_what)
        if sentence and sentence not in exclude and sentence not in lines:
            lines.append(sentence)
    if case_line:
        sentence = _sentence(case_line)
        if sentence and sentence not in exclude and sentence not in lines:
            lines.append(sentence)
    return _paragraph(*lines)


def _evidence_sentence(regime: str) -> str:
    regime = (regime or "").lower()
    if regime == "directional":
        return _sentence("Treat this as a directional read.")
    if regime == "starved":
        return _sentence("Evidence is too thin to run this play.")
    return ""


def _mechanism_lines(mechanisms: List[Dict[str, str]]) -> List[str]:
    lines: List[str] = []
    for mech in mechanisms[:3]:
        cause = _clean_text(mech.get("cause"))
        effect = _clean_text(mech.get("effect"))
        second = _clean_text(mech.get("second_order"))
        if not cause and not effect:
            continue
        line = effect or cause
        if cause and effect:
            line = f"When {cause}, {effect}"
        if second:
            line = f"{line}. Second-order: {second}"
        constraint = _clean_text(mech.get("constraint"))
        if constraint:
            line = f"{line}. {constraint}"
        line = _final_cleanup(line)
        lines.append(_sentence(line))
    return lines


def _risk_lines(risks: List[Dict[str, str]]) -> List[str]:
    lines: List[str] = []
    for risk in risks[:3]:
        name = _clean_text(risk.get("name")) or "Operational drift"
        trigger = _clean_text(risk.get("trigger"))
        mitigation = _clean_text(risk.get("mitigation"))
        line = name
        if trigger:
            line = f"{name} shows up when {trigger}"
        if mitigation:
            line = f"{line}. {mitigation}"
        lines.append(_sentence(line))
    return lines


def _build_narrative(
    bundle: Dict[str, Any],
    signals: List[Dict[str, Any]],
    guardrails: List[str],
    case_story: str,
    operator_moves: Dict[str, List[str]],
    watch_metrics: List[str],
    mechanisms: List[Dict[str, str]],
    risks: List[Dict[str, str]],
    measurement: Dict[str, Any],
    deep_link: Optional[str],
    pilot_spec: Optional[Dict[str, Any]] = None,
    role_actions: Optional[Dict[str, str]] = None,
    metric_spec: Optional[Dict[str, Dict[str, Any]]] = None,
    coherence_issues: Optional[List[str]] = None,
) -> Dict[str, Any]:
    fast_stack = bundle.get("fast_stack") or {}
    spine = bundle.get("spine") or {}
    highlights = bundle.get("highlights") or []
    exec_summary = bundle.get("executive_summary")
    hook_line = _clean_text(bundle.get("hook_line") or (highlights[0] if highlights else ""))
    job_story = _clean_text(bundle.get("operator_job_story"))
    job_line = ""
    if job_story:
        lowered = job_story.lower()
        if lowered.startswith("how to "):
            job_line = _sentence("You are trying to " + job_story[6:])
        elif lowered.startswith("how do "):
            job_line = _sentence("You are trying to " + job_story[6:])
        else:
            job_line = _sentence(job_story)
    headline_line = _sentence(fast_stack.get("headline") or spine.get("what") or exec_summary or (highlights[0] if highlights else ""))
    why_line = _sentence(fast_stack.get("why_now") or spine.get("so_what") or (highlights[1] if len(highlights) > 1 else ""))
    time_window = bundle.get("time_window") or {}
    window_label = _time_window_label(time_window) if time_window else ""
    window_line = _sentence(f"The window we're instrumenting runs {window_label}.") if window_label else ""
    ask_source = (
        fast_stack.get("next_30_days")
        or bundle.get("letter_primary_cta")
        or bundle.get("letter_tldr")
        or (operator_moves.get("immediate") or [""])[0]
    )
    ask_line = _imperative_line(ask_source)

    standfirst = _paragraph(job_line or headline_line, why_line, hook_line or ask_line)

    mechanism_text = _mechanism_lines(mechanisms)
    risk_lines = _risk_lines(risks)
    case_line = _first_sentence(case_story.replace("\n", " ")) if case_story else ""
    if case_line.lower().startswith("then: "):
        case_line = case_line.split(":", 1)[-1].strip()

    pilot_description = _clean_text(
        bundle.get("letter_tldr")
        or bundle.get("letter_primary_cta")
        or fast_stack.get("next_30_days")
        or (operator_moves.get("immediate") or [""])[0]
    )
    pilot_sentences = _pilot_sentences(pilot_spec or {}, metric_spec or {}, pilot_description)
    pilot_body = _paragraph(*pilot_sentences)

    guardrail_clauses = _guardrail_clauses(pilot_spec, metric_spec)
    measurement_lines = [
        _sentence("By week three the readout should be boring."),
        _if_then_guardrail(guardrail_clauses),
        _sentence("If those checks fail, you thank the partner and fall back to the old play."),
    ]
    guardrail_sentence = _guardrail_sentence(guardrails)
    if guardrail_sentence:
        measurement_lines.append(guardrail_sentence)
    measurement_body = _paragraph(*[line for line in measurement_lines if line])

    story_paragraphs: List[str] = []
    opening_sentences = [line for line in [why_line or job_line, window_line, ask_line] if line]
    opening = _paragraph(*opening_sentences)
    if opening:
        story_paragraphs.append(opening)
    world_paragraph = _world_shift_paragraph(fast_stack, spine, case_line, set(opening_sentences))
    if world_paragraph:
        story_paragraphs.append(world_paragraph)
    if pilot_body:
        story_paragraphs.append(pilot_body)
    if measurement_body:
        story_paragraphs.append(measurement_body)
    role_story = _role_actions_story(role_actions or {})
    if role_story:
        story_paragraphs.append(role_story)
    consequence_lines = []
    if risk_lines:
        consequence_lines.append(_sentence("Ignore this window and you default back to blanket discounts."))
        consequence_lines.append(risk_lines[0])
    consequence = _paragraph(*[line for line in consequence_lines if line])
    if consequence:
        story_paragraphs.append(consequence)
    if not story_paragraphs:
        story_paragraphs.append("We're trading blanket discounts for collaboration windows.")

    pointer = "Open the full Intelligence report if you want the tables, decision grids, and activation kit behind this letter."
    if deep_link:
        pointer = f"Open the full [Intelligence report]({deep_link}) if you want the tables, decision grids, and activation kit behind this letter."

    evidence_regime = (bundle.get("evidence_regime") or "").lower()
    evidence_sentence = _evidence_sentence(evidence_regime)
    if evidence_sentence:
        standfirst = _paragraph(standfirst, evidence_sentence)

    standfirst = _final_cleanup(standfirst)
    story_paragraphs = [_final_cleanup(paragraph) for paragraph in story_paragraphs if paragraph]

    narrative = {
        "standfirst": standfirst or "We're trading blanket discounts for collaboration windows.",
        "sections": [],
        "story_paragraphs": story_paragraphs,
        "mechanism_lines": mechanism_text,
        "risk_lines": risk_lines,
        "watch_metrics": watch_metrics,
        "intelligence_pointer": pointer,
        "evidence_line": evidence_sentence,
    }
    return narrative


def build_market_path_context(
    report_bundle: Dict[str, Any],
    deep_link: Optional[str] = None,
    artifact_links: Optional[List[Dict[str, str]]] = None,
    report_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Build shared context for Market-Path dossier renderers."""

    signals = report_bundle.get("signals") or []
    quant = report_bundle.get("quant") or {}
    sections = report_bundle.get("sections") or {}
    time_window = report_bundle.get("time_window") or {}
    pilot_spec = report_bundle.get("pilot_spec") or {}
    metric_spec = report_bundle.get("metric_spec") or {}
    role_actions = report_bundle.get("role_actions") or {}
    if not isinstance(pilot_spec, dict):
        pilot_spec = {}
    if not isinstance(metric_spec, dict):
        metric_spec = {}
    if not isinstance(role_actions, dict):
        role_actions = {}
    spec_version = report_bundle.get("spec_version")
    if spec_version and spec_version not in {"v1"}:
        raise ValueError(f"Unsupported spec version: {spec_version}")
    spec_notes = report_bundle.get("spec_notes") or []
    spec_ok = bool(report_bundle.get("spec_ok", True))

    title = _display_title(report_bundle.get("title") or report_bundle.get("query") or "Market Report")
    subtitle = _clean_text(report_bundle.get("hook_line") or report_bundle.get("letter_subtitle") or (report_bundle.get("highlights") or [""])[0])
    exec_take = _build_exec_take(report_bundle, signals, quant)
    core_signal = signals[0] if signals else {}
    core_signal_block = {
        "name": _clean_text(core_signal.get("name") or core_signal.get("text") or "Signal"),
        "summary": _clean_text(core_signal.get("text") or report_bundle.get("executive_summary")),
        "mechanism": _clean_text(core_signal.get("description") or core_signal.get("operator_move")),
        "analogy": f"It behaves like a timing switchboard for the {core_signal.get('category', 'market').lower()} teams." if core_signal else "Treat it like a timing switchboard for operators.",
        "diagram": "Sketch the compressed window with operators gating demand like an air traffic stack.",
    }

    measurement = _measurement_from_spec(metric_spec, quant, time_window)

    signals_digest = []
    for signal in signals[:5]:
        signals_digest.append(
            {
                "name": _clean_text(signal.get("name") or signal.get("text") or "Signal"),
                "category": _clean_text(signal.get("category") or "Signal"),
                "operator_move": _clean_text(signal.get("operator_move") or ""),
                "time_horizon": _clean_text(signal.get("time_horizon") or "now"),
                "scan": _clean_text(signal.get("operator_scan") or signal.get("spine_hook") or ""),
            }
        )

    confidence = report_bundle.get("confidence") or {}
    read_time = report_bundle.get("read_time_minutes") or STIConfig.TARGET_READ_TIME_MINUTES
    comparison = _comparison_blocks(report_bundle)
    mechanisms = _mechanism_rows(sections, signals)
    operator_moves = _operator_moves(report_bundle, sections)
    risks = _risk_rows(sections)
    case_story = _case_story(report_bundle, sections)
    guardrails = _guardrails_text(report_bundle, time_window)
    watch_metrics = _watch_metrics(measurement, metric_spec, pilot_spec)
    coherence_issues = report_bundle.get("pilot_coherence_issues") or []
    hook_line = _clean_text(report_bundle.get("hook_line") or (report_bundle.get("highlights") or [""])[0])
    narrative = _build_narrative(
        report_bundle,
        signals,
        guardrails,
        case_story,
        operator_moves,
        watch_metrics,
        mechanisms,
        risks,
        measurement,
        deep_link,
        pilot_spec,
        role_actions,
        metric_spec,
        coherence_issues,
    )

    context = {
        "title": title,
        "subtitle": subtitle,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "exec_take": exec_take,
        "core_signal": core_signal_block,
        "mechanisms": mechanisms,
        "measurement": measurement,
        "operator_moves": operator_moves,
        "risks": risks,
        "case_story": case_story,
        "closing_frame": "",
        "mental_model": _clean_text((report_bundle.get("highlights") or ["Hold the guardrails."])[-1]),
        "guardrails": guardrails,
        "sources": _summarize_sources(report_bundle.get("sources") or []),
        "confidence": confidence,
        "confidence_line": _confidence_line(confidence),
        "signals_digest": signals_digest,
        "time_window_label": _time_window_label(time_window),
        "region": _clean_text(report_bundle.get("region") or "US"),
        "read_time": read_time,
        "read_time_minutes": read_time,
        "deep_link": deep_link,
        "artifact_links": artifact_links or [],
        "fast_path": report_bundle.get("fast_path") or {},
        "fast_stack": report_bundle.get("fast_stack") or {},
        "spine": report_bundle.get("spine") or {},
        "decision_map": comparison["approaches"],
        "buyer_guide": comparison["buyers"],
        "typst_visuals": _build_typst_visuals(report_dir, report_bundle),
        "hook_line": hook_line,
        "narrative": narrative,
        "evidence_note": report_bundle.get("evidence_note", ""),
        "evidence_regime": report_bundle.get("evidence_regime", "healthy"),
        "pilot_spec": pilot_spec,
        "metric_spec": metric_spec,
        "role_actions": role_actions,
        "pilot_coherence_issues": coherence_issues,
        "spec_note": "; ".join(spec_notes) if isinstance(spec_notes, list) else "",
        "spec_ok": spec_ok,
    }
    closing_signal = _clean_text(core_signal_block["name"])
    if closing_signal.lower() in {"", "signal", "the lead signal"}:
        closing_signal = "this signal"
    top_move_line = _clean_text((report_bundle.get("top_operator_moves") or [""])[0]) or "the disciplined move"
    top_move_line = top_move_line.rstrip(".")
    context["closing_frame"] = f"If {closing_signal} holds, {top_move_line} becomes the disciplined move."
    return context


def _build_typst_visuals(report_dir: Optional[str], report_bundle: Dict[str, Any]) -> Dict[str, str]:
    if not report_dir:
        return {}
    base = Path(report_dir)
    if not base.exists():
        return {}
    try:
        converter = HTMLConverterAgent()
    except Exception:
        return {}
    try:
        image_context = converter.build_image_context(report_dir, report_bundle.get("metadata") or {})
    except Exception:
        return {}
    visuals: Dict[str, str] = {}
    hero = image_context.get("hero") or {}
    anchor = hero.get("anchor_section") if isinstance(hero, dict) else None
    if anchor:
        snippet = _typst_figure_snippet(base, hero)
        if snippet:
            visuals[anchor] = snippet
    for entry in image_context.get("sections") or []:
        anchor = entry.get("anchor_section")
        if not anchor or anchor in visuals:
            continue
        snippet = _typst_figure_snippet(base, entry)
        if snippet:
            visuals[anchor] = snippet
    if visuals:
        logger.info("Typst visuals assigned: %s", sorted(visuals.keys()))
    else:
        logger.info("No Typst visuals available for %s", report_dir)
    return visuals


def _typst_figure_snippet(base: Path, image: Dict[str, Any]) -> str:
    src = image.get("src")
    if not src:
        return ""
    abs_src = (base / src).resolve()
    label = _clean_text(image.get("label") or image.get("anchor_section") or "")
    description = _clean_text(image.get("description") or image.get("caption") or image.get("alt"))
    raw_metrics = image.get("metric_focus") or []
    if isinstance(raw_metrics, str):
        raw_iterable = [raw_metrics]
    elif isinstance(raw_metrics, list):
        raw_iterable = raw_metrics
    else:
        raw_iterable = [raw_metrics]
    metrics: List[str] = []
    for metric in raw_iterable:
        label_metric = friendly_metric_name(metric)
        if label_metric:
            metrics.append(label_metric)
    caption_lines: List[str] = []
    if label:
        caption_lines.append(f"#strong[{label}]")
    if description:
        caption_lines.append(description)
    if metrics:
        caption_lines.append(f"#set text(size: 10pt)[Focus: {', '.join(metrics)}]")
    caption_body = "\n    ".join(caption_lines).strip()
    caption_block = caption_body if caption_body else ""
    return (
        "#figure(\n"
        f'  image("{abs_src.as_posix()}"),\n'
        "  caption: [\n"
        f"    {caption_block}\n"
        "  ],\n"
        ")\n"
    )

## generate_signal_map (servers/analysis_server.py:119)

```
        f"""
ROLE
You are the Brand Collab Lab's signal synthesizer for US retail.

GOAL
Select up to six on-spine signals that move the collaboration thesis forward and tell a simple story about how the world is shifting for operators. Push everything weaker or adjacent into an appendix with a short reason. Always cite source IDs.

SCOPE
{json.dumps(scope)}

INPUTS
SOURCES:
{source_digest}

TASK
0. Before listing signals, define the operator job for this report:
   - operator_job_story: one sentence in plain language framed as the job the operator is trying to get done ("How to [achieve X] without [tradeoff] in [time window]"). Write it as if it were the opening sentence of a Paul Graham essay: use "you" or "we", state the tension bluntly, no acronyms, no buzzwords.
   - search_shaped_variants: 3–5 ways a senior operator might search or brief their team about this job. Write them like subject lines or Slack searches a real operator would type, with pronouns and verbs, zero marketing jargon.

1. Read the scope and sources.
2. Publish ≤6 signals that reinforce the scope, are testable by operators, and together form a coherent narrative spine (what is changing, why it matters, and where the leverage sits).
3. Anything that misses the gate (weak strength, low US fit, off thesis) goes to the appendix with a reason.
4. Capture quick-scan hooks so other agents can maintain the same narrative spine across all artifacts.

PUBLISHED SIGNAL FIELDS
Each signal in "signals" MUST include:
- category: one of {', '.join(STIConfig.SIGNAL_FAMILIES)}
- name: concise, title case
- description: exactly 2 sentences, newsroom tone
  • Sentence 1: what is happening at a high level.
  • Sentence 2: why it matters or what is changing for operators.
- operator_move: single imperative sentence in {OPERATOR_MOVE_TONE} that suggests a test, not a full playbook.
- operator_scan: one line that starts with a verb (≤14 words) summarizing what to watch or test.
- spine_hook: ≤12-word "what is happening" line to anchor the spine.
- time_horizon: "now" | "6-week" | "quarter"
- strength: float 0–1
- US_fit: float 0–1
- operationality: float 0–1
- support: array of source IDs
- on_spine: true | false
- quant_support: "none" | "light" | "strong"
- source_grade: "A" | "B" | "C" | "D"

APPENDIX ENTRY FIELDS
- name: short label
- reason: why it was demoted (e.g., "strength < 0.78", "non-US").

GATE
Only publish a signal if strength ≥ {max(STIConfig.SIGNAL_MIN_STRENGTH, 0.78)} AND US_fit ≥ {STIConfig.SIGNAL_MIN_US_FIT}. Everything else goes to the appendix.

STYLE GUARDRAILS
- Use plain, executive-readable language.
- Write `operator_job_story` like an honest opening line from a founder memo—direct, slightly surprising, and personal.
- Write `search_shaped_variants` the way operators actually ask questions, not as SEO keywords.
- When writing `operator_notes` or `spine_hook`, lean into a candid peer-to-peer voice; it's acceptable to use "you" or "we" if it clarifies who needs to act.
- Do not leak internal ids or snake_case metric names into user-facing text; use human labels or natural phrases when you must reference measurement.
- Treat any example text in this prompt as illustrative only. Do not copy example wordings into your output. Compose wording directly from the scope and sources.

OUTPUT JSON
Return ONLY JSON shaped like:
{{
    "operator_job_story": "One-sentence operator job in plain language.",
    "search_shaped_variants": ["how to ...", "how to ..."],
    "signals": [{{ ...fields above... }}],
    "appendix": [{{"name": "", "reason": ""}}],
    "operator_notes": "Short note connecting these signals to collaboration choices and flagging any competing approaches that show up in the research."
}}
"""
```

## generate_deep_analysis (servers/analysis_server.py:202)

```
        f"""
ROLE
Write the Deep Analysis section so it feels like one ruthless narrative, not a list of disjointed notes. Write as if you were explaining this to a smart founder friend over coffee:
- Use plain language, short sentences, and concrete examples.
- It's acceptable to use "you" and "we" when it clarifies who is acting.
- You may briefly show your reasoning process when that helps the reader trust the conclusion.

GOAL
Deliver 3–4 investigative subsections that cover the narrative spine (what → so_what → now_what) and end with a clear instruction on what to instrument next.

TASK
Anchor every subsection to the operator job and the comparison approaches:
- At least one "what" or "so_what" section must clarify how competing approaches behave along a key axis (margin, foot-traffic lift, media value, loyalty performance, etc.).
- Call out what breaks or holds when moving from one approach to another so the comparison map can use it later.
- Focus each subsection on explaining how the world is changing and what that implies, then only secondarily on the specific tests.

Each subsection MUST include:
- title: short headline
- spine_position: "what" | "so_what" | "now_what"
- priority: 1 (highest) to 3 (lower) so we can sort
- scan_line: ≤14 words, bold-friendly summary
- insight: 2–3 sentences with citations in [^N] format
    • Sentence 1: core observation about how the system behaves or is changing.
    • Sentence 2: mechanism or second-order effect.
    • Optional sentence 3: contrast between approaches or a data-backed implication.
    • Make the first or second sentence feel like something a practitioner might actually say out loud; avoid generic slide language.
- operator_note: dense instruction in plain language (no schema jargon).
- instrument_next: sentence starting with "Instrument..." that names what to measure and compare.
- citations: source IDs

Close with a summary paragraph (3–5 sentences) that could stand alone as the ending to a short essay: restate how the world is shifting, say what the reader should now believe about the job (not just the pilot), and directly address "you" once or twice if it helps land the implication.

OUTPUT JSON
{{
    "deep_analysis": {{
        "sections": [
            {{
                "title": "Systems signal",
                "spine_position": "what",
                "priority": 1,
                "scan_line": "Short scan line",
                "insight": "Three-sentence paragraph with [^1][^3].",
                "operator_note": "Direct instruction.",
                "instrument_next": "Instrument ...",
                "citations": [1, 3]
            }}
        ],
        "summary": "3–5 sentence connective paragraph that reads like a short essay conclusion."
    }}
}}

INPUTS
SOURCES:
{_sources_digest(sources)}

SIGNAL MAP:
{_signals_digest(signals)}

QUANT ANCHORS:
{_quant_digest(quant)}

SCOPE:
{json.dumps(scope)}

OPERATOR JOB STORY:
{scope.get("operator_job_story") or "Not provided"}

SEARCH-SHAPED VARIANTS:
{", ".join(scope.get("search_shaped_variants", [])) or "Not provided"}

APPROACH HINTS:
{", ".join(scope.get("approach_hints", [])) or "Not provided"}

STYLE GUARDRAILS
- Do not coin proprietary concept names, slide outlines, or taglines.
- Keep phrasing descriptive, operator-focused, and practical.
- When referencing metrics, prefer natural language labels over internal ids.
- Treat any example text in this prompt as illustrative only. Do not copy example wordings into your output.
"""
```

## generate_pattern_matches (servers/analysis_server.py:294)

```
        f"""
ROLE
Map precedent so operators can see "then vs now" and what to test next.

TASK
Blend historical proof-points with contemporary analogs. For each pattern include:
- label: short descriptor
- then: one sentence describing the historical example
- now: one sentence describing the analogous move now
- operator_leap: one sentence on the test operators should run
- supports_approach: optional string naming the approach this pattern reinforces (for example, an approach_name from the comparison map)
- citations: source IDs

If no clear approach mapping exists, set supports_approach to an empty string.

STYLE
- Write like you are telling a quick story to an exec: concrete, non-technical, no internal ids.
- Make the operator_leap something that could realistically fit in a one-line experiment brief.
- Write `then` and `now` as tiny stories with actors, actions, and consequences so the contrast is vivid.
- Swap generic phrases ("a leading retailer") for descriptive operator types whenever the sources allow.
- Keep `operator_leap` brutally specific about the next test.
- Do not reuse any example wording from this prompt in your output.

OUTPUT JSON
{{
    "pattern_matches": [
        {{
            "label": "Example pattern label",
            "then": "Historical precedent sentence.",
            "now": "Current analog sentence.",
            "operator_leap": "Direct instruction on what to test now.",
            "supports_approach": "",
            "citations": [2, 4]
        }}
    ]
}}

SOURCES:
{_sources_digest(sources)}

SIGNAL MAP:
{_signals_digest(signals)}

QUANT HINTS:
{_quant_digest(quant)}

SCOPE:
{json.dumps(scope)}
"""
```

## generate_brand_outcomes (servers/analysis_server.py:357)

```
        f"""
ROLE
Translate signals into concrete brand/operator outcomes.

GOAL
Describe up to four shifts collaboration teams can act on immediately, with clear ownership, time horizon, and the commercial lever impacted.

TASK
Use the operator job story (below) as the north star:
- At least one outcome must explicitly complete the operator job story (for example, "move 20% of demand into the earlier window without crushing margin").
- When you describe impact, tie it to metrics from the unified target pack whenever possible (foot-traffic uplift, early-window share, CPA, redemption rates, etc.).
- Keep copy high-level enough that it could stand in a strategy memo, while still being specific about the lever and horizon.
- Write each `description` as a tiny essay paragraph: one clear claim about what changes, one sentence on why, optional third sentence on how the operator would notice it in the numbers.

Each outcome MUST include:
- title
- description: short paragraph with citations [^id]
- impact: commercial lever (loyalty, throughput, incremental margin, etc.)
- time_horizon: for example, "next 90 days", "holiday 2025"
- owner: team accountable (Retail ops, Partnerships, CRM, etc.)
- citations: source IDs

Avoid proprietary concept names, slide outlines, or campaign taglines.

Do not copy any example sentences from this prompt into your output. Write descriptions directly from the research.

OUTPUT JSON
{{
    "brand_outcomes": [
        {{
            "title": "Outcome title",
            "description": "Short paragraph with operator tone [^1][^2]",
            "impact": "Metric or lever impacted",
            "time_horizon": "next 90 days",
            "owner": "Retail ops",
            "citations": [1, 2]
        }}
    ]
}}

SOURCES:
{_sources_digest(sources)}

SIGNAL MAP:
{_signals_digest(signals)}

QUANT HINTS:
{_quant_digest(quant)}

SCOPE:
{json.dumps(scope)}

OPERATOR JOB STORY:
{scope.get("operator_job_story") or "Not provided"}

UNIFIED TARGET PACK (if provided):
{json.dumps(scope.get("unified_target_pack", {}))}
"""
```

## generate_quant_blocks (servers/analysis_server.py:429)

```
        f"""
ROLE
You are the Quantifier.

GOAL
Surface the hard numbers (observed and target) that prove whether the operator job story is working, while keeping the unified target pack (when provided) front and center.

UNIFIED TARGET PACK
You may receive a structured object describing the target metrics for this thesis (foot-traffic uplift, early-window share, CPA, redemption rates, etc.).
When it exists, use those targets as the basis for anchors and the measurement plan. When it is missing, infer explicit plan targets directly from the scope and signal map.

TASK
- Pull at least two anchors grounded in credible sources. Mark each as "observed" or "target" and tag whether it is base or stretch.
- Prioritize anchors that directly prove or disprove the operator job story.
- Limit anchors to ≤4 entries.
- Limit measurement_plan to ≤4 entries and include the paired-metric item (buyer activity share vs promo intensity) when it is relevant.
- When data is missing, encode it explicitly as a "plan" target with a clear owner.
- Provide a single-line `spine_hook` summarizing how success is measured ("how we know it worked").

OUTPUT JSON
{{
    "spine_hook": "One-line measurement spine hook.",
    "anchors": [
        {{
            "id": "Q1",
            "headline": "Plain-English label",
            "topic": "Example topic",
            "value_low": 2.9,
            "value_high": 3.4,
            "unit": "% YoY",
            "status": "observed" | "target",
            "band": "base" | "stretch",
            "owner": "Team",
            "expression": "Example expression",
            "source_ids": [3],
            "applies_to_signals": ["S1", "S2"]
        }}
    ],
    "measurement_plan": [
        {{
            "id": "M1",
            "metric": "Example metric",
            "expression": "Example expression",
            "owner": "Example owner",
            "timeframe": "Example timeframe",
            "status": "plan",
            "why_it_matters": "Plain language sentence referencing the guardrail."
        }}
    ],
    "coverage": 0.0
}}

`coverage` must be a float between 0.0 and 1.0 (for example, 0.75).

SCOPE
{json.dumps(scope)}

OPERATOR JOB STORY:
{scope.get("operator_job_story") or "Not provided"}

UNIFIED TARGET PACK (if provided):
{json.dumps(scope.get("unified_target_pack", {}))}

SOURCES:
{_sources_digest(sources)}

SIGNALS:
{_signals_digest(signals)}

STYLE
- Use labels and expressions that match the actual data and targets in this run.
- Do not copy the example labels or expressions above into your output.
"""
```

## generate_operator_specs (servers/analysis_server.py:524)

```
        f"""
ROLE
You are the operator pilot planner. Convert the scope, signals, and quant into a single shared spec.

GOAL
Publish JSON with `pilot_spec`, `metric_spec`, and `role_actions` so every artifact reuses the same facts.

PILOT SPEC RULES
- scenario: short snake_case identifier for the pilot.
- store_count: integer number of active stores/sites in the pilot.
- store_type: for example, "flagship", "tier_1_mall", "multi_market".
- duration_weeks: number of weeks for the core pilot (use 2, 4, 6, or 8 when in doubt).
- window: friendly label referencing the time window from scope.
- primary_move: single sentence describing the move using operator language.
- owner_roles: 2–4 roles that will own the pilot (Head of Retail, Head of Partnerships, Head of Marketing, Finance, etc.).
- location_radius_miles: integer radius around the flagship/market if applicable.
- key_metrics: array of metric ids that must be inside guardrails. Use ids from metric_spec.

METRIC SPEC RULES
- Dictionary keyed by snake_case metric ids.
- Each metric entry must include: label, target_range (two numeric values when possible), unit, stage (target|observed|guardrail), owner, and target_text for fallback phrasing.
- When the data only includes a single bound (e.g., "≥25%"), still populate target_range with two numbers by repeating the bound (e.g., [25, 25]) and encode the direction in target_text.
- Use unified_target_pack, quant anchors, and measurement_plan as sources; never invent numbers without notes.

ROLE ACTIONS
- At minimum, include keys for "Head of Retail", "Head of Partnerships", and "Finance". Add more only if owner_roles reference them.
- Each action must be a single string (no arrays or lists), one imperative sentence referencing the same pilot and metrics (for example: "Lock the pilot doors and guardrails with ops this week.").

ROLE ACTIONS OUTPUT SHAPE (example):
{{
    "Head of Retail": "Lock the pilot doors and guardrails with ops this week.",
    "Head of Partnerships": "Align creator partners and in-store layout before the two-week window.",
    "Finance": "Set CPA and margin guardrails before launch."
}}

CONSTRAINTS
- Use only the provided context; be explicit when a field is "TBD".
- Keep JSON tight and machine readable. No markdown.
- This spec will feed both an essay-like executive letter and an operator-heavy Intelligence report. Do not try to write prose here; focus on clean, consistent structure and ids.
- Do not reuse example text from this prompt in your output.

CONTEXT
- SCOPE: {json.dumps(scope)[:1800]}
- OPERATOR JOB STORY: {operator_job_story}
- SIGNAL DIGEST: {_signals_digest(signals)}
- QUANT DIGEST: {_quant_digest(quant)}
- MEASUREMENT PLAN: {json.dumps(measurement_plan)[:1200]}
- ACTIVATION KIT: {json.dumps(activation)[:1200]}
"""
```

## generate_activation_kit (servers/analysis_server.py:584)

```
        f"""
    ROLE
    Design the Activation Kit cards for the Brand Collab Lab handoff.

    GOAL
    Deliver merged plays across {', '.join(STIConfig.ACTIVATION_PILLARS)} with a clean display layer for humans and a detailed ops layer for automation.

    TASK
    1. Merge overlapping placement ideas into a single play with `placement_options`.
    2. Use descriptive, non-proprietary labels.
    3. For each play, emit both a `display` block and an `ops` block:

        DISPLAY BLOCK
        - pillar
        - play_name
        - card_title (simplified headline)
        - persona
        - best_fit
        - not_for
        - thresholds_summary (sentence referencing the guardrails in plain language)
        - why_now (sentence tying to the current window/signals)
        - proof_point (signal-based)
        - approach_name (which comparison approach this play represents, drawn from the actual approaches in this run)
        - time_horizon ("immediate", "6-week", or "pilot")
        - placement_options (1–3 strings)

        OPS BLOCK
        - operator_owner
        - collaborator
        - collab_type
        - thresholds (structured values referencing guardrails)
        - prerequisites
        - target_map (3–5 entries: org_type, role, why_now)
        - cadence: exactly 3 touches (each with day, subject ≤60 chars, narrative ≤1 sentence, CTA starting with a verb)
        - zero_new_sku (true/false)
        - ops_drag (low/medium/high)
        - strategy_tag (mirror of approach_name for the ops layer)

    4. Where possible, tag each play with the comparison approach it best represents so downstream decision maps can group them.
    5. Write the display copy so it could sit on a one-page brief or slide without feeling like a schema dump.

    OUTPUT JSON
    {{
        "activation_kit": [
            {{
                "display": {{
                    "pillar": "",
                    "play_name": "",
                    "card_title": "",
                    "persona": "",
                    "best_fit": "",
                    "not_for": "",
                    "thresholds_summary": "",
                    "why_now": "",
                    "proof_point": "",
                    "approach_name": "",
                    "time_horizon": "immediate",
                    "placement_options": ["Flagship window"]
                }},
                "ops": {{
                    "operator_owner": "",
                    "collaborator": "",
                    "collab_type": "brand↔operator",
                    "thresholds": {{"cpa": "≤0.80× baseline"}},
                    "prerequisites": ["Door counts"],
                    "target_map": [{{"org_type": "Retailer", "role": "Retail ops", "why_now": "Vacant bay"}}],
                    "cadence": [
                        {{"day": "0", "subject": "Kickoff", "narrative": "One sentence", "CTA": "Book the pilot"}},
                        {{"day": "3", "subject": "Reconfirm", "narrative": "One sentence", "CTA": "Share instrumentation"}},
                        {{"day": "7", "subject": "Close", "narrative": "One sentence", "CTA": "Sign off"}}
                    ],
                    "zero_new_sku": true,
                    "ops_drag": "low",
                    "strategy_tag": ""
                }}
            }}
        ]
    }}

    SIGNAL MAP:
    {_signals_digest(signals)}

    SECTION SUMMARY:
    {json.dumps(sections)[:1500]}

    QUANT ANCHORS:
    {_quant_digest(quant)}

    GUARDRAILS
    - Mini-burst success if event CPA ≤ {STIConfig.ACTIVATION_THRESHOLDS['mini_burst']['cpa']}x baseline and redemption ≥ {int(STIConfig.ACTIVATION_THRESHOLDS['mini_burst']['redemption']*100)}%.
    - Staged discount success if margin per order ≥ baseline minus {abs(STIConfig.ACTIVATION_THRESHOLDS['staged_discount']['margin_delta_bps'])} bps and 90-day repeat ≥ baseline.

    Do not reuse example phrases from this prompt. Fill values from the actual report context.
    """
```

## generate_comparison_map (servers/analysis_server.py:701)

```
        f"""
ROLE
You are the STI comparison map architect. Convert the job story, signal stack, and risk intel into a decision map operators can act on.

OPERATOR JOB STORY:
{operator_job_story}

APPROACH HINTS:
{approach_hints}

SEARCH-SHAPED VARIANTS:
{search_variants}

SIGNAL DIGEST:
{_signals_digest(signals)}

PATTERN MATCHES:
{json.dumps(pattern_matches)[:1200]}

BRAND OUTCOMES:
{json.dumps(brand_outcomes)[:1200]}

RISK RADAR:
{json.dumps(risk_radar)[:1200]}

ACTIVATION PLAYS:
{json.dumps(activation)[:1200]}

TASK
1. Build `approach_map` covering up to three distinct approaches (pull from APPROACH HINTS or infer from signals). Each entry must include:
   - Use the same signal IDs emitted by `generate_signal_map` (for example, "S1") when filling supporting_signals.
   - approach_name
   - who_it_is_for (plain sentence naming the operator profile)
   - strengths (≤2 sentences referencing actual signals/outcomes)
   - failure_modes (≤2 sentences referencing risks/patterns)
   - when_to_choose (one sentence trigger)
   - when_not_to_choose (one sentence guardrail)
   - supporting_signals (array of signal IDs such as ["S1", "S3"])
   - key_risks (array of risk IDs or names)
   - key_metrics (array naming the metrics that prove it worked, using human labels not snake_case ids)
2. Build a `buyer_guide` with 2–4 commercial options (agency, in-house studio sprint, pop-up collab, etc.). Each option must include:
   - option_name
   - best_for
   - not_for
   - commercial_shape (describe payment/window)
   - proof_needed_before_scaling
   - where_STI_fits (how STI or the operator plugs in)
3. Keep copy short, factual, and grounded in the provided data. Write for an executive scanning on a phone, not for a schema browser. When describing `strengths` or `failure_modes`, use the voice of a trusted peer warning another operator—be candid about where each approach breaks.

OUTPUT JSON
{{
    "approach_map": [
        {{
            "approach_name": "Example approach name",
            "who_it_is_for": "Operators with a specific capability profile.",
            "strengths": "Two sentences citing signals and outcomes.",
            "failure_modes": "Two sentences referencing risk entries.",
            "when_to_choose": "One sentence trigger.",
            "when_not_to_choose": "One sentence guardrail.",
            "supporting_signals": ["S1", "S4"],
            "key_risks": ["Example risk"],
            "key_metrics": ["Example metric label"]
        }}
    ],
    "buyer_guide": [
        {{
            "option_name": "Traditional agency retainer",
            "best_for": "Brands needing turnkey creative deployment across many doors.",
            "not_for": "Operators with no budget or time for retained teams.",
            "commercial_shape": "Describe fee and cadence (for example, monthly retainer plus production costs).",
            "proof_needed_before_scaling": "Evidence required before scaling (for example, 15% lift in two pilots).",
            "where_STI_fits": "How STI hands the playbook and instrumentation to that option."
        }}
    ]
}}

Do not reuse example text above in your output. Fill content from this run's signals, risks, and outcomes.
"""
```

## generate_risk_radar (servers/analysis_server.py:792)

```
        f"""
    Build the Risk Radar. Highlight up to four failure modes and include scan-friendly metadata:
        - risk_name
        - scan_line (for example, "Risk: concise phrase capturing the failure mode")
        - trigger (what causes it)
        - detection (what to instrument)
        - mitigation (operator move starting with a verb)
        - severity: 1 (low) to 3 (high)
        - likelihood: 1 (low) to 3 (high)
        - approach_exposure: which comparison approach is most exposed (or "all" if universal)
        - citations

    If the risk clearly ties to one approach, set approach_exposure to that approach_name; otherwise use "all".

    Style: keep each entry tight enough that it could fit in a margin note of the letter, but remember the full mitigation will be unpacked in the Intelligence report. Start mitigation lines with a blunt verb and spell out what to actually do, not what to "consider".

    Return JSON: {{"risk_radar": [{{...}}]}}

    Do not copy any example phrasing from this prompt into your risk entries.

    SIGNAL MAP:
    {_signals_digest(signals)}

    SECTION HINTS:
    {json.dumps(sections)[:1500]}
    """
```

## generate_future_outlook (servers/analysis_server.py:832)

```
        f"""
    Draft outlook scenarios for 6-month and 12-month horizons (only add 24-month if there is overwhelming evidence). Each horizon must answer, "If the operator job story is true and we act (or fail to act), what happens in this window?" and include:
        - headline
        - scan_line: "If true, we will see X within Y months"
        - description: exactly 3 sentences with citations [^id]
            • Sentence 1 should feel like the opening line of an essay scenario—describe the world the operator wakes up in.
            • Sentence 2 should explain the mechanism in everyday language.
            • Sentence 3 should say plainly what the operator will celebrate or regret if they chose the dominant approach.
        - operator_watch: the single most important metric to observe
        - collaboration_upside: what success looks like in that horizon
        - dominant_approach: which comparison approach is most likely in this scenario (or "mixed" if unclear)
        - confidence: 0–1
        - citations

    Treat these as narrative scenarios: explain how the world looks and behaves if this play becomes the norm, not just what the next pilot looks like.

    Return JSON: {{
        "future_outlook": [
            {{
                "horizon": "6-month",
                "headline": "Short title",
                "scan_line": "If true, we will see ...",
                "description": "Three sentences with citations [^1].",
                "operator_watch": "Metric to instrument",
                "collaboration_upside": "What success looks like",
                "dominant_approach": "example_approach_name",
                "confidence": 0.8,
                "citations": [1]
            }}
        ]
    }}

    Do not reuse example wording; write each scenario from the actual signals and scope.

    SIGNAL MAP:
    {_signals_digest(signals)}

    SECTION HINTS:
    {json.dumps(sections)[:1500]}

    OPERATOR JOB STORY:
    {scope.get("operator_job_story") or "Not provided"}

    APPROACH HINTS:
    {", ".join(scope.get("approach_hints", [])) or "Not provided"}
    """
```

## generate_executive_letter (servers/analysis_server.py:886)

```
        f"""
    Write a short essay in the voice of a founder talking to a Head of Retail, CMO, or CFO they respect. It should read like a Paul Graham essay: conversational, blunt, curious, grounded in specific observations, with one disciplined experiment at the end. No AI mentions.

    Use the JSON schema below and obey every constraint:

    {{
        "title": "Short report title",
        "subtitle": "One-line promise",
        "tldr": "Optional single sentence outcome + ask",
        "sections": [
            {{"name": "What we are seeing", "body": "..."}},
            {{"name": "The move", "body": "..."}},
            {{"name": "Size of prize", "body": "..."}},
            {{"name": "Risks", "body": "..."}},
            {{"name": "Decision requested", "body": "..."}}
        ],
        "bullets_investable": ["exactly 3 short bullets"],
        "bullets_targets": ["exactly 3 bullets with explicit numbers and time windows"],
        "primary_cta": "One-sentence ask for the exec",
        "email_subject": "Suggested internal forward subject line"
    }}

    Requirements:
    - Total length target 450-550 words; hard cap 600.
    - Each section body must be 2-4 sentences, no inline bullets.
    - Bold only 3-5 key numbers and 1-2 decisive phrases across the entire letter.
    - `bullets_investable` must contain exactly 3 items explaining why the window matters now at a world and business level, not as pilot configuration.
    - `bullets_targets` must contain exactly 3 items, each with at least one numeric value AND a time window (for example, "two-week window", "within 30 days"), drawn from metric_spec or quant targets.
    - Voice: decisive, confident, plain language, speaking to fellow executives about a two-to-eight week test.
    - You may use "I", "we", and "you" when it helps the argument feel direct and honest.
    - Prefer simple words over jargon: say stores, customers, extra dollar, holiday window, visits, cost.
    - In "What we are seeing" and "The move", start from a concrete observation before zooming out; avoid opening with pure metric recaps.
    - When in tension, favor essay-like phrasing over newsroom phrasing. It should feel like something a thoughtful founder might email a peer on a Sunday morning.
    - Follow the `tone_hint` in the provided context if present (for example, "slightly impatient but constructive").
    - Use the provided context only; do not invent new data.
    - The `Decision requested` section must end with the exact `primary_cta` string verbatim.
    - Return JSON only; do not output prose outside the JSON object. Inside the string fields you may use Markdown-style **bold** for at most 3-5 numbers and 1-2 decisive phrases.

    Narrative guardrails:
    - Use `operator_job_story` to frame the title, subtitle, and "What we are seeing" so the operator problem is explicit.
    - Treat this as a stand-alone essay: explain what changed in the operator's environment, why it matters for their P&L and teams, and what disciplined move follows.
    - In "What we are seeing", begin with one oddly specific observation (from signals or sections) and then generalize.
    - In "The move", explain the move as a simple story ("If you are in X, do Y for two weeks and watch Z") instead of bullet-style phrasing.
    - In "Size of prize", tie numbers to lived experience—explain what the lift would feel like in stores, not just the percentage.
    - In "Risks", talk the way a good investor would: state what breaks first and how you'll notice.
    - Make "Decision requested" read like the closing paragraph of an essay: restate the bet, then the ask, using the same plain words from the opening. End with the `primary_cta`.
    - If `approach_names` are provided, state clearly which approach you recommend inside "The move" and why it fits this operator, in words an exec would actually use.
    - When `pilot_spec` or `metric_spec` is provided, use them to stay consistent on duration, store_count/sites, window labels, and 1–3 key metrics, but:
        • Do NOT dump the full pilot configuration or every guardrail into the letter.
        • Mention the pilot in at most 2–3 sentences, in natural language (for example, "a four-week test in a small set of flagship sites").
        • Summarize measurement in words (for example, "keep acquisition cost near baseline while the early window takes a bigger share"), not as a list of schema fields.
    - Tie "Size of prize" and `bullets_targets` to `quant_targets` or `unified_target_pack` metrics, but keep copy high-level and story-driven.
    - Use `role_actions` when writing "Decision requested" so each role hears their move, but paraphrase into prose instead of copying schema lines (no "Head of Retail:" prefixes; work them into sentences).
    - Do not leak internal ids or snake_case metric names into the letter; always use human labels or plain English.
    - Assume the detailed pilot spec and full measurement spine live in the Intelligence report. In this letter, point to the pilot as the canonical example, not as a configuration dump.
    - Do not reuse any example phrases from this prompt in the letter. Compose all language directly from this report's context and evidence.

    CONTEXT:
    {json.dumps(context)[:8000]}

    PILOT + METRICS (if provided):
    {json.dumps({"pilot_spec": context.get("pilot_spec"), "metric_spec": context.get("metric_spec"), "role_actions": context.get("role_actions")})[:2000]}
"""
```

## generate_image_prompt_bundle (servers/analysis_server.py:953)

```
        f"""
    You are the STI image-brief generator. The user is giving you the full report bundle.
    Produce FIVE polished editorial image prompts plus alt text. Follow the rules:

    GENERAL BRAND RULES
    - Optimistic editorial, bright daylight, confident highlights, generous negative space.
    - No UI, no charts, no overlays, no text.
    - Mention operators or tactile props tied to this report's content.
    - Alt text ≤ 120 characters.
    - Visuals should feel like clean editorial illustrations for an essay, not campaign key art.

    IMAGES TO GENERATE (in order):
    1. Hero: describe the decisive operator action implied by this report. Include the key theme abstractly and leave space compositionally for a potential CTA.
    2. Signal Map: abstract arcs or nodes showing timing windows referencing actual signals.
    3. Case Study 1: scene, persona, moment, and props tied to the first major assertion.
    4. Case Study 2: scene, persona, moment, and props tied to a different mechanism or assertion.
    5. Conclusion: forward-looking image showing an activation outcome or future horizon.

    OUTPUT JSON ARRAY EXACTLY:
    [
      {{"type": "hero", "prompt": "...", "alt": "..."}},
      {{"type": "signal_map", "prompt": "...", "alt": "..."}},
      {{"type": "case_study_1", "prompt": "...", "alt": "..."}},
      {{"type": "case_study_2", "prompt": "...", "alt": "..."}},
      {{"type": "conclusion", "prompt": "...", "alt": "..."}}
    ]

    Each prompt must be 2–3 sentences, referencing real data or tests (cite the specific signal, play, or section name inside the text). Alt text must describe the scene and action plainly.

    Do not copy example phrases from this prompt. Describe scenes using the actual report bundle.

    REPORT BUNDLE:
    {json.dumps(report)[:7000]}
    """
```

## write_executive_summary (servers/analysis_server.py:1011)

```
        f"""
Deliver the executive summary for an operator audience.

CONTEXT
- SCOPE: {json.dumps(scope)}
- SIGNAL MAP: {_signals_digest(signals)}
- SECTION OVERVIEW: {json.dumps(sections)[:1500]}
- QUANT ANCHORS: {_quant_digest(quant)}
- SOURCES: {_sources_digest(sources)}

KEY INPUTS
- operator_job_story: {operator_job_story}
- approach_hints: {approach_hints}
- unified_target_pack (if present): {json.dumps(unified_pack)}

REQUIREMENTS FOR EXECUTIVE SUMMARY
- Exactly one paragraph containing 3–4 sentences, in a plain, conversational tone.
- Avoid corporate jargon unless it appears verbatim in scope.
- Sentence 1 must restate the operator_job_story in natural language so the operator problem is obvious.
- Explicitly reference 2–4 key metrics from unified_target_pack when it exists (foot-traffic uplift, early-window share, CPA, redemption, dwell time, etc.). Use the provided labels or ranges; do not invent new numbers.
- If unified_target_pack is missing, reference the most important metrics from QUANT ANCHORS instead.
- Make clear which approach you are implicitly favoring, using approach_hints to name it (for example, the primary approach in that list).
- Explain what collaboration or operator teams must do in the next 30 days in one clear clause.
- Include [^id] citations.
- DO NOT include any markdown headings (#, ##, ###) or bullet formatting inside the executive_summary field.

STRUCTURE OF EXECUTIVE SUMMARY
- Sentence 1: What is happening, framed through the operator_job_story.
- Sentence 2: Why it matters, anchored in specific metrics from unified_target_pack or quant anchors.
- Sentence 3 (optional Sentence 4): What to do in the next 30 days, plus how success will be measured and which approach carries the leverage.

OUTPUT FIELDS
Return JSON with:
{{
    "title": "Short report title (no 'Signal Report' prefix).",
    "hook_line": "One-sentence plain-English promise under the H1.",
    "executive_summary": "Single-paragraph summary (3–4 sentences) with [^id] citations.",
    "highlights": ["Three short bullets capturing concrete mechanisms or data-backed insights."],
    "top_operator_moves": [
        "Exactly three imperative sentences describing the most important moves in the next 30 days."
    ],
    "prerequisites": [
        "Minimum viable capabilities (data, instrumentation, owners) to run the tests."
    ],
    "best_fit": "One sentence describing which brands or operators this play is for.",
    "not_for": "One sentence describing who should NOT run this play.",
    "play_summary": [
        {{
            "label": "Short play label (for example, 'Early-access window')",
            "success": "Plain-English success condition tied to a metric (for example, 'traffic uplift ≥1.10×')."
        }}
    ],
    "fast_path": {{
        "sections": ["executive_summary", "highlights", "top_operator_moves", "play_summary"]
    }},
    "fast_stack": {{
        "headline": "Two-sentence fast hook summarizing job and favored approach.",
        "why_now": "Sentence explaining the timing or window from scope.",
        "next_30_days": "Sentence stating the immediate mandate and owner."
    }}
}}

GUIDELINES
- Use **bold** only for key numbers or decisive instructions inside string values (max 3–5 numbers and 1–2 phrases).
- Keep language plain, decisive, and specific to the operator_job_story; avoid proprietary taglines.
- Tie any metric references to unified_target_pack or quant anchors; do not invent new ranges.
- Do not reuse any example phrases from this prompt in your output.
"""
```

## generate_image_briefs (servers/analysis_server.py:1095)

```
        f"""
    Craft concise image briefs for the design system. Produce exactly 3–5 briefs:
        - 1 hero, 1 signal_map, up to 3 case studies (or future_outlook)
        - Polished editorial lighting with confident highlights and clean negative space
        - Operator and studio collaboration imagery, no literal UI
        - Mention composition cues (angle, subject, material)
        - Describe the underlying tension or timing symbolically instead of mandating a specific prop
        - Make every visual feel like a clean editorial illustration for an essay, not campaign key art
        - Provide alt text ≤ 120 characters that names at least one operator persona AND the action or test underway.
        - For every image set anchor_section from this list only: header, signals_and_thesis, measurement_spine, mini_case_story, deep_analysis, future_outlook. Do not invent new values.
        - slot must be one of: hero, signal_map, case_study_1, case_study_2, case_study_3, future_outlook. HTML anchors use these slot names ("<!-- image:slot -->").
        - Include metric_focus listing 1–3 metrics (footfall_lift, early_window_share, event_cpa, qr_redemption, dwell_time, partner_value, conversion_rate) that the visual reinforces.
        - Reference at least one named section, signal, or activation play in each brief so imagery stays anchored to the narrative.
        - Case Study 1 and Case Study 2 must depict different mechanisms and reference different sections or plays so the visuals stay distinct.
        - Hero image must dramatize the operator_job_story and favored approach (from approach_hints or the comparison map) with the operator visibly choosing or executing that path.
        - Signal map visual must encode at least two metrics from unified_target_pack or quant anchors inside the geometry so the measurement spine is obvious.
        - Any future_outlook or conclusion visual (anchor_section future_outlook) should depict the solved job story and explicitly reference the metric_focus values as success indicators.

    Return JSON with structured fields so the image generator can fill templates automatically:
    {{
        "image_briefs": {{
            "hero": {{
                "core_tension": "Describe the decision or timing tension to depict",
                "setting": "Environment cues",
                "persona": "Operator or studio persona involved",
                "action": "Key action",
                "urgency_symbol": "Symbol for time sensitivity",
                "props": ["Props tied to signals or plays"],
                "lighting": "Polished editorial lighting with confident highlights",
                "mood": "For example, precise, collaborative, confident",
                "anchor_section": "header",
                "metric_focus": ["Metric names the hero hints at"],
                "alt": "Alt text"
            }},
            "signal_map": {{
                "structure": "Geometry (rings, lattice, arcs, etc.)",
                "elements": ["Elements such as tokens, paths, arcs"],
                "motion": "Flow description",
                "palette": "Palette or material cues",
                "anchor_section": "signals_and_thesis",
                "metric_focus": ["Metric names the diagram emphasizes"],
                "alt": "Alt text"
            }},
            "case_studies": [
                {{
                    "scene": "Scene description",
                    "moment": "Key moment",
                    "persona": "Persona description",
                    "props": ["Props"],
                    "lighting": "Lighting description",
                    "mood": "Mood description",
                    "anchor_section": "mini_case_story",
                    "metric_focus": ["Metric names the case illustrates"],
                    "alt": "Alt text"
                }}
            ]
        }}
    }}

    USE THESE SIGNALS:
    {_signals_digest(signals)}

    SECTION CONTEXT:
    {json.dumps(sections)[:1500]}

    SOURCE HINTS:
    {_sources_digest(sources)}

    SCOPE:
    {json.dumps(scope)}

    Do not reuse example phrases from this prompt. Describe visuals based on this report's actual content.
    """
```

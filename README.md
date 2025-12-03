# STI Operator Briefing System

Focused, signal-driven intelligence for the Brand Collab Lab. The system ingests fresh sources, extracts behavioral signals, and produces dark-mode operator reports ready for studios, retailers, hospitality partners, and in-house brand teams.

## Why This Repo Exists

- **Single operator path.** No more thesis routing or academic scaffolding—every run centers on market-path collaboration outcomes.
- **Signal-first flow.** Search → Signal Map → Deep Analysis → Pattern Matches → Operator Outcomes → Activation Kit → Risk Radar → Future Outlook.
- **Market-Path dossier.** The default outputs are a memo-grade Markdown brief, a print-ready PDF, and a simplified McKinsey-style HTML report; the previous dark-mode dashboard lives on as an optional legacy renderer.
- **Minimal artifacts.** Each run saves the operator Markdown (`market_path_report.md`), the PDF dossier, raw Markdown, JSON-LD, `sources.json`, `signals.json`, `sections.json`, `metadata.json`, `images/briefs.json`, optional social content, and minimalist HTML companions for both Markdown reports.

## Key Components

| Module | Purpose |
| --- | --- |
| `enhanced_mcp_agent.py` | Collect sources via SearXNG, call MCP analysis tools, assemble the structured report bundle. |
| `servers/analysis_server.py` | FastMCP server with tools for signal map, deep analysis, activation kit, risk radar, future outlook, etc. |
| `renderers/market_path_markdown.py` | Builds the Market-Path Markdown dossier from the structured bundle. |
| `renderers/market_path_pdf.py` | Mirrors the same context into a Typst (or fallback) PDF for export. |
| `templates/article_minimal.html` + `html_converter_agent.py` | Render minimalist journalism-style HTML companions from the Markdown dossiers. |
| `file_utils.py` | Dispatches to the configured renderers, writes JSON dumps, and handles social content persistence. |
| `social_media_agent.py` | Produces LinkedIn/Twitter/Substack-ready copy using the signal map for provenance. |
| `image_generator.py` | Dark-mode prompt generation for hero + signal map + case study vignettes (OpenAI Images API). |

## Multi-Agent Pipeline

The operator workflow now mirrors the refinement plan shared by STI:

1. **Query & Scope Agent** locks topic, window, region (US) and must-answer prompts before research.
2. **Source Hunters + Authority Ranker** enrich raw hits with authority, recency, US-fit, evidence depth, and blocklist enforcement. Anything below `quality ≥ 0.70` is demoted to support.
3. **Signal Synthesizer** (via MCP) emits ≤6 signals with explicit `strength`, `US_fit`, `quant_support`, and `source_grade`. Only on-spine signals with A/B sourcing and strength ≥ 0.78 make the primary map; the rest are demoted to the appendix with reasons.
4. **Quantifier** provides structured anchors (value ranges, units, signal cross-links) plus a measurement plan so operators see both “what’s true now” and “what to instrument next.”
5. **Writer + Activation Kit Agents** assemble the report micro-structure (exec summary → top operator moves → signal map → deep analysis → outcomes → activation kit) while embedding thresholds, KPIs, and Outreach logic (target map + 3-touch cadence) for Brand Collab Lab handoff.
6. **Red Team / QA** enforces US focus, caps section counts/read time, and feeds the public confidence band (low/medium/high) that replaces opaque decimals.

## Report Structure

1. Executive Summary + highlights
2. Signal Map (Market, Technology, Cultural, Behavioral clusters)
3. Deep Analysis (3–5 investigative subsections)
4. Historical & Contemporary Pattern Matches
5. Brand & Operator Outcomes
6. Activation Kit (Brand Collab Lab handoff)
7. Risk Radar
8. Future Outlook (6/12/24 month scenarios)
9. Sources + disclosure

## Running Reports

```bash
python run_report.py "immersive retail hospitality mashups" --days 7 --trace
```

Environment prerequisites:

- `OPENAI_API_KEY`
- Optional: `SEARXNG_BASE_URL` if SearXNG is not running on `http://localhost:8080`

Outputs land in `sti_reports/sti_operator_output_<timestamp>_<query>/`.

> Need to see every step? Add `--debug` to enable verbose logging plus `--trace` to surface the raw search payloads, MCP responses, and section counts inside the log file/console.

## Configuration Highlights (`config.py`)

- `REPORT_STRUCTURE` defines the section order.
- `SIGNAL_FAMILIES` + `ACTIVATION_PILLARS` feed prompts and Market-Path labels.
- `SOURCE_DOMAIN_WEIGHTS` keep the confidence score grounded in publisher diversity.
- `REPORT_RENDERERS` toggles which renderers run (default `market_path_markdown,market_path_pdf`; append `legacy_html` for the minimalist HTML companions).
- `MARKDOWN_HTML_TEMPLATE` points to the minimal article shell used for both Markdown renderings.
- `IMAGE_BRIEF_TARGETS` instruct the image generator which vignettes to create (hero, signal map, case studies).

## Confidence Model

`confidence.py` exposes the math that prints in the report footnote:

- `average_strength` (0.4 weight)
- `coverage` across the required on-spine signals (0.3 weight)
- `quant_support` based on the anchors/measurement plan (0.2 weight)
- `contradiction_penalty` from QA/red-team flags (0.1 weight)

The Market-Path dossier still surfaces a banded verdict (“Confidence: High — strength high, coverage full, quant strong, consistency high”) instead of a raw decimal.

## Testing

`pytest` exercises confidence math, social media formatting, and the Market-Path renderers using fixture data. Tests were trimmed to match the new operator scope.

## Visual QA

Images are treated as first-class artifacts. Run the combined lint before committing regenerated reports:

```bash
make visual-check
```

This command executes:

- `visual_qc.py` – verifies anchors, required slots, and gallery fallbacks via each report's `visual_stats.json`.
- `visual_template_audit.py` – ensures every entry in `images/manifest.json` was generated with the current `TEMPLATE_VERSION`.

By default the target scans every directory under `sti_reports/`; override with `VISUAL_DIRS` if you only want to check specific runs:

```bash
VISUAL_DIRS="sti_reports/sti_operator_output_20251129_*" make visual-check
```

## What's Archived

Legacy thesis-path agents, Google Slides automation, budget/gate logic, router/blend flows, and the previous light-mode templates now live under `archive/` for reference. They are not part of the active runtime.

## Next Ideas

1. Add simple cache for SearXNG queries to reduce duplicate scraping.
2. Expose a `/reports/latest` CLI helper for quick opening.
3. Extend `social_media_agent.py` to ship Instagram carousels using the case-study images.

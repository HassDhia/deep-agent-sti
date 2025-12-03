"""Templating utilities for Market-Path renderers."""

from __future__ import annotations

from typing import Dict, Any

from jinja2 import BaseLoader, Environment

ENV = Environment(
    loader=BaseLoader(),
    autoescape=False,
    trim_blocks=True,
    lstrip_blocks=True,
    variable_start_string="[[",
    variable_end_string="]]",
)

MARKDOWN_TEMPLATE = ENV.from_string(
    """# [[ title ]]

> [[ narrative.standfirst or hook_line or exec_take ]]

_Meta: [[ time_window_label ]] · [[ region ]] · Confidence [[ confidence.band or 'Medium' ]] · ~[[ read_time or read_time_minutes ]] min{% if evidence_note %} · Evidence [[ evidence_note ]]{% endif %}_

{% if artifact_links -%}
_Formats:_ {% for link in artifact_links %}[[ "[" + link.label + "](" + link.href + ")" ]]{% if not loop.last %} · {% endif %}{% endfor %}

{% endif -%}
**Executive take**  
[[ exec_take ]]

{% for paragraph in narrative.story_paragraphs -%}
[[ paragraph ]]

{% endfor %}

[[ narrative.intelligence_pointer ]]

[[ closing_frame ]]

{% if narrative.mechanism_lines -%}
**Why this works**

{% for line in narrative.mechanism_lines -%}
- [[ line ]]
{% endfor %}
{% endif -%}

{% if narrative.risk_lines -%}
**Where it breaks**

{% for line in narrative.risk_lines -%}
- [[ line ]]
{% endfor %}
{% endif -%}

_Mental Model_  
> [[ mental_model ]]

_Sources & Confidence_  
[[ confidence_line ]]
{% for source in sources -%}
- [[ source ]]
{% endfor %}

_Generated [[ generated_at ]] · Window [[ time_window_label ]] · Region [[ region ]]_
"""
)

TYPST_TEMPLATE = ENV.from_string(
    """
#set page(paper: "letter", margin: 1in)
#set text(font: "Helvetica", size: 11pt)

= [[ title ]]
[[ subtitle ]]
{% if typst_visuals.get('header') -%}
[[ typst_visuals.get('header') ]]
{% endif %}

#quote([[ narrative.standfirst or hook_line or exec_take ]])
#strong[Meta] [[ time_window_label ]] · [[ region ]] · Confidence [[ confidence.band or 'Medium' ]] · ~[[ read_time or read_time_minutes ]] min{% if evidence_note %} · Evidence [[ evidence_note ]]{% endif %}
{% if deep_link -%}
#link("[[ deep_link ]]", "Read the full intelligence report")
{% endif %}

#strong[Executive take]
[[ exec_take ]]

{% for paragraph in narrative.story_paragraphs -%}
[[ paragraph ]]

{% endfor %}

[[ narrative.intelligence_pointer ]]

[[ closing_frame ]]

{% if narrative.mechanism_lines -%}
#strong[Why this works]
{% for line in narrative.mechanism_lines -%}
- [[ line ]]
{% endfor %}
{% endif %}

{% if narrative.risk_lines -%}
#strong[Where it breaks]
{% for line in narrative.risk_lines -%}
- [[ line ]]
{% endfor %}
{% endif %}

#strong[Mental model]
[[ mental_model ]]

#strong[Sources & confidence]
[[ confidence_line ]]
{% for source in sources -%}
- [[ source ]]
{% endfor %}

Generated [[ generated_at ]] · Window [[ time_window_label ]] · Region [[ region ]]
"""
)


def render_markdown(context: Dict[str, Any]) -> str:
    return MARKDOWN_TEMPLATE.render(**context)


def render_typst(context: Dict[str, Any]) -> str:
    return TYPST_TEMPLATE.render(**context)

"""
Analysis MCP Server

FastMCP server providing specialized analysis tools for generating
comprehensive research report sections including market analysis,
technology deep-dive, competitive landscape, and expanded lenses.
"""

import json
import os
from mcp.server.fastmcp import FastMCP
from langchain_openai import ChatOpenAI
from config import STIConfig

# Initialize FastMCP server
analysis_mcp = FastMCP("DeepAnalysis")

# Initialize LLM for analysis
# Get organization ID from environment for verified org
organization = os.getenv("OPENAI_ORGANIZATION") or getattr(STIConfig, 'OPENAI_ORGANIZATION', None)
llm_params = {
    "api_key": os.getenv("OPENAI_API_KEY"),
    "model": "gpt-5-mini-2025-08-07",
    "temperature": 0.1,
    "response_format": {"type": "json_object"}
}
if organization:
    llm_params["openai_organization"] = organization
llm = ChatOpenAI(**llm_params)


@analysis_mcp.tool()
def analyze_market(sources_json: str, signals_json: str) -> str:
    """
    Generate market analysis section covering:
    - Pricing power dynamics
    - Capital flow patterns
    - Infrastructure investment trends
    Target: ~500 words
    """
    try:
        sources = json.loads(sources_json)
        signals = json.loads(signals_json)
        
        # Combine content for analysis
        combined_content = "\n\n".join([f"Source {s['id']}: {s['content']}" for s in sources])
        signal_texts = [s.get('text', '') for s in signals]
        
        market_prompt = f"""
        Analyze the market dynamics from this content and generate a comprehensive market analysis section (~500 words).
        
        Focus on:
        1. Pricing power dynamics - who has pricing leverage and why
        2. Capital flow patterns - where money is moving and investment trends
        3. Infrastructure investment trends - what's being built and funded
        4. Market structure changes - consolidation, new entrants, exits
        5. Supply chain and operational impacts
        
        IMPORTANT: Reference ALL {len(sources)} sources in your analysis.
        Each major claim should cite specific sources using [^N] format.
        Distribute citations across: {', '.join([f"Source {s['id']} ({s['publisher']})" for s in sources])}
        
        Content: {combined_content[:4000]}
        
        Key Signals: {signal_texts}
        
        Return as JSON with this exact structure:
        {{
            "market_analysis": "Comprehensive market analysis covering pricing power, capital flows, infrastructure investment, and market structure changes. Target ~500 words with specific data points and trends. MUST cite multiple sources using [^N] format."
        }}
        """
        
        response = llm.invoke(market_prompt)
        data = json.loads(response.content)
        return data.get('market_analysis', 'Market analysis unavailable.')
        
    except Exception as e:
        return f"Error generating market analysis: {str(e)}"


@analysis_mcp.tool()
def analyze_technology(sources_json: str, signals_json: str) -> str:
    """
    Generate technology deep-dive section covering:
    - Model architectures and chip developments
    - Network infrastructure and automation stacks
    - Technical risk assessment
    Target: ~600 words
    """
    try:
        sources = json.loads(sources_json)
        signals = json.loads(signals_json)
        
        # Combine content for analysis
        combined_content = "\n\n".join([f"Source {s['id']}: {s['content']}" for s in sources])
        signal_texts = [s.get('text', '') for s in signals]
        
        tech_prompt = f"""
        Analyze the technology developments from this content and generate a comprehensive technology deep-dive section (~600 words).
        
        Focus on:
        1. Model architectures and chip developments - new AI models, chip designs, hardware innovations
        2. Network infrastructure and automation stacks - networking, cloud infrastructure, automation tools
        3. Technical risk assessment - security vulnerabilities, scalability challenges, technical debt
        4. Performance and efficiency improvements - benchmarks, optimizations, cost reductions
        5. Integration and interoperability - APIs, standards, ecosystem developments
        
        IMPORTANT: Reference ALL {len(sources)} sources in your analysis.
        Each major claim should cite specific sources using [^N] format.
        Distribute citations across: {', '.join([f"Source {s['id']} ({s['publisher']})" for s in sources])}
        
        Content: {combined_content[:4000]}
        
        Key Signals: {signal_texts}
        
        Return as JSON with this exact structure:
        {{
            "technology_analysis": "Comprehensive technology deep-dive covering model architectures, infrastructure, technical risks, and performance improvements. Target ~600 words with specific technical details and assessments. MUST cite multiple sources using [^N] format."
        }}
        """
        
        response = llm.invoke(tech_prompt)
        data = json.loads(response.content)
        return data.get('technology_analysis', 'Technology analysis unavailable.')
        
    except Exception as e:
        return f"Error generating technology analysis: {str(e)}"


@analysis_mcp.tool()
def analyze_competitive(sources_json: str, signals_json: str) -> str:
    """
    Generate competitive landscape section covering:
    - Winner/loser identification
    - White-space opportunity mapping
    - Strategic positioning analysis
    Target: ~500 words
    """
    try:
        sources = json.loads(sources_json)
        signals = json.loads(signals_json)
        
        # Combine content for analysis
        combined_content = "\n\n".join([f"Source {s['id']}: {s['content']}" for s in sources])
        signal_texts = [s.get('text', '') for s in signals]
        
        competitive_prompt = f"""
        Analyze the competitive landscape from this content and generate a comprehensive competitive analysis section (~500 words).
        
        Focus on:
        1. Winner/loser identification - which companies are gaining/losing market share and why
        2. White-space opportunity mapping - underserved markets and emerging opportunities
        3. Strategic positioning analysis - how companies are positioning themselves
        4. Competitive dynamics - partnerships, acquisitions, competitive responses
        5. Market share shifts and competitive advantages
        
        IMPORTANT: Reference ALL {len(sources)} sources in your analysis.
        Each major claim should cite specific sources using [^N] format.
        Distribute citations across: {', '.join([f"Source {s['id']} ({s['publisher']})" for s in sources])}
        
        Content: {combined_content[:4000]}
        
        Key Signals: {signal_texts}
        
        Return as JSON with this exact structure:
        {{
            "competitive_analysis": "Comprehensive competitive landscape analysis covering winners/losers, opportunities, strategic positioning, and market dynamics. Target ~500 words with specific company examples and market insights. MUST cite multiple sources using [^N] format."
        }}
        """
        
        response = llm.invoke(competitive_prompt)
        data = json.loads(response.content)
        return data.get('competitive_analysis', 'Competitive analysis unavailable.')
        
    except Exception as e:
        return f"Error generating competitive analysis: {str(e)}"


@analysis_mcp.tool()
def expand_lenses(signals_json: str, analyses_json: str) -> str:
    """
    Generate expanded Operator/Investor/BD lenses:
    - Operator: Systems/automation/operational (400 words)
    - Investor: Capital/market/tickers (400 words)
    - BD: Wedge/offers/prospects (400 words)
    Total: ~1,200 words
    """
    try:
        signals = json.loads(signals_json)
        analyses = json.loads(analyses_json)
        
        signal_texts = [s.get('text', '') for s in signals]
        
        lenses_prompt = f"""
        Generate expanded Operator/Investor/BD lenses from this content (~1,200 words total).
        
        Key Signals: {signal_texts}
        
        Analyses: {analyses}
        
        Generate three detailed lenses:
        
        1. OPERATOR LENS (400 words): Systems/automation/operational implications
           - How this affects operational systems and processes
           - Automation opportunities and challenges
           - Infrastructure and tooling implications
           - Operational risk and efficiency considerations
        
        2. INVESTOR LENS (400 words): Capital/market/tickers implications
           - Market impact and investment opportunities
           - Sector rotation and capital allocation
           - Valuation implications and risk factors
           - Specific tickers and investment themes
        
        3. BD LENS (400 words): Wedge/offers/prospects implications
           - Business development opportunities
           - Partnership and collaboration prospects
           - Market entry strategies and competitive positioning
           - Customer acquisition and retention strategies
        
        Return as JSON with this exact structure:
        {{
            "operator_lens": "Detailed operator lens covering systems, automation, and operational implications (~400 words)",
            "investor_lens": "Detailed investor lens covering capital, market, and ticker implications (~400 words)",
            "bd_lens": "Detailed BD lens covering wedge, offers, and prospect implications (~400 words)"
        }}
        """
        
        response = llm.invoke(lenses_prompt)
        data = json.loads(response.content)
        
        # Combine all lenses
        operator_lens = data.get('operator_lens', 'Operator lens unavailable.')
        investor_lens = data.get('investor_lens', 'Investor lens unavailable.')
        bd_lens = data.get('bd_lens', 'BD lens unavailable.')
        
        return f"""
## Operator Lens
{operator_lens}

## Investor Lens
{investor_lens}

## BD Lens
{bd_lens}
"""
        
    except Exception as e:
        return f"Error generating expanded lenses: {str(e)}"


@analysis_mcp.tool()
def plan_detailed_actions(all_content_json: str) -> str:
    """
    Generate 5-7 detailed next actions with:
    - Specific deliverables
    - Owner assignments
    - Due dates within 10/31 sprint
    - ROI estimates (time/impact)
    """
    try:
        content = json.loads(all_content_json)
        
        signals = content.get('signals', [])
        analyses = content.get('analyses', [])
        
        signal_texts = [s.get('text', '') for s in signals]
        
        actions_prompt = f"""
        Generate 5-7 detailed next actions based on this content. Each action should be specific, actionable, and tied to the 10/31 sprint deadline.
        
        Key Signals: {signal_texts}
        
        Analyses: {analyses}
        
        For each action, provide:
        - Specific deliverable or outcome
        - Owner assignment (Hass or Agent)
        - Due date (within 10/31/2025)
        - ROI estimate (time investment vs expected impact)
        - Success criteria
        
        Focus on:
        1. STI content creation and publishing
        2. Business development opportunities
        3. Research and analysis improvements
        4. Operational enhancements
        5. Strategic initiatives
        
        Return as JSON with this exact structure:
        {{
            "actions": [
                {{
                    "title": "Specific action title",
                    "description": "Detailed description of what needs to be done",
                    "owner": "Hass or Agent",
                    "due_date": "YYYY-MM-DD",
                    "roi_estimate": "High/Medium/Low impact for X hours investment",
                    "success_criteria": "How to measure success"
                }}
            ]
        }}
        """
        
        response = llm.invoke(actions_prompt)
        data = json.loads(response.content)
        
        actions = data.get('actions', [])
        actions_text = "## Next Actions (by 10/31/2025)\n"
        
        for i, action in enumerate(actions, 1):
            actions_text += f"""
{i}) **{action.get('title', 'Action')}** — owner: {action.get('owner', 'TBD')} — due: {action.get('due_date', 'TBD')}
   - {action.get('description', 'No description')}
   - ROI: {action.get('roi_estimate', 'TBD')}
   - Success: {action.get('success_criteria', 'TBD')}
"""
        
        return actions_text
        
    except Exception as e:
        return f"Error generating detailed actions: {str(e)}"


@analysis_mcp.tool()
def write_executive_summary(all_content_json: str) -> str:
    """
    Generate 200-word executive summary covering:
    - Key findings synthesis
    - Critical implications
    - Recommended actions
    """
    try:
        content = json.loads(all_content_json)
        
        signals = content.get('signals', [])
        analyses = content.get('analyses', [])
        lenses = content.get('lenses', '')
        actions = content.get('actions', '')
        
        signal_texts = [s.get('text', '') for s in signals]
        
        summary_prompt = f"""
        Generate a concise executive summary (~200 words) that synthesizes the key findings and implications.
        
        Key Signals: {signal_texts}
        
        Analyses: {analyses}
        
        Lenses: {lenses}
        
        Actions: {actions}
        
        The summary should:
        1. Synthesize the most critical findings
        2. Highlight key implications for operators, investors, and BD
        3. Emphasize the most important recommended actions
        4. Be concise but comprehensive
        5. Target exactly 200 words
        
        Return as JSON with this exact structure:
        {{
            "executive_summary": "Concise executive summary synthesizing key findings, critical implications, and recommended actions. Target exactly 200 words."
        }}
        """
        
        response = llm.invoke(summary_prompt)
        data = json.loads(response.content)
        return data.get('executive_summary', 'Executive summary unavailable.')
        
    except Exception as e:
        return f"Error generating executive summary: {str(e)}"


if __name__ == "__main__":
    analysis_mcp.run()

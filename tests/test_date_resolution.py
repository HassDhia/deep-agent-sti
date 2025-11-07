"""Tests for date resolution and rejection of sources without dates."""

import pytest
from datetime import datetime
from simple_mcp_agent import SimpleMCPTimeFilteredAgent
from final_analyst_agent import FinalAnalystGradeAgent


def test_extract_date_returns_none_when_missing():
    """Test that _extract_date returns None when no date is found."""
    agent = SimpleMCPTimeFilteredAgent(
        openai_api_key="test_key",
        tavily_api_key=""
    )
    
    result_no_date = {}
    date = agent._extract_date(result_no_date)
    assert date is None, "Should return None when no date fields present"


def test_extract_date_parses_various_formats():
    """Test that _extract_date parses common date formats."""
    agent = SimpleMCPTimeFilteredAgent(
        openai_api_key="test_key",
        tavily_api_key=""
    )
    
    # ISO format
    result_iso = {"published_date": "2025-10-13"}
    assert agent._extract_date(result_iso) == "2025-10-13"
    
    # ISO with time
    result_iso_time = {"date": "2025-10-13T14:30:00Z"}
    assert agent._extract_date(result_iso_time) == "2025-10-13"
    
    # US format
    result_us = {"pubdate": "10/13/2025"}
    assert agent._extract_date(result_us) == "2025-10-13"


def test_final_analyst_extract_date_returns_none():
    """Test that FinalAnalystGradeAgent._extract_date returns None when no date."""
    agent = FinalAnalystGradeAgent(
        openai_api_key="test_key",
        tavily_api_key=""
    )
    
    result_no_date = {}
    date = agent._extract_date(result_no_date)
    assert date is None, "Should return None when no date fields present"


def test_final_analyst_extract_date_parses_formats():
    """Test that FinalAnalystGradeAgent._extract_date parses formats correctly."""
    agent = FinalAnalystGradeAgent(
        openai_api_key="test_key",
        tavily_api_key=""
    )
    
    # ISO format
    result_iso = {"published_date": "2025-10-13"}
    assert agent._extract_date(result_iso) == "2025-10-13"
    
    # ISO with time
    result_iso_time = {"date": "2025-10-13T14:30:00Z"}
    assert agent._extract_date(result_iso_time) == "2025-10-13"


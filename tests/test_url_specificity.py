"""Tests for URL specificity validation (rejecting index pages)."""

import pytest
from simple_mcp_agent import SimpleMCPTimeFilteredAgent
from config import STIConfig


def test_reject_reuters_index_page():
    """Test that reuters.com/technology index page is rejected."""
    agent = SimpleMCPTimeFilteredAgent(
        openai_api_key="test_key",
        tavily_api_key=""
    )
    
    # Index page (should be rejected)
    index_url = "https://www.reuters.com/technology"
    assert agent._validate_url(index_url, "Technology News") is None
    
    # Article page (should be accepted)
    article_url = "https://www.reuters.com/technology/2025/10/13/ai-breakthrough"
    assert agent._validate_url(article_url, "AI Breakthrough") is not None


def test_reject_bloomberg_index():
    """Test that Bloomberg index pages are rejected."""
    agent = SimpleMCPTimeFilteredAgent(
        openai_api_key="test_key",
        tavily_api_key=""
    )
    
    # Index page
    index_url = "https://www.bloomberg.com/technology"
    assert agent._validate_url(index_url, "Tech News") is None
    
    # Article page
    article_url = "https://www.bloomberg.com/news/articles/2025-10-13/ai-advances"
    assert agent._validate_url(article_url, "AI Advances") is not None


def test_accept_sec_filing():
    """Test that SEC filing URLs are accepted."""
    agent = SimpleMCPTimeFilteredAgent(
        openai_api_key="test_key",
        tavily_api_key=""
    )
    
    filing_url = "https://www.sec.gov/Archives/edgar/data/1234567/000123456725000001/form10k.htm"
    assert agent._validate_url(filing_url, "10-K Filing") is not None


def test_is_article_url():
    """Test _is_article_url helper method."""
    agent = SimpleMCPTimeFilteredAgent(
        openai_api_key="test_key",
        tavily_api_key=""
    )
    
    # Index pages
    assert agent._is_article_url("https://reuters.com/technology") is False
    assert agent._is_article_url("https://bloomberg.com/") is False
    
    # Article pages
    assert agent._is_article_url("https://reuters.com/technology/2025/10/13/article") is True
    assert agent._is_article_url("https://bloomberg.com/news/articles/2025-10-13/story") is True
    assert agent._is_article_url("https://example.com/path/to/article") is True  # Generic domain with depth


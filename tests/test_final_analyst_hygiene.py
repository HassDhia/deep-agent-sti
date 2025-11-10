"""Tests for final_analyst_agent.py hygiene filters."""

import pytest
from final_analyst_agent import FinalAnalystGradeAgent


def test_reject_reuters_index_page():
    """Test that reuters.com/technology index page is rejected."""
    agent = FinalAnalystGradeAgent(
        openai_api_key="test_key",
        tavily_api_key=""
    )
    
    # Index page (should be rejected)
    index_result = {'url': 'https://www.reuters.com/technology/', 'title': 'Technology News'}
    assert agent._passes_strict_hygiene_filters(index_result) is False
    
    # Article page (should be accepted)
    article_result = {'url': 'https://www.reuters.com/technology/2025/10/13/ai-breakthrough', 'title': 'AI Breakthrough'}
    assert agent._passes_strict_hygiene_filters(article_result) is True


def test_reject_bloomberg_index():
    """Test that Bloomberg index pages are rejected."""
    agent = FinalAnalystGradeAgent(
        openai_api_key="test_key",
        tavily_api_key=""
    )
    
    # Index page
    index_result = {'url': 'https://www.bloomberg.com/technology', 'title': 'Tech News'}
    assert agent._passes_strict_hygiene_filters(index_result) is False
    
    # Article page
    article_result = {'url': 'https://www.bloomberg.com/news/articles/2025-10-13/ai-advances', 'title': 'AI Advances'}
    assert agent._passes_strict_hygiene_filters(article_result) is True


def test_is_article_url():
    """Test _is_article_url helper function."""
    agent = FinalAnalystGradeAgent(
        openai_api_key="test_key",
        tavily_api_key=""
    )
    
    # Index pages should return False
    assert agent._is_article_url("https://www.reuters.com/technology/") is False
    assert agent._is_article_url("https://www.bloomberg.com/technology") is False
    
    # Article URLs should return True
    assert agent._is_article_url("https://www.reuters.com/technology/2025/10/13/article") is True
    assert agent._is_article_url("https://www.bloomberg.com/news/articles/2025-10-13/article") is True
    assert agent._is_article_url("https://www.ft.com/content/article-id") is True
    assert agent._is_article_url("https://www.wsj.com/articles/article-id") is True


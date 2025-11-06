#!/usr/bin/env python3
"""
Test to verify that the search method returns the correct number of values
and that confidence is properly initialized.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestSearchReturnValues(unittest.TestCase):
    """Test that search method returns correct values and handles confidence properly"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.openai_api_key = "test_key"
        self.tavily_api_key = ""
    
    def _get_audit_outputs(self):
        """Helper to get standard audit outputs"""
        return {
            'ledger': None,
            'quant_patch': None,
            'adversarial': None,
            'playbooks': None,
            'confidence_breakdown': None,
            'confidence': 0.5,
            'metrics': {},
            'anchor_gate': False,
            'advanced_tokens': 0,
            'tasks_executed': [],
            'tasks_requested': [],
            'task_matrix': {},
            'source_sha_map': {},
            'report_sections': {},
            'claims': [],
        }
    
    @patch('enhanced_mcp_agent.save_enhanced_report_auto')
    @patch('enhanced_mcp_agent.write_json')
    @patch('enhanced_mcp_agent.SimpleMCPTimeFilteredAgent.__init__')
    @patch('enhanced_mcp_agent.EnhancedSTIAgent.initialize_analysis_tools')
    def test_search_returns_three_values(self, mock_init_tools, mock_parent_init, 
                                         mock_write_json, mock_save_report):
        """Test that search method returns exactly 3 values"""
        mock_parent_init.return_value = None
        mock_save_report.return_value = '/test/path'
        
        from enhanced_mcp_agent import EnhancedSTIAgent
        
        agent = EnhancedSTIAgent(
            openai_api_key=self.openai_api_key,
            tavily_api_key=self.tavily_api_key
        )
        
        # Mock all methods with a simpler approach
        agent._refine_query_for_title = Mock(return_value="test query")
        agent._search_with_time_filtering = Mock(return_value=[])
        agent._check_market_source_adequacy = Mock(return_value=False)
        agent._expand_theoretical_query = Mock(return_value="expanded query")
        agent._decompose_theory_query = Mock(return_value=[])
        agent._search_foundational_sources = Mock(return_value=[])
        agent._search_theoretical_concepts = Mock(return_value=[])
        agent._deduplicate_sources = Mock(return_value=[])
        agent._reweight_by_source_type = Mock(return_value=[])
        agent._semantic_similarity_filter = Mock(return_value=[])
        agent._check_academic_floor = Mock(return_value=False)
        agent._filter_sources_by_title_relevance = Mock(return_value=[])
        agent._check_quality_gates = Mock(return_value=True)
        agent._extract_signals_enhanced = Mock(return_value=[])
        agent._derive_title_from_content = Mock(return_value="Test Title")
        agent._serialize_sources_to_json = Mock(return_value='[]')
        agent._serialize_signals_to_json = Mock(return_value='[]')
        agent._call_analysis_tool = Mock(return_value="test analysis")
        agent._calculate_confidence_with_intent = Mock(return_value=0.5)
        agent._run_auditors = Mock(return_value=self._get_audit_outputs())
        agent._calculate_source_attribution_stats = Mock()
        agent._generate_enhanced_report = Mock(return_value="# Test Report\nTest content")
        agent._generate_json_ld_artifact = Mock(return_value={'test': 'jsonld'})
        
        # Call search method
        result = agent.search("test query", days_back=7)
        
        # Verify it returns exactly 3 values
        self.assertEqual(len(result), 3, "search() should return exactly 3 values")
        
        markdown_report, json_ld_artifact, run_summary = result
        
        # Verify types
        self.assertIsInstance(markdown_report, str, "First return value should be a string")
        self.assertIsInstance(json_ld_artifact, dict, "Second return value should be a dict")
        self.assertIsInstance(run_summary, dict, "Third return value should be a dict")
        
        # Verify run_summary structure
        self.assertIn('intent', run_summary)
        self.assertIn('artifacts', run_summary)
        self.assertIn('metrics', run_summary)
        self.assertIn('confidence_breakdown', run_summary)
        self.assertIn('premium', run_summary)
    
    @patch('enhanced_mcp_agent.save_enhanced_report_auto')
    @patch('enhanced_mcp_agent.write_json')
    @patch('enhanced_mcp_agent.SimpleMCPTimeFilteredAgent.__init__')
    @patch('enhanced_mcp_agent.EnhancedSTIAgent.initialize_analysis_tools')
    def test_confidence_initialized_before_auditors(self, mock_init_tools, mock_parent_init,
                                                     mock_write_json, mock_save_report):
        """Test that confidence is initialized before _run_auditors is called"""
        mock_parent_init.return_value = None
        mock_save_report.return_value = '/test/path'
        
        from enhanced_mcp_agent import EnhancedSTIAgent
        
        agent = EnhancedSTIAgent(
            openai_api_key=self.openai_api_key,
            tavily_api_key=self.tavily_api_key
        )
        
        # Track call order
        call_order = []
        
        def track_calculate_confidence(*args, **kwargs):
            call_order.append('calculate_confidence')
            return 0.5
        
        def track_run_auditors(*args, **kwargs):
            call_order.append('run_auditors')
            return self._get_audit_outputs()
        
        # Mock all methods
        agent._refine_query_for_title = Mock(return_value="test query")
        agent._search_with_time_filtering = Mock(return_value=[])
        agent._check_market_source_adequacy = Mock(return_value=False)
        agent._expand_theoretical_query = Mock(return_value="expanded query")
        agent._decompose_theory_query = Mock(return_value=[])
        agent._search_foundational_sources = Mock(return_value=[])
        agent._search_theoretical_concepts = Mock(return_value=[])
        agent._deduplicate_sources = Mock(return_value=[])
        agent._reweight_by_source_type = Mock(return_value=[])
        agent._semantic_similarity_filter = Mock(return_value=[])
        # Return True for academic floor to avoid early return
        agent._check_academic_floor = Mock(return_value=True)
        # Return at least 3 sources to avoid insufficient sources early return
        mock_source = Mock()
        agent._filter_sources_by_title_relevance = Mock(return_value=[mock_source, mock_source, mock_source])
        agent._check_quality_gates = Mock(return_value=True)
        agent._extract_signals_enhanced = Mock(return_value=[])
        agent._derive_title_from_content = Mock(return_value="Test Title")
        agent._serialize_sources_to_json = Mock(return_value='[]')
        agent._serialize_signals_to_json = Mock(return_value='[]')
        agent._call_analysis_tool = Mock(return_value="test analysis")
        agent._calculate_confidence_with_intent = Mock(side_effect=track_calculate_confidence)
        agent._run_auditors = Mock(side_effect=track_run_auditors)
        agent._calculate_source_attribution_stats = Mock()
        agent._generate_enhanced_report = Mock(return_value="# Test Report\nTest content")
        agent._generate_json_ld_artifact = Mock(return_value={'test': 'jsonld'})
        
        # Call search method
        agent.search("test query", days_back=7)
        
        # Verify confidence calculation happens before auditors
        self.assertIn('calculate_confidence', call_order)
        self.assertIn('run_auditors', call_order)
        self.assertLess(
            call_order.index('calculate_confidence'),
            call_order.index('run_auditors'),
            "confidence should be calculated before _run_auditors is called"
        )
    
    @patch('enhanced_mcp_agent.SimpleMCPTimeFilteredAgent.__init__')
    @patch('enhanced_mcp_agent.EnhancedSTIAgent.initialize_analysis_tools')
    def test_error_returns_three_values(self, mock_init_tools, mock_parent_init):
        """Test that error case also returns 3 values"""
        mock_parent_init.return_value = None
        
        from enhanced_mcp_agent import EnhancedSTIAgent
        
        agent = EnhancedSTIAgent(
            openai_api_key=self.openai_api_key,
            tavily_api_key=self.tavily_api_key
        )
        
        # Force an error by making _refine_query_for_title raise an exception
        agent._refine_query_for_title = Mock(side_effect=Exception("Test error"))
        
        result = agent.search("test query", days_back=7)
        
        # Verify it returns exactly 3 values even on error
        self.assertEqual(len(result), 3, "search() should return exactly 3 values even on error")
        
        markdown_report, json_ld_artifact, run_summary = result
        
        # Verify error structure
        self.assertIsInstance(markdown_report, str)
        self.assertIn("Error", markdown_report)
        self.assertIsInstance(json_ld_artifact, dict)
        self.assertIsInstance(run_summary, dict)
        self.assertEqual(run_summary.get('intent'), 'unknown')


if __name__ == '__main__':
    unittest.main()

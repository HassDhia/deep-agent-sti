"""
Test to verify anchor_coverage fix - ensures metrics.get() is used instead of undefined variable
"""
import unittest
from unittest.mock import Mock, patch, MagicMock
import os


class TestAnchorCoverageFix(unittest.TestCase):
    """Test that anchor_coverage is correctly accessed from metrics dictionary"""
    
    def setUp(self):
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "test-key")
        self.tavily_api_key = os.getenv("TAVILY_API_KEY", "")
    
    def _get_audit_outputs_with_metrics(self, anchor_coverage=0.5):
        """Helper to create audit_outputs with metrics containing anchor_coverage"""
        mock_breakdown = Mock()
        mock_breakdown.source_diversity = 0.5
        mock_breakdown.anchor_coverage = anchor_coverage
        mock_breakdown.method_transparency = 0.5
        mock_breakdown.replication_readiness = 0.5
        mock_breakdown.__dict__ = {
            'source_diversity': 0.5,
            'anchor_coverage': anchor_coverage,
            'method_transparency': 0.5,
            'replication_readiness': 0.5
        }
        
        return {
            "ledger": {},
            "quant_patch": None,
            "adversarial": None,
            "playbooks": None,
            "confidence_breakdown": mock_breakdown,
            "confidence": 0.5,
            "confidence_raw": 0.5,
            "metrics": {
                "anchor_coverage": anchor_coverage,
                "quant_flags": 0,
                "confidence": 0.5,
            },
            "anchor_gate": False,
            "advanced_tokens": 0,
            "tasks_executed": [],
            "tasks_requested": [],
            "task_matrix": {},
            "source_sha_map": {},
            "report_sections": {},
            "claims": [],
        }
    
    @patch('enhanced_mcp_agent.save_enhanced_report_auto')
    @patch('enhanced_mcp_agent.write_json')
    @patch('enhanced_mcp_agent.SimpleMCPTimeFilteredAgent.__init__')
    @patch('enhanced_mcp_agent.EnhancedSTIAgent.initialize_analysis_tools')
    def test_anchor_coverage_from_metrics(self, mock_init_tools, mock_parent_init,
                                         mock_write_json, mock_save_report):
        """Test that anchor_coverage is correctly extracted from metrics dictionary"""
        mock_parent_init.return_value = None
        
        from enhanced_mcp_agent import EnhancedSTIAgent
        
        agent = EnhancedSTIAgent(
            openai_api_key=self.openai_api_key,
            tavily_api_key=self.tavily_api_key
        )
        
        # Mock all the necessary methods
        agent._refine_query_for_title = Mock(return_value="test query")
        agent._search_with_time_filtering = Mock(return_value=[])
        agent._check_market_source_adequacy = Mock(return_value=False)
        agent._deduplicate_sources = Mock(return_value=[])
        agent._reweight_by_source_type = Mock(return_value=[])
        agent._filter_sources_by_title_relevance = Mock(return_value=([], {
            'evaluation_success': True,
            'sources_passed': 3,
            'failure_reason': None
        }))
        agent._extract_signals_enhanced = Mock(return_value=[])
        agent._serialize_sources_to_json = Mock(return_value='[]')
        agent._serialize_signals_to_json = Mock(return_value='[]')
        agent._call_analysis_tool = Mock(return_value="test analysis")
        agent._calculate_confidence_with_intent = Mock(return_value=0.5)
        agent._run_auditors = Mock(return_value=self._get_audit_outputs_with_metrics(anchor_coverage=0.75))
        agent._calculate_source_attribution_stats = Mock()
        agent._generate_enhanced_report = Mock(return_value="# Test Report\nTest content")
        agent._generate_json_ld_artifact = Mock(return_value={'test': 'jsonld'})
        agent._derive_title_from_content = Mock(return_value="Test Title")
        agent._classify_horizon = Mock(return_value="Near-term")
        agent._is_hybrid_thesis_anchored = Mock(return_value=False)
        agent.get_date_filter_stats = Mock(return_value={})
        
        # Mock budget initialization
        with patch('enhanced_mcp_agent.BudgetManager') as mock_budget_class:
            mock_budget = Mock()
            mock_budget.left.return_value = 1000
            mock_budget_class.return_value = mock_budget
            
            # Call search method - this should NOT raise NameError for anchor_coverage
            try:
                result = agent.search("test query", days_back=7, budget_advanced=1000)
            except NameError as e:
                if 'anchor_coverage' in str(e):
                    self.fail(f"NameError for anchor_coverage should not occur: {e}")
                else:
                    raise
            
            # Verify it returns 3 values
            self.assertEqual(len(result), 3, "search() should return exactly 3 values")
            
            markdown_report, json_ld_artifact, run_summary = result
            
            # Verify run_summary has metrics with anchor_coverage
            self.assertIn('metrics', run_summary)
            self.assertIn('anchor_coverage', run_summary['metrics'])
            self.assertEqual(run_summary['metrics']['anchor_coverage'], 0.75)
            
            # Verify asset_gating was set correctly
            self.assertIn('asset_gating', run_summary)
            asset_gating = run_summary['asset_gating']
            self.assertIn('images_enabled', asset_gating)
            self.assertIn('social_enabled', asset_gating)
    
    @patch('enhanced_mcp_agent.save_enhanced_report_auto')
    @patch('enhanced_mcp_agent.write_json')
    @patch('enhanced_mcp_agent.SimpleMCPTimeFilteredAgent.__init__')
    @patch('enhanced_mcp_agent.EnhancedSTIAgent.initialize_analysis_tools')
    def test_anchor_coverage_missing_from_metrics(self, mock_init_tools, mock_parent_init,
                                                  mock_write_json, mock_save_report):
        """Test that missing anchor_coverage in metrics is handled gracefully"""
        mock_parent_init.return_value = None
        
        from enhanced_mcp_agent import EnhancedSTIAgent
        
        agent = EnhancedSTIAgent(
            openai_api_key=self.openai_api_key,
            tavily_api_key=self.tavily_api_key
        )
        
        # Mock all the necessary methods
        agent._refine_query_for_title = Mock(return_value="test query")
        agent._search_with_time_filtering = Mock(return_value=[])
        agent._check_market_source_adequacy = Mock(return_value=False)
        agent._deduplicate_sources = Mock(return_value=[])
        agent._reweight_by_source_type = Mock(return_value=[])
        agent._filter_sources_by_title_relevance = Mock(return_value=([], {
            'evaluation_success': True,
            'sources_passed': 3,
            'failure_reason': None
        }))
        agent._extract_signals_enhanced = Mock(return_value=[])
        agent._serialize_sources_to_json = Mock(return_value='[]')
        agent._serialize_signals_to_json = Mock(return_value='[]')
        agent._call_analysis_tool = Mock(return_value="test analysis")
        agent._calculate_confidence_with_intent = Mock(return_value=0.5)
        
        # Create audit_outputs WITHOUT anchor_coverage in metrics
        mock_breakdown_missing = Mock()
        mock_breakdown_missing.__dict__ = {}
        
        audit_outputs_missing = {
            "ledger": {},
            "quant_patch": None,
            "adversarial": None,
            "playbooks": None,
            "confidence_breakdown": mock_breakdown_missing,
            "confidence": 0.5,
            "confidence_raw": 0.5,
            "metrics": {
                # Missing anchor_coverage!
                "quant_flags": 0,
                "confidence": 0.5,
            },
            "anchor_gate": False,
            "advanced_tokens": 0,
            "tasks_executed": [],
            "tasks_requested": [],
            "task_matrix": {},
            "source_sha_map": {},
            "report_sections": {},
            "claims": [],
        }
        
        agent._run_auditors = Mock(return_value=audit_outputs_missing)
        agent._calculate_source_attribution_stats = Mock()
        agent._generate_enhanced_report = Mock(return_value="# Test Report\nTest content")
        agent._generate_json_ld_artifact = Mock(return_value={'test': 'jsonld'})
        agent._derive_title_from_content = Mock(return_value="Test Title")
        agent._classify_horizon = Mock(return_value="Near-term")
        agent._is_hybrid_thesis_anchored = Mock(return_value=False)
        agent.get_date_filter_stats = Mock(return_value={})
        
        # Mock budget initialization
        with patch('enhanced_mcp_agent.BudgetManager') as mock_budget_class:
            mock_budget = Mock()
            mock_budget.left.return_value = 1000
            mock_budget_class.return_value = mock_budget
            
            # Call search method - should handle missing anchor_coverage gracefully
            result = agent.search("test query", days_back=7, budget_advanced=1000)
            
            # Verify it returns 3 values
            self.assertEqual(len(result), 3, "search() should return exactly 3 values")
            
            markdown_report, json_ld_artifact, run_summary = result
            
            # Verify metrics now has anchor_coverage (should be defaulted to 0.0)
            self.assertIn('metrics', run_summary)
            self.assertIn('anchor_coverage', run_summary['metrics'])
            self.assertEqual(run_summary['metrics']['anchor_coverage'], 0.0)


if __name__ == '__main__':
    unittest.main()


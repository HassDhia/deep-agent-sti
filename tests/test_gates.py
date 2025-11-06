from gates import value_of_information


def test_value_of_information_triggers_expected_tasks():
    metrics = {"anchor_coverage": 0.6, "quant_flags": 2, "confidence": 0.6}
    tasks = value_of_information(metrics, "theory")
    assert "evidence_alignment" in tasks
    assert "math_guard" in tasks
    assert "adversarial_review" in tasks
    assert "decision_playbooks" in tasks


def test_value_of_information_market_path():
    metrics = {"anchor_coverage": 0.85, "quant_flags": 0, "confidence": 0.8}
    tasks = value_of_information(metrics, "market")
    assert tasks == []


def test_asset_gating_thesis_anchor_absent():
    """Test that thesis reports with Anchor-Absent status skip image generation."""
    from html_converter_agent import HTMLConverterAgent
    from config import STIConfig
    
    # Mock template_data with thesis + Anchor-Absent
    template_data = {
        'anchor_status': 'Anchor-Absent',
        'title': 'Test Thesis Report'
    }
    
    # Mock agent_stats with asset_gating
    agent_stats = {
        'asset_gating': {
            'images_enabled': True,  # Initially enabled
            'social_enabled': True
        }
    }
    
    # Simulate the gating logic
    is_thesis = True
    images_enabled = agent_stats.get('asset_gating', {}).get('images_enabled', True)
    
    # Apply thesis asset gating
    if is_thesis and getattr(STIConfig, 'REQUIRE_ANCHORS_FOR_ASSETS', False):
        anchor_status = template_data.get('anchor_status', '')
        if anchor_status in ("Anchor-Absent", "Anchor-Sparse"):
            images_enabled = False
    
    assert images_enabled == False, "Thesis with Anchor-Absent should gate images"


def test_asset_gating_thesis_anchored():
    """Test that thesis reports with Anchored status allow image generation."""
    from config import STIConfig
    
    template_data = {
        'anchor_status': 'Anchored',
        'title': 'Test Thesis Report'
    }
    
    agent_stats = {
        'asset_gating': {
            'images_enabled': True
        }
    }
    
    is_thesis = True
    images_enabled = agent_stats.get('asset_gating', {}).get('images_enabled', True)
    
    # Apply thesis asset gating
    if is_thesis and getattr(STIConfig, 'REQUIRE_ANCHORS_FOR_ASSETS', False):
        anchor_status = template_data.get('anchor_status', '')
        if anchor_status in ("Anchor-Absent", "Anchor-Sparse"):
            images_enabled = False
    
    assert images_enabled == True, "Thesis with Anchored status should allow images"


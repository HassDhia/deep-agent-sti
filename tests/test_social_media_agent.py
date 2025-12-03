from social_media_agent import SocialMediaAgent


def test_social_media_uses_signal_claim():
    agent = SocialMediaAgent(api_key="test", model_name="gpt-5")
    report = "Executive summary text."
    context = {
        "title": "Signal Brief",
        "confidence": 0.8,
        "signals": [
            {"text": "VIP hospitality drops now behave like streetwear capsules.", "citations": [1]},
            {"text": "Secondary signal", "citations": []},
        ],
        "sources": [
            {"id": 1, "publisher": "Reuters", "date": "2024-05-01", "url": "https://example.com"},
        ],
    }
    payload = agent.generate_all_formats(report, context)
    assert "VIP hospitality" in payload["linkedin_post"]
    assert payload["metadata"]["teaser_mode"] is False


def test_social_media_handles_missing_signals():
    agent = SocialMediaAgent(api_key="test", model_name="gpt-5")
    payload = agent.generate_all_formats("Fallback report text.", {"confidence": 0.5})
    assert payload["metadata"]["teaser_mode"] is True
    assert payload["linkedin_post"]

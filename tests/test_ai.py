from app import ai, config


def test_merge_settings_prefers_stored_values():
    cfg = config.Config(
        db_path="/tmp/x.db",
        classify_threshold=0.8,
        classify_interval_seconds=30,
        ai_provider="anthropic",
        anthropic_api_key="env-a",
        openai_api_key=None,
        gemini_api_key=None,
        xai_api_key=None,
        anthropic_model="claude-haiku-4-5",
        openai_model=None,
        gemini_model=None,
        xai_model=None,
        s3_bucket=None,
        s3_region=None,
        s3_endpoint_url=None,
        backup_retention=7,
        seed_demo=False,
    )
    runtime = ai.merge_settings(
        cfg,
        {
            "ai_provider": "openai",
            "openai_api_key": "stored-o",
            "openai_model": "gpt-5-mini",
        },
    )
    assert runtime.provider == "openai"
    assert runtime.tokens["openai"] == "stored-o"
    assert runtime.models["openai"] == "gpt-5-mini"


def test_merge_settings_falls_back_to_first_available_token():
    cfg = config.Config(
        db_path="/tmp/x.db",
        classify_threshold=0.8,
        classify_interval_seconds=30,
        ai_provider="anthropic",
        anthropic_api_key=None,
        openai_api_key="env-openai",
        gemini_api_key="env-gemini",
        xai_api_key=None,
        anthropic_model=None,
        openai_model=None,
        gemini_model=None,
        xai_model=None,
        s3_bucket=None,
        s3_region=None,
        s3_endpoint_url=None,
        backup_retention=7,
        seed_demo=False,
    )
    runtime = ai.merge_settings(cfg, {})
    assert runtime.provider == "openai"

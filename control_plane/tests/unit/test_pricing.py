from app.pricing import cost_of


def test_cost_uses_price_table():
    # gpt-4o: $0.005/1k in, $0.015/1k out
    cost = cost_of("gpt-4o", {"prompt_tokens": 1000, "completion_tokens": 1000})
    assert cost == 0.005 + 0.015


def test_unknown_model_is_free_but_defined():
    assert cost_of("mystery-model", {"prompt_tokens": 999, "completion_tokens": 999}) == 0.0


def test_missing_usage_fields_default_to_zero():
    assert cost_of("gpt-4o", {}) == 0.0

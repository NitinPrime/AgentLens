from decimal import Decimal

from app.core.pricing import estimate_cost, infer_provider


def test_gpt4o_cost():
    cost = estimate_cost("gpt-4o", 1_000_000, 1_000_000)
    assert cost == Decimal("12.500000")


def test_unknown_model_uses_default_and_infer_openai():
    assert infer_provider("gpt-4o") == "openai"
    assert infer_provider("claude-3-5-sonnet") == "anthropic"
    assert infer_provider("mystery-model") == "unknown"

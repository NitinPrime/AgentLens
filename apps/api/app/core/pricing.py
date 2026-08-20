"""Configurable model pricing. Costs are USD per 1 million tokens."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

# Input/output prices are USD per 1M tokens.
MODEL_PRICING: dict[str, dict[str, object]] = {
    "gpt-5": {"provider": "openai", "input_per_1m": Decimal("5.00"), "output_per_1m": Decimal("15.00")},
    "gpt-4.1": {"provider": "openai", "input_per_1m": Decimal("2.00"), "output_per_1m": Decimal("8.00")},
    "gpt-4o": {"provider": "openai", "input_per_1m": Decimal("2.50"), "output_per_1m": Decimal("10.00")},
    "gpt-4o-mini": {"provider": "openai", "input_per_1m": Decimal("0.15"), "output_per_1m": Decimal("0.60")},
    "gpt-4-turbo": {"provider": "openai", "input_per_1m": Decimal("10.00"), "output_per_1m": Decimal("30.00")},
    "claude-opus-4": {
        "provider": "anthropic",
        "input_per_1m": Decimal("15.00"),
        "output_per_1m": Decimal("75.00"),
    },
    "claude-sonnet-4": {
        "provider": "anthropic",
        "input_per_1m": Decimal("3.00"),
        "output_per_1m": Decimal("15.00"),
    },
    "claude-3-5-sonnet": {
        "provider": "anthropic",
        "input_per_1m": Decimal("3.00"),
        "output_per_1m": Decimal("15.00"),
    },
    "claude-3-5-haiku": {
        "provider": "anthropic",
        "input_per_1m": Decimal("0.80"),
        "output_per_1m": Decimal("4.00"),
    },
}

DEFAULT_PRICING = {
    "provider": "unknown",
    "input_per_1m": Decimal("1.00"),
    "output_per_1m": Decimal("3.00"),
}


def normalize_model_name(model: str | None) -> str:
    if not model:
        return "unknown"
    return model.strip().lower()


def get_model_pricing(model: str | None) -> dict[str, object]:
    key = normalize_model_name(model)
    if key in MODEL_PRICING:
        return MODEL_PRICING[key]
    for registered, pricing in MODEL_PRICING.items():
        if key.startswith(registered) or registered in key:
            return pricing
    return DEFAULT_PRICING


def estimate_cost(
    model: str | None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
) -> Decimal:
    pricing = get_model_pricing(model)
    inp = Decimal(input_tokens or 0)
    out = Decimal(output_tokens or 0)
    cost = (inp / Decimal(1_000_000)) * Decimal(str(pricing["input_per_1m"])) + (
        out / Decimal(1_000_000)
    ) * Decimal(str(pricing["output_per_1m"]))
    return cost.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def infer_provider(model: str | None, explicit: str | None = None) -> str:
    if explicit:
        return explicit
    return str(get_model_pricing(model)["provider"])

"""Usage → cost.

A tiny built-in price table keeps the slice self-contained and deterministic in
tests. In production this is replaced by LiteLLM's `completion_cost` /
`model_cost` map so we track spend at true upstream rates.
"""

from __future__ import annotations

from collections.abc import Mapping

# USD per 1K tokens: model -> (input, output)
PRICES: dict[str, tuple[float, float]] = {
    "gpt-4o": (0.005, 0.015),
    "claude-sonnet": (0.003, 0.015),
}


def cost_of(model: str, usage: Mapping[str, object]) -> float:
    """Compute request cost in USD from an OpenAI-shaped `usage` block."""
    price_in, price_out = PRICES.get(model, (0.0, 0.0))
    prompt = int(usage.get("prompt_tokens", 0) or 0)
    completion = int(usage.get("completion_tokens", 0) or 0)
    return (prompt / 1000) * price_in + (completion / 1000) * price_out

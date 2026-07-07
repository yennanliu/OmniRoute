"""Roll usage events up into dashboard-ready totals (Stage 2)."""

from __future__ import annotations

from collections.abc import Iterable

from .usage import UsageEvent


def _blank() -> dict[str, float]:
    return {"requests": 0, "prompt_tokens": 0, "completion_tokens": 0, "cost": 0.0}


def rollup(events: Iterable[UsageEvent]) -> dict[str, object]:
    """Aggregate events into overall totals plus per-model and per-key breakdowns."""
    totals = _blank()
    by_model: dict[str, dict[str, float]] = {}
    by_key: dict[str, dict[str, float]] = {}

    for e in events:
        buckets = (
            totals,
            by_model.setdefault(e.model, _blank()),
            by_key.setdefault(e.key, _blank()),
        )
        for b in buckets:
            b["requests"] += 1
            b["prompt_tokens"] += e.prompt_tokens
            b["completion_tokens"] += e.completion_tokens
            b["cost"] = round(b["cost"] + e.cost, 10)

    return {"totals": totals, "by_model": by_model, "by_key": by_key}

"""Markup pricing and invoice generation (Stage 4).

Markup is a per-org knob defaulting to 0% (the MixRoute positioning). Invoices
aggregate usage events into per-model line items and apply the org's markup.
`render_invoice` is deterministic so it can be pinned with a golden-file test.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .usage import UsageEvent


def billed_cost(base_cost: float, markup_pct: float) -> float:
    """Apply a percentage markup to an upstream cost."""
    return round(base_cost * (1 + markup_pct / 100), 10)


@dataclass
class InvoiceLine:
    model: str
    requests: int
    prompt_tokens: int
    completion_tokens: int
    base_cost: float


@dataclass
class Invoice:
    org_id: str
    period: str  # e.g. "2026-07"
    markup_pct: float
    lines: list[InvoiceLine] = field(default_factory=list)

    @property
    def subtotal_base(self) -> float:
        return round(sum(line.base_cost for line in self.lines), 10)

    @property
    def total(self) -> float:
        return billed_cost(self.subtotal_base, self.markup_pct)


def generate_invoice(
    *, org_id: str, period: str, events: list[UsageEvent], markup_pct: float = 0.0
) -> Invoice:
    """Build an invoice from usage events, one line per model (sorted by model)."""
    by_model: dict[str, InvoiceLine] = {}
    for e in events:
        line = by_model.get(e.model)
        if line is None:
            line = InvoiceLine(e.model, 0, 0, 0, 0.0)
            by_model[e.model] = line
        line.requests += 1
        line.prompt_tokens += e.prompt_tokens
        line.completion_tokens += e.completion_tokens
        line.base_cost = round(line.base_cost + e.cost, 10)

    lines = [by_model[m] for m in sorted(by_model)]
    return Invoice(org_id=org_id, period=period, markup_pct=markup_pct, lines=lines)


def render_invoice(invoice: Invoice) -> str:
    """Deterministic plain-text rendering (used by the golden-file test)."""
    out = [
        f"INVOICE  org={invoice.org_id}  period={invoice.period}",
        f"markup: {invoice.markup_pct:.1f}%",
        "-" * 60,
        f"{'model':<20}{'reqs':>6}{'in_tok':>10}{'out_tok':>10}{'cost_usd':>12}",
    ]
    for line in invoice.lines:
        out.append(
            f"{line.model:<20}{line.requests:>6}{line.prompt_tokens:>10}"
            f"{line.completion_tokens:>10}{line.base_cost:>12.6f}"
        )
    out += [
        "-" * 60,
        f"{'subtotal':<20}{invoice.subtotal_base:>38.6f}",
        f"{'total (w/ markup)':<20}{invoice.total:>38.6f}",
    ]
    return "\n".join(out) + "\n"

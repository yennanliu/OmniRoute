from pathlib import Path

from app.billing import billed_cost, generate_invoice, render_invoice
from app.usage import UsageEvent

GOLDEN = Path(__file__).parent.parent / "golden" / "invoice_acme_2026-07.txt"


def _events():
    return [
        UsageEvent("1", "sk-a", "gpt-4o", 1000, 500, 0.0125),
        UsageEvent("2", "sk-a", "gpt-4o", 2000, 1000, 0.025),
        UsageEvent("3", "sk-b", "claude-sonnet", 1000, 200, 0.006),
    ]


def test_markup_default_is_zero():
    assert billed_cost(1.0, 0.0) == 1.0


def test_markup_applies_percentage():
    assert billed_cost(1.0, 10.0) == 1.1


def test_invoice_aggregates_by_model_and_totals():
    inv = generate_invoice(org_id="org_acme", period="2026-07", events=_events(), markup_pct=10.0)
    models = {line.model: line for line in inv.lines}
    assert models["gpt-4o"].requests == 2
    assert models["gpt-4o"].prompt_tokens == 3000
    assert inv.subtotal_base == 0.0435
    assert inv.total == 0.04785  # +10%


def test_invoice_matches_golden():
    inv = generate_invoice(org_id="org_acme", period="2026-07", events=_events(), markup_pct=10.0)
    assert render_invoice(inv) == GOLDEN.read_text()

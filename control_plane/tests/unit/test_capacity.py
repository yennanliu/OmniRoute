import pytest

from app.capacity import CapacityLedger, OverCapacityError


def test_commit_and_available():
    ledger = CapacityLedger()
    pool = ledger.commit("openai/us-east-1", 1000)
    assert pool.available == 1000
    ledger.consume("openai/us-east-1", 400)
    assert ledger.pool("openai/us-east-1").available == 600
    assert ledger.pool("openai/us-east-1").utilization == 0.4


def test_commit_respects_provider_ceiling():
    ledger = CapacityLedger(provider_ceilings={"openai": 1500})
    ledger.commit("openai/us-east-1", 1000)
    ledger.commit("openai/eu-west-1", 500)  # total 1500 == ceiling, ok
    with pytest.raises(OverCapacityError):
        ledger.commit("openai/ap-1", 1)  # would exceed ceiling


def test_recommit_same_pool_does_not_double_count():
    ledger = CapacityLedger(provider_ceilings={"openai": 1000})
    ledger.commit("openai/us-east-1", 800)
    ledger.commit("openai/us-east-1", 1000)  # replace, not add — still within ceiling
    assert ledger.pool("openai/us-east-1").committed == 1000


def test_consume_cannot_exceed_committed():
    ledger = CapacityLedger()
    ledger.commit("openai/us-east-1", 100)
    with pytest.raises(OverCapacityError):
        ledger.consume("openai/us-east-1", 101)


def test_reconcile_returns_drift():
    ledger = CapacityLedger()
    ledger.commit("openai/us-east-1", 1000)
    ledger.consume("openai/us-east-1", 300)
    drift = ledger.reconcile("openai/us-east-1", actual_consumed=350)
    assert drift == 50
    assert ledger.pool("openai/us-east-1").consumed == 350

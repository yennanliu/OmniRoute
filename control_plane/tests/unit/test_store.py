from app.store import KeyStore


def test_created_key_has_prefix_and_defaults():
    store = KeyStore()
    rec = store.create()
    assert rec.key.startswith("sk-omni-")
    assert rec.max_budget is None
    assert rec.spend == 0.0
    assert rec.models is None
    assert not rec.budget_exceeded


def test_add_spend_accumulates_and_trips_budget():
    store = KeyStore()
    store.create(max_budget=1.0, key="sk-omni-x")
    assert store.add_spend("sk-omni-x", 0.4) == 0.4
    assert not store.get("sk-omni-x").budget_exceeded
    assert store.add_spend("sk-omni-x", 0.6) == 1.0
    assert store.get("sk-omni-x").budget_exceeded


def test_model_allow_list():
    rec = KeyStore().create(models=("gpt-4o",))
    assert rec.allows("gpt-4o")
    assert not rec.allows("claude-sonnet")

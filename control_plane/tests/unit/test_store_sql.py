"""SqlKeyStore against a real SQLite file — same contract as the in-memory store."""

import pytest

from app.db import make_engine
from app.store_sql import SqlKeyStore


@pytest.fixture
def db_url(tmp_path):
    return f"sqlite:///{tmp_path / 'omniroute.db'}"


def test_create_and_get_roundtrip(db_url):
    store = SqlKeyStore(make_engine(db_url))
    created = store.create(max_budget=5.0, models=("gpt-4o",), key="sk-omni-a")
    fetched = store.get("sk-omni-a")
    assert fetched == created
    assert fetched.models == ("gpt-4o",)


def test_add_spend_is_atomic_and_persisted(db_url):
    store = SqlKeyStore(make_engine(db_url))
    store.create(max_budget=1.0, key="sk-omni-a")
    assert store.add_spend("sk-omni-a", 0.4) == 0.4
    assert store.add_spend("sk-omni-a", 0.6) == 1.0
    assert store.get("sk-omni-a").budget_exceeded


def test_data_survives_a_new_store_instance(db_url):
    SqlKeyStore(make_engine(db_url)).create(max_budget=2.0, key="sk-omni-persist")
    # A fresh store on the same file still sees the key — that's the point of SQLite.
    reopened = SqlKeyStore(make_engine(db_url))
    assert reopened.get("sk-omni-persist").max_budget == 2.0


def test_get_missing_key_returns_none(db_url):
    assert SqlKeyStore(make_engine(db_url)).get("sk-omni-nope") is None

"""SqlSink and SqlAuditLog against a real SQLite file — same contracts, durable."""

from dataclasses import replace

import pytest

from app.audit import verify_chain
from app.audit_sql import SqlAuditLog
from app.db import make_engine
from app.usage import UsageEvent
from app.usage_sql import SqlSink


@pytest.fixture
def engine(tmp_path):
    return make_engine(f"sqlite:///{tmp_path / 'omniroute.db'}")


def _event(request_id="r1", **kw):
    base = dict(key="sk-a", model="gpt-4o", prompt_tokens=5, completion_tokens=1, cost=0.01)
    base.update(kw)
    return UsageEvent(request_id=request_id, **base)


def test_sink_emit_is_idempotent_and_queryable(engine):
    sink = SqlSink(engine)
    assert sink.emit(_event("r1")) is True
    assert sink.emit(_event("r1")) is False  # duplicate request_id ignored
    assert sink.emit(_event("r2")) is True
    assert {e.request_id for e in sink.all_events()} == {"r1", "r2"}


def test_sink_events_survive_a_new_instance(engine):
    SqlSink(engine).emit(_event("r1", cost=0.42))
    assert SqlSink(engine).all_events()[0].cost == 0.42


def test_audit_chain_records_and_verifies(engine):
    log = SqlAuditLog(engine)
    log.record(actor="master", action="create_key", target="sk-1")
    log.record(actor="alice", action="rotate_key", target="sk-1")
    entries = log.entries()

    assert [e.seq for e in entries] == [0, 1]
    assert entries[1].prev_hash == entries[0].entry_hash
    assert log.verify() is True


def test_audit_survives_new_instance_and_detects_tampering(engine):
    SqlAuditLog(engine).record(actor="master", action="create_key", target="sk-1")
    reopened = SqlAuditLog(engine)
    reopened.record(actor="alice", action="delete_key", target="sk-1")

    entries = reopened.entries()
    assert reopened.verify() is True
    tampered = [entries[0], replace(entries[1], action="noop")]
    assert verify_chain(tampered) is False

from dataclasses import replace

from app.audit import InMemoryAuditLog, verify_chain


def test_records_are_chained_and_verify():
    log = InMemoryAuditLog()
    log.record(actor="master", action="create_key", target="sk-1")
    log.record(actor="alice", action="rotate_key", target="sk-1")
    entries = log.entries()

    assert [e.seq for e in entries] == [0, 1]
    assert entries[1].prev_hash == entries[0].entry_hash
    assert log.verify() is True


def test_tampering_breaks_verification():
    log = InMemoryAuditLog()
    log.record(actor="master", action="create_key", target="sk-1")
    log.record(actor="alice", action="delete_key", target="sk-1")
    entries = log.entries()

    # Rewrite history: pretend alice never deleted the key.
    tampered = [entries[0], replace(entries[1], action="noop")]
    assert verify_chain(tampered) is False


def test_log_is_append_only_surface():
    log = InMemoryAuditLog()
    # Only append + read exist — no update/delete methods.
    assert not any(hasattr(log, m) for m in ("update", "delete", "remove", "pop"))

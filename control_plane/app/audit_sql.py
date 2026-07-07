"""SQL-backed audit log (SQLite locally, Postgres in prod).

Satisfies the `AuditLog` protocol. An in-process lock serializes the
read-last-then-append step so the hash chain stays consistent for a single
process; multi-writer deployments should serialize via the database.
"""

from __future__ import annotations

from threading import Lock

from sqlalchemy import Engine

from .audit import GENESIS, AuditEntry, chain_hash, verify_chain
from .db import audit_log


def _to_entry(row: dict) -> AuditEntry:
    return AuditEntry(
        seq=row["seq"],
        actor=row["actor"],
        action=row["action"],
        target=row["target"],
        prev_hash=row["prev_hash"],
        entry_hash=row["entry_hash"],
    )


class SqlAuditLog:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._lock = Lock()

    def record(self, *, actor: str, action: str, target: str) -> AuditEntry:
        with self._lock, self._engine.begin() as conn:
            last = (
                conn.execute(audit_log.select().order_by(audit_log.c.seq.desc()).limit(1))
                .mappings()
                .first()
            )
            seq = last["seq"] + 1 if last else 0
            prev_hash = last["entry_hash"] if last else GENESIS
            entry_hash = chain_hash(seq, actor, action, target, prev_hash)
            conn.execute(
                audit_log.insert().values(
                    seq=seq,
                    actor=actor,
                    action=action,
                    target=target,
                    prev_hash=prev_hash,
                    entry_hash=entry_hash,
                )
            )
        return AuditEntry(seq, actor, action, target, prev_hash, entry_hash)

    def entries(self) -> list[AuditEntry]:
        with self._engine.connect() as conn:
            rows = conn.execute(audit_log.select().order_by(audit_log.c.seq)).mappings().all()
        return [_to_entry(dict(r)) for r in rows]

    def verify(self) -> bool:
        return verify_chain(self.entries())

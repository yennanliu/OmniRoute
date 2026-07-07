"""Append-only, tamper-evident audit log (Stage 4).

Each entry is chained to the previous by hash, so any later mutation breaks
`verify_chain`. `AuditLog` is the seam (a Protocol): `InMemoryAuditLog` for tests
and quick runs; `SqlAuditLog` (see `audit_sql.py`) persists to the shared
database. Timestamps are injected, not read from the clock, to keep it testable.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from threading import Lock
from typing import Protocol

GENESIS = "0" * 64


def chain_hash(seq: int, actor: str, action: str, target: str, prev_hash: str) -> str:
    payload = f"{seq}\x1f{actor}\x1f{action}\x1f{target}\x1f{prev_hash}"
    return hashlib.sha256(payload.encode()).hexdigest()


@dataclass(frozen=True)
class AuditEntry:
    seq: int
    actor: str
    action: str
    target: str
    prev_hash: str
    entry_hash: str


def verify_chain(entries: list[AuditEntry]) -> bool:
    prev_hash = GENESIS
    for i, e in enumerate(entries):
        expected = chain_hash(i, e.actor, e.action, e.target, prev_hash)
        if e.seq != i or e.prev_hash != prev_hash or e.entry_hash != expected:
            return False
        prev_hash = e.entry_hash
    return True


class AuditLog(Protocol):
    def record(self, *, actor: str, action: str, target: str) -> AuditEntry: ...

    def entries(self) -> list[AuditEntry]: ...

    def verify(self) -> bool: ...


class InMemoryAuditLog:
    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []
        self._lock = Lock()

    def record(self, *, actor: str, action: str, target: str) -> AuditEntry:
        with self._lock:
            seq = len(self._entries)
            prev_hash = self._entries[-1].entry_hash if self._entries else GENESIS
            entry = AuditEntry(
                seq=seq,
                actor=actor,
                action=action,
                target=target,
                prev_hash=prev_hash,
                entry_hash=chain_hash(seq, actor, action, target, prev_hash),
            )
            self._entries.append(entry)
            return entry

    def entries(self) -> list[AuditEntry]:
        return list(self._entries)

    def verify(self) -> bool:
        return verify_chain(self._entries)

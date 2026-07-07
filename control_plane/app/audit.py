"""Append-only, tamper-evident audit log (Stage 4).

Each entry is chained to the previous by hash, so any later mutation breaks
`verify_chain`. The log exposes only append + read — there is no update or
delete. Timestamps are injected (not read from the clock) to keep it testable.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


def _hash(seq: int, actor: str, action: str, target: str, prev_hash: str) -> str:
    payload = f"{seq}\x1f{actor}\x1f{action}\x1f{target}\x1f{prev_hash}"
    return hashlib.sha256(payload.encode()).hexdigest()


GENESIS = "0" * 64


@dataclass(frozen=True)
class AuditEntry:
    seq: int
    actor: str
    action: str
    target: str
    prev_hash: str
    entry_hash: str


class AuditLog:
    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []

    def record(self, *, actor: str, action: str, target: str) -> AuditEntry:
        seq = len(self._entries)
        prev_hash = self._entries[-1].entry_hash if self._entries else GENESIS
        entry = AuditEntry(
            seq=seq,
            actor=actor,
            action=action,
            target=target,
            prev_hash=prev_hash,
            entry_hash=_hash(seq, actor, action, target, prev_hash),
        )
        self._entries.append(entry)
        return entry

    def entries(self) -> list[AuditEntry]:
        return list(self._entries)

    def verify(self) -> bool:
        return self.verify_chain(self._entries)

    @staticmethod
    def verify_chain(entries: list[AuditEntry]) -> bool:
        prev_hash = GENESIS
        for i, e in enumerate(entries):
            expected = _hash(i, e.actor, e.action, e.target, prev_hash)
            if e.seq != i or e.prev_hash != prev_hash or e.entry_hash != expected:
                return False
            prev_hash = e.entry_hash
        return True

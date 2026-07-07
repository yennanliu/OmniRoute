"""In-memory key store.

Stage 1 uses this simple, thread-safe store so the vertical slice runs with no
external dependencies. It hides behind a small surface (`create` / `get` /
`add_spend`) so a Postgres-backed implementation can drop in later without
touching callers.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from threading import Lock


@dataclass
class KeyRecord:
    """A virtual API key and its budget state."""

    key: str
    max_budget: float | None = None  # USD; None = unlimited
    spend: float = 0.0
    models: tuple[str, ...] | None = None  # allow-list; None = all models

    @property
    def budget_exceeded(self) -> bool:
        return self.max_budget is not None and self.spend >= self.max_budget

    def allows(self, model: str) -> bool:
        return self.models is None or model in self.models


class KeyStore:
    def __init__(self) -> None:
        self._keys: dict[str, KeyRecord] = {}
        self._lock = Lock()

    def create(
        self,
        *,
        max_budget: float | None = None,
        models: tuple[str, ...] | None = None,
        key: str | None = None,
    ) -> KeyRecord:
        record = KeyRecord(
            key=key or f"sk-omni-{secrets.token_urlsafe(24)}",
            max_budget=max_budget,
            models=models,
        )
        with self._lock:
            self._keys[record.key] = record
        return record

    def get(self, key: str) -> KeyRecord | None:
        return self._keys.get(key)

    def add_spend(self, key: str, amount: float) -> float:
        """Atomically add `amount` to a key's spend; returns the new total."""
        with self._lock:
            record = self._keys[key]
            record.spend += amount
            return record.spend

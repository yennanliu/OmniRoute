"""SQL-backed `KeyStore` (SQLite locally, Postgres in prod).

Satisfies the `KeyStore` protocol, so it drops in wherever `InMemoryKeyStore`
is used. The same code targets either backend via the engine's URL.
"""

from __future__ import annotations

from sqlalchemy import Engine

from .db import keys
from .store import KeyRecord, new_key


def _to_record(row: dict) -> KeyRecord:
    models = row["models"]
    return KeyRecord(
        key=row["key"],
        max_budget=row["max_budget"],
        spend=row["spend"],
        models=tuple(models) if models else None,
    )


class SqlKeyStore:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def create(
        self,
        *,
        max_budget: float | None = None,
        models: tuple[str, ...] | None = None,
        key: str | None = None,
    ) -> KeyRecord:
        record_key = key or new_key()
        with self._engine.begin() as conn:
            conn.execute(
                keys.insert().values(
                    key=record_key,
                    max_budget=max_budget,
                    spend=0.0,
                    models=list(models) if models is not None else None,
                )
            )
        return KeyRecord(key=record_key, max_budget=max_budget, spend=0.0, models=models)

    def get(self, key: str) -> KeyRecord | None:
        with self._engine.connect() as conn:
            row = conn.execute(keys.select().where(keys.c.key == key)).mappings().first()
        return _to_record(dict(row)) if row is not None else None

    def add_spend(self, key: str, amount: float) -> float:
        # `spend = spend + :amount` is applied atomically by the database.
        with self._engine.begin() as conn:
            conn.execute(
                keys.update().where(keys.c.key == key).values(spend=keys.c.spend + amount)
            )
            row = conn.execute(keys.select().where(keys.c.key == key)).mappings().first()
        return float(row["spend"])

"""SQL-backed usage sink (SQLite locally, Postgres in prod).

Satisfies the `EventSink` protocol and doubles as an analytics source. Emit is
idempotent: a duplicate `request_id` violates the primary key and is ignored.
"""

from __future__ import annotations

from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError

from .db import usage_events
from .usage import UsageEvent


def _to_event(row: dict) -> UsageEvent:
    return UsageEvent(
        request_id=row["request_id"],
        key=row["key"],
        model=row["model"],
        prompt_tokens=row["prompt_tokens"],
        completion_tokens=row["completion_tokens"],
        cost=row["cost"],
        status=row["status"],
    )


class SqlSink:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def emit(self, event: UsageEvent) -> bool:
        try:
            with self._engine.begin() as conn:
                conn.execute(usage_events.insert().values(**event.__dict__))
            return True
        except IntegrityError:
            return False  # duplicate request_id

    def all_events(self) -> list[UsageEvent]:
        with self._engine.connect() as conn:
            rows = conn.execute(usage_events.select()).mappings().all()
        return [_to_event(dict(r)) for r in rows]

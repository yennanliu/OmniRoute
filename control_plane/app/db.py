"""Database engine + schema (SQLAlchemy Core).

One portable schema serves both backends — SQLite for local dev, Postgres in
prod — selected purely by the connection URL. Core (not the ORM) keeps this
small and dependency-light; migrations (Alembic) come with the Postgres rollout.
"""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    Column,
    Engine,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
)

metadata = MetaData()

keys = Table(
    "keys",
    metadata,
    Column("key", String, primary_key=True),
    Column("max_budget", Float, nullable=True),
    Column("spend", Float, nullable=False, default=0.0),
    Column("models", JSON, nullable=True),  # list[str] | None
)

usage_events = Table(
    "usage_events",
    metadata,
    Column("request_id", String, primary_key=True),  # idempotency key
    Column("key", String, nullable=False),
    Column("model", String, nullable=False),
    Column("prompt_tokens", Integer, nullable=False),
    Column("completion_tokens", Integer, nullable=False),
    Column("cost", Float, nullable=False),
    Column("status", String, nullable=False),
)

audit_log = Table(
    "audit_log",
    metadata,
    Column("seq", Integer, primary_key=True),  # 0-based chain position
    Column("actor", String, nullable=False),
    Column("action", String, nullable=False),
    Column("target", String, nullable=False),
    Column("prev_hash", String, nullable=False),
    Column("entry_hash", String, nullable=False),
)


def make_engine(url: str) -> Engine:
    """Create an engine and ensure the schema exists.

    Examples:
        sqlite:///omniroute.db                    # local dev (a file)
        postgresql+psycopg://user:pw@host/omni    # production
    """
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, connect_args=connect_args)
    metadata.create_all(engine)
    return engine

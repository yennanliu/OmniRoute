"""Database engine + schema (SQLAlchemy Core).

One portable schema serves both backends — SQLite for local dev, Postgres in
prod — selected purely by the connection URL. Core (not the ORM) keeps this
small and dependency-light; migrations (Alembic) come with the Postgres rollout.
"""

from __future__ import annotations

from sqlalchemy import JSON, Column, Engine, Float, MetaData, String, Table, create_engine

metadata = MetaData()

keys = Table(
    "keys",
    metadata,
    Column("key", String, primary_key=True),
    Column("max_budget", Float, nullable=True),
    Column("spend", Float, nullable=False, default=0.0),
    Column("models", JSON, nullable=True),  # list[str] | None
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

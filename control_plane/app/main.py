"""Application factory.

`create_app` takes its collaborators explicitly (dependency injection), so the
same wiring serves production and tests. `app` is the ASGI entrypoint used by
uvicorn, backed by LiteLLM's Router.
"""

from __future__ import annotations

from fastapi import FastAPI

from .audit import AuditLog
from .completer import Completer, LiteLLMCompleter
from .config import Settings, default_model_list
from .routes import admin, analytics, chat
from .store import InMemoryKeyStore, KeyStore
from .usage import EventSink, InMemorySink


def create_app(
    *,
    store: KeyStore,
    completer: Completer,
    settings: Settings,
    sink: EventSink | None = None,
    audit: AuditLog | None = None,
) -> FastAPI:
    app = FastAPI(title="OmniRoute", version="0.1.0")
    app.state.store = store
    app.state.completer = completer
    app.state.settings = settings
    app.state.sink = sink if sink is not None else InMemorySink()
    app.state.audit = audit if audit is not None else AuditLog()

    app.include_router(chat.router)
    app.include_router(admin.router)
    app.include_router(analytics.router)

    @app.get("/health", tags=["ops"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


def _build_store(settings: Settings) -> KeyStore:
    """SQLite/Postgres if DATABASE_URL is set, else an in-memory store."""
    if settings.database_url:
        from .db import make_engine
        from .store_sql import SqlKeyStore

        return SqlKeyStore(make_engine(settings.database_url))
    return InMemoryKeyStore()


def default_app() -> FastAPI:
    """Production wiring: real settings + LiteLLM-backed completer."""
    settings = Settings()
    return create_app(
        store=_build_store(settings),
        completer=LiteLLMCompleter(model_list=default_model_list()),
        settings=settings,
        sink=InMemorySink(),
    )


app = default_app()

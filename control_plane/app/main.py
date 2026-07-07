"""Application factory.

`create_app` takes its collaborators explicitly (dependency injection), so the
same wiring serves production and tests. `app` is the ASGI entrypoint used by
uvicorn, backed by LiteLLM's Router.
"""

from __future__ import annotations

from fastapi import FastAPI

from .completer import Completer, LiteLLMCompleter
from .config import Settings, default_model_list
from .routes import admin, chat
from .store import KeyStore


def create_app(*, store: KeyStore, completer: Completer, settings: Settings) -> FastAPI:
    app = FastAPI(title="OmniRoute", version="0.1.0")
    app.state.store = store
    app.state.completer = completer
    app.state.settings = settings

    app.include_router(chat.router)
    app.include_router(admin.router)

    @app.get("/health", tags=["ops"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


def default_app() -> FastAPI:
    """Production wiring: real settings + LiteLLM-backed completer."""
    return create_app(
        store=KeyStore(),
        completer=LiteLLMCompleter(model_list=default_model_list()),
        settings=Settings(),
    )


app = default_app()

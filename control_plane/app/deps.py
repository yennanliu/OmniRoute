"""FastAPI dependencies.

State (store, completer, settings) lives on `app.state`, so tests build an app
with a fake completer and a fresh store — no global mutation, no overrides.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status

from .audit import AuditLog
from .completer import Completer
from .config import Settings
from .store import KeyRecord, KeyStore
from .usage import EventSink


def get_store(request: Request) -> KeyStore:
    return request.app.state.store


def get_completer(request: Request) -> Completer:
    return request.app.state.completer


def get_sink(request: Request) -> EventSink:
    return request.app.state.sink


def get_audit(request: Request) -> AuditLog:
    return request.app.state.audit


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def _bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
        )
    return authorization.removeprefix("Bearer ").strip()


def require_key(
    store: Annotated[KeyStore, Depends(get_store)],
    authorization: Annotated[str | None, Header()] = None,
) -> KeyRecord:
    """Authenticate a customer virtual key."""
    token = _bearer_token(authorization)
    record = store.get(token)
    if record is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
    return record


def require_master_key(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """Authenticate an admin/provisioning call."""
    if _bearer_token(authorization) != settings.master_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Master key required"
        )

"""Control-plane provisioning: issue keys and read spend."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from ..audit import AuditLog
from ..deps import get_audit, get_store, require_master_key
from ..schemas import CreateKeyRequest, KeyResponse, SpendResponse
from ..store import KeyRecord, KeyStore

router = APIRouter(prefix="/admin", tags=["control-plane"])


@router.post("/keys", response_model=KeyResponse, status_code=status.HTTP_201_CREATED)
def create_key(
    body: CreateKeyRequest,
    store: Annotated[KeyStore, Depends(get_store)],
    audit: Annotated[AuditLog, Depends(get_audit)],
    _: Annotated[None, Depends(require_master_key)],
) -> KeyResponse:
    record = store.create(
        max_budget=body.max_budget,
        models=tuple(body.models) if body.models is not None else None,
    )
    audit.record(actor="master", action="create_key", target=record.key)
    return _to_key_response(record)


@router.get("/audit")
def list_audit(
    audit: Annotated[AuditLog, Depends(get_audit)],
    _: Annotated[None, Depends(require_master_key)],
) -> dict[str, object]:
    return {
        "verified": audit.verify(),
        "entries": [
            {"seq": e.seq, "actor": e.actor, "action": e.action, "target": e.target}
            for e in audit.entries()
        ],
    }


@router.get("/keys/{key}/spend", response_model=SpendResponse)
def get_spend(
    key: str,
    store: Annotated[KeyStore, Depends(get_store)],
    _: Annotated[None, Depends(require_master_key)],
) -> SpendResponse:
    record = store.get(key)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Key not found")
    return SpendResponse(key=record.key, spend=record.spend, max_budget=record.max_budget)


def _to_key_response(record: KeyRecord) -> KeyResponse:
    return KeyResponse(
        key=record.key,
        max_budget=record.max_budget,
        spend=record.spend,
        models=list(record.models) if record.models is not None else None,
    )

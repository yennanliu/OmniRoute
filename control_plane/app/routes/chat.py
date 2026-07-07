"""The gateway hot path: OpenAI-compatible chat completions."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from ..completer import Completer
from ..deps import get_completer, get_sink, get_store, require_key
from ..pricing import cost_of
from ..schemas import ChatCompletionRequest
from ..store import KeyRecord, KeyStore
from ..usage import EventSink, UsageEvent

router = APIRouter(tags=["gateway"])


@router.post("/v1/chat/completions")
async def chat_completions(
    body: ChatCompletionRequest,
    key: Annotated[KeyRecord, Depends(require_key)],
    completer: Annotated[Completer, Depends(get_completer)],
    store: Annotated[KeyStore, Depends(get_store)],
    sink: Annotated[EventSink, Depends(get_sink)],
) -> dict[str, Any]:
    if key.budget_exceeded:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Budget exceeded"
        )
    if not key.allows(body.model):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Key not permitted to use model '{body.model}'",
        )

    response = await completer.acomplete(
        model=body.model, messages=body.messages, **body.passthrough_params()
    )

    usage = response.get("usage", {}) or {}
    cost = cost_of(body.model, usage)
    # Attribute spend to the key and emit a usage event for analytics.
    store.add_spend(key.key, cost)
    sink.emit(
        UsageEvent.from_response(
            request_id=uuid.uuid4().hex,
            key=key.key,
            model=body.model,
            cost=cost,
            usage=usage,
        )
    )
    return response

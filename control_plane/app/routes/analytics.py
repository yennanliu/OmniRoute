"""Control-plane analytics read APIs (Stage 2)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from ..analytics import rollup
from ..deps import get_sink, require_master_key
from ..usage import EventSink

router = APIRouter(prefix="/admin/analytics", tags=["analytics"])


@router.get("/usage")
def usage_rollup(
    sink: Annotated[EventSink, Depends(get_sink)],
    _: Annotated[None, Depends(require_master_key)],
) -> dict[str, object]:
    if not hasattr(sink, "all_events"):
        # Production reads from Athena over S3, not from the write sink.
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="This sink is not queryable; use the analytics warehouse.",
        )
    return rollup(sink.all_events())

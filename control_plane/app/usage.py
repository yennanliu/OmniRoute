"""Usage events and the sink they flow into (Stage 2).

Every request emits a `UsageEvent`. `EventSink` is the seam: tests and local
runs use `InMemorySink`; production uses `FirehoseSink` (Kinesis Firehose → S3),
per the design doc's usage pipeline. Emitting is idempotent on `request_id` so a
retried callback never double-counts.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class UsageEvent:
    request_id: str
    key: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost: float
    status: str = "success"

    @classmethod
    def from_response(
        cls, *, request_id: str, key: str, model: str, cost: float, usage: Mapping[str, Any]
    ) -> UsageEvent:
        return cls(
            request_id=request_id,
            key=key,
            model=model,
            prompt_tokens=int(usage.get("prompt_tokens", 0) or 0),
            completion_tokens=int(usage.get("completion_tokens", 0) or 0),
            cost=cost,
        )


class EventSink(Protocol):
    def emit(self, event: UsageEvent) -> bool:
        """Record an event. Returns True if newly recorded, False if a duplicate."""
        ...


class InMemorySink:
    """Keeps events in memory and doubles as an analytics source for the slice."""

    def __init__(self) -> None:
        self._events: list[UsageEvent] = []
        self._seen: set[str] = set()

    def emit(self, event: UsageEvent) -> bool:
        if event.request_id in self._seen:
            return False
        self._seen.add(event.request_id)
        self._events.append(event)
        return True

    def all_events(self) -> list[UsageEvent]:
        return list(self._events)


class FirehoseSink:
    """Production sink: puts JSON records to a Kinesis Firehose delivery stream.

    boto3 is imported lazily so tests/local runs never require AWS. Analytics
    reads come from Athena over S3 (a separate source), not from this sink.
    """

    def __init__(self, stream_name: str, *, region: str | None = None) -> None:
        self._stream_name = stream_name
        self._region = region
        self._client: Any | None = None

    def _get_client(self) -> Any:
        if self._client is None:
            import boto3  # lazy; AWS-only dependency

            self._client = boto3.client("firehose", region_name=self._region)
        return self._client

    def emit(self, event: UsageEvent) -> bool:
        import json

        payload = json.dumps(event.__dict__) + "\n"
        self._get_client().put_record(
            DeliveryStreamName=self._stream_name, Record={"Data": payload.encode()}
        )
        return True

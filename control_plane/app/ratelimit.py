"""Per-key request rate limiting (Stage 2, scale).

`RateLimiter` is the seam: `InMemoryRateLimiter` for a single process/tests;
`RedisRateLimiter` (shared counters) keeps limits correct across gateway
replicas, per the design doc. Both use a fixed-window counter keyed by the
current minute.
"""

from __future__ import annotations

from collections import defaultdict
from threading import Lock
from typing import Any, Protocol


class RateLimiter(Protocol):
    def allow(self, key: str, *, limit_per_min: int, minute: int) -> bool:
        """Return True if a request under `key` is allowed in the given minute."""
        ...


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._counts: dict[tuple[str, int], int] = defaultdict(int)
        self._lock = Lock()

    def allow(self, key: str, *, limit_per_min: int, minute: int) -> bool:
        if limit_per_min <= 0:  # 0 / negative means "no limit"
            return True
        with self._lock:
            window = (key, minute)
            if self._counts[window] >= limit_per_min:
                return False
            self._counts[window] += 1
            return True


class RedisRateLimiter:
    """Shared-counter limiter for multi-replica deployments.

    Uses an atomic INCR + EXPIRE on a per-minute key so counts are consistent
    across all gateway tasks. `redis` client is injected.
    """

    def __init__(self, client: Any) -> None:
        self._redis = client

    def allow(self, key: str, *, limit_per_min: int, minute: int) -> bool:
        if limit_per_min <= 0:
            return True
        window = f"rl:{key}:{minute}"
        count = self._redis.incr(window)
        if count == 1:
            self._redis.expire(window, 120)
        return count <= limit_per_min

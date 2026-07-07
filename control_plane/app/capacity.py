"""Reserved-capacity ledger (Stage 3).

Models the MixRoute differentiator: we pre-purchase provider throughput and
track committed vs. consumed per pool (provider/region). Commits are guarded by
a per-provider ceiling; consumption is guarded by what's committed. Reconcile
against real usage to correct drift.
"""

from __future__ import annotations

from dataclasses import dataclass


class OverCapacityError(Exception):
    """Raised when a commit or consume would exceed the allowed limit."""


@dataclass
class Pool:
    name: str  # e.g. "openai/us-east-1"
    committed: float  # reserved units (e.g. tokens/min)
    consumed: float = 0.0

    @property
    def available(self) -> float:
        return self.committed - self.consumed

    @property
    def utilization(self) -> float:
        return self.consumed / self.committed if self.committed else 0.0


class CapacityLedger:
    def __init__(self, provider_ceilings: dict[str, float] | None = None) -> None:
        # provider -> max total units we may commit across its pools
        self._ceilings = provider_ceilings or {}
        self._pools: dict[str, Pool] = {}

    def _provider_of(self, pool_name: str) -> str:
        return pool_name.split("/", 1)[0]

    def _committed_for_provider(self, provider: str) -> float:
        return sum(
            p.committed for p in self._pools.values() if self._provider_of(p.name) == provider
        )

    def commit(self, pool_name: str, units: float) -> Pool:
        """Reserve capacity for a pool, respecting the provider ceiling."""
        provider = self._provider_of(pool_name)
        ceiling = self._ceilings.get(provider)
        existing = self._pools.get(pool_name)
        already = existing.committed if existing else 0.0
        projected = self._committed_for_provider(provider) - already + units
        if ceiling is not None and projected > ceiling:
            raise OverCapacityError(
                f"commit {units} to {pool_name} exceeds {provider} ceiling {ceiling}"
            )
        if existing:
            existing.committed = units
        else:
            self._pools[pool_name] = Pool(name=pool_name, committed=units)
        return self._pools[pool_name]

    def consume(self, pool_name: str, units: float) -> Pool:
        """Draw down committed capacity; refuse to over-consume."""
        pool = self._pools[pool_name]
        if pool.consumed + units > pool.committed:
            raise OverCapacityError(
                f"consume {units} from {pool_name} exceeds available {pool.available}"
            )
        pool.consumed += units
        return pool

    def reconcile(self, pool_name: str, actual_consumed: float) -> float:
        """Correct consumed to the measured value; return the drift (actual - tracked)."""
        pool = self._pools[pool_name]
        drift = actual_consumed - pool.consumed
        pool.consumed = actual_consumed
        return drift

    def pool(self, pool_name: str) -> Pool:
        return self._pools[pool_name]

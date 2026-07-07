"""Smart deployment selection (Stage 3).

A pure, testable selection function that mirrors the intent of LiteLLM's
`usage-based-routing-v2` / `cost-based` strategies: among healthy deployments of
a model group, pick by lowest utilization or lowest cost, skipping any that are
cooling down or lack the requested headroom. In production this informs the
LiteLLM Router config; here it's isolated so the logic is unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Deployment:
    id: str
    model_name: str
    tpm_limit: int
    tpm_used: int = 0
    cost_per_1k: float = 0.0
    region: str = ""
    cooling_down: bool = False

    @property
    def tpm_available(self) -> int:
        return self.tpm_limit - self.tpm_used

    @property
    def utilization(self) -> float:
        return self.tpm_used / self.tpm_limit if self.tpm_limit else 1.0


def select_deployment(
    deployments: list[Deployment],
    *,
    strategy: str = "usage-based",
    need_tpm: int = 0,
) -> Deployment | None:
    """Return the best healthy deployment, or None if none can serve the request."""
    healthy = [
        d for d in deployments if not d.cooling_down and d.tpm_available >= need_tpm
    ]
    if not healthy:
        return None
    if strategy == "cost-based":
        return min(healthy, key=lambda d: (d.cost_per_1k, d.utilization))
    if strategy == "usage-based":
        return min(healthy, key=lambda d: (d.utilization, d.cost_per_1k))
    # simple-shuffle fallback: first healthy (deterministic for tests)
    return healthy[0]

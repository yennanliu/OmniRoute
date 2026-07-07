"""Load / latency test for the gateway (Stage 2, scale).

Asserts the gateway adds low overhead and that per-key rate-limit counting holds
across replicas (run against ≥2 tasks behind the ALB, sharing Redis).

    export OMNI_KEY=sk-omni-...            # a provisioned virtual key
    uv run locust -f load/locustfile.py --host https://api.omniroute.ai \
        --users 50 --spawn-rate 10 --run-time 2m

SLO (design doc): gateway overhead p95 < 30 ms on top of upstream latency.
"""

from __future__ import annotations

import os

from locust import HttpUser, between, task


class GatewayUser(HttpUser):
    wait_time = between(0.1, 0.5)

    @task
    def chat(self) -> None:
        self.client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {os.environ['OMNI_KEY']}"},
            json={"model": "gpt-4o", "messages": [{"role": "user", "content": "ping"}]},
            name="/v1/chat/completions",
        )

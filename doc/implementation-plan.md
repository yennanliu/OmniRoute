# OmniRoute — Implementation Plan

**Companion to [`system-design.md`](./system-design.md)**

| | |
|---|---|
| **Status** | Draft v1.0 |
| **Date** | 2026-07-07 |
| **Approach** | Test-Driven Development (TDD), trunk-based, incremental |
| **Stack** | Python 3.12 · uv · FastAPI · LiteLLM · pytest · PostgreSQL · Redis · Terraform · AWS |

This document turns the architecture into an executable, test-first delivery plan: how we work (TDD loop, tooling), what we build (stages with entry/exit criteria), and how we verify each stage.

---

## 1. Engineering Principles

1. **Test-first.** No production code without a failing test that demands it. Red → Green → Refactor, small commits.
2. **Outside-in.** Start from an API/contract test (what the client sees), drop to unit tests for the internals it forces into existence.
3. **Vertical slices.** Each stage delivers a thin end-to-end capability that runs and is demoable, not a horizontal layer.
4. **Fast feedback.** Unit + contract suite < 60s locally. Slow/integration tests gated separately.
5. **Deterministic tests.** Upstream LLM providers are always mocked in unit/contract tests; real-provider calls live in a small, quarantined "smoke" suite.
6. **Config as code.** LiteLLM `config.yaml`, Terraform, and CI are versioned and reviewed like source.

---

## 2. Tooling & Project Setup (uv)

```bash
# Bootstrap
uv init omniroute && cd omniroute
uv add fastapi "uvicorn[standard]" litellm sqlalchemy asyncpg redis \
       pydantic pydantic-settings httpx stripe
uv add --dev pytest pytest-asyncio pytest-cov respx httpx \
       testcontainers ruff mypy pre-commit locust

uv sync                 # resolve + create .venv, write uv.lock
uv run pytest           # run the suite
uv run ruff check .
uv run mypy .
```

- **`uv.lock` is committed.** Docker builds use `uv sync --frozen` for reproducibility.
- **`uv run <cmd>`** is the single entrypoint for tests/lint/app — no manual venv activation.
- **pre-commit** runs `ruff` (lint+format) and `mypy` on staged files.

### Test tooling roles

| Tool | Purpose |
|---|---|
| `pytest` + `pytest-asyncio` | test runner, async support |
| `httpx.ASGITransport` / `TestClient` | drive FastAPI without a live server |
| `respx` | mock upstream provider HTTP calls (deterministic LLM responses) |
| `testcontainers` | ephemeral Postgres + Redis for integration tests |
| `pytest-cov` | coverage gate (fail under threshold) |
| `locust` | load / latency tests for the gateway |

### Layout (test-first mirror)

```
omniroute/
├── pyproject.toml · uv.lock
├── control_plane/
│   ├── app/ (api, models, services, main.py)
│   └── tests/ (unit/, contract/, integration/)
├── gateway/
│   ├── config.yaml
│   ├── shim/ (auth hooks, callbacks, custom routing)
│   └── tests/
├── infra/            # Terraform + `terraform test` / terratest
└── doc/
```

---

## 3. The TDD Loop (per feature)

```
1. Write a failing contract/API test describing the behavior a client needs.   (RED)
2. Run it — confirm it fails for the right reason.
3. Write the minimum code (route → service → model) to pass.                    (GREEN)
4. Add unit tests for edge cases the implementation now exposes.
5. Refactor with the suite green; commit.                                       (REFACTOR)
6. If it touches infra/hot path, add an integration/load test before merge.
```

**Example — first test written for Stage 1 (before any app code):**

```python
# control_plane/tests/contract/test_chat_completions.py
import pytest, respx, httpx
from httpx import ASGITransport, AsyncClient
from app.main import app

@pytest.mark.asyncio
@respx.mock
async def test_chat_completion_proxies_to_provider_and_records_spend(db, redis):
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={
            "choices": [{"message": {"role": "assistant", "content": "hi"}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 6},
        })
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post("/v1/chat/completions",
                         headers={"Authorization": "Bearer sk-omni-test"},
                         json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 200
    assert r.json()["choices"][0]["message"]["content"] == "hi"
    # behavior we're driving out: spend must be recorded for this key
    assert await get_spend(db, key="sk-omni-test") > 0
```

This one test forces into existence: the route, auth/key validation, the LiteLLM call, and the spend-recording hook — each then covered by its own unit tests.

---

## 4. Delivery Stages

Each stage is a shippable vertical slice with explicit **exit criteria** (all green tests + a demoable behavior). Maps onto the rollout phases in the design doc.

### Stage 0 — Walking skeleton (Spike)
**Goal:** prove the unified API + failover end-to-end, minimal ceremony.

- LiteLLM Proxy running locally via Docker with a 2-provider `config.yaml` (e.g. OpenAI + Bedrock, one shared `model_name` + a `fallbacks` chain).
- `master_key` auth only; no DB persistence yet.
- **Tests:** contract test hits `/v1/chat/completions` (respx-mocked providers) and asserts a normalized OpenAI-shaped response; a failover test where the primary deployment returns 429 and the request succeeds on the fallback.
- **Exit:** `uv run pytest gateway/tests` green; manual curl through the proxy returns a completion and survives a simulated primary outage.

### Stage 1 — MVP control plane (keys, budgets, spend)
**Goal:** the smallest real product — a customer can get a virtual key with a budget and be billed for usage.

- **Data:** Postgres schema for `organization`, `team`, `virtual_key`, `wallet`, `spend_log`. Alembic migrations (migration tested against a `testcontainers` Postgres).
- **Provisioning service:** create/rotate virtual keys by calling LiteLLM admin API (`/key/generate`, `/team/new`) with `max_budget`, `rpm/tpm`, model allow-list. Unit-tested against a mocked LiteLLM admin client.
- **Spend + wallet:** LiteLLM success callback → record spend, decrement prepaid wallet (Redis counter + Postgres). Budget-exceeded → 429 to client (contract test).
- **Auth:** `sk-omni-...` validation with Redis cache + short TTL; fail-open behavior on Redis outage is explicitly tested.
- **Billing:** Stripe prepaid top-up (webhook handler tested with signed fixture payloads).
- **Tests:** contract suite for the OpenAI-compatible surface; unit suite for services; integration suite (testcontainers Postgres+Redis) for provisioning + spend; coverage gate ≥ 85% on control_plane.
- **Exit:** a scripted e2e — create org → issue key → make N calls → wallet debited → budget cap enforced → spend visible via API — passes in CI.

### Stage 2 — Analytics & scale
**Goal:** real-time visibility and horizontal scale.

- **Usage pipeline:** custom async LiteLLM callback → Kinesis Firehose → S3 (+ optional ClickHouse). Callback is unit-tested (event shape/idempotency); pipeline validated with a localstack/testcontainers integration test.
- **Dashboard read APIs:** per-model / per-key rollups; contract-tested.
- **Scale:** stateless gateway confirmed via a `locust` load test asserting p95 overhead < 30 ms and correct rate-limit counting across ≥ 2 replicas (shared Redis).
- **Exit:** load test meets latency/limit SLOs; dashboard shows live spend within seconds of a request.

### Stage 3 — Reserved capacity & smart routing
**Goal:** the MixRoute differentiator.

- **Capacity ledger** (control plane): committed vs. consumed per provider/region; tests for reconciliation math and over-commit guards.
- **Routing upgrades:** enable `usage-based-routing-v2` / `cost-based` for hot model groups; tests assert selection honors `tpm`/cost constraints and skips cooled-down deployments.
- **Multi-region provider pools:** config-driven; failover test across regions.
- **Exit:** simulated peak-load test shows no upstream 429 breach of reserved limits and correct cross-region distribution.

### Stage 4 — Enterprise
**Goal:** orgs/teams RBAC, per-org markup/pricing, invoicing, audit logs, SSO.

- RBAC policy tests (allow/deny matrices), markup/pricing-engine unit tests (0% default → per-org override), invoice-generation golden-file tests, audit-log append-only tests, SSO/OIDC login flow tests.
- **Exit:** enterprise acceptance scenarios pass; audit log immutable; invoices reconcile against spend logs to the cent.

---

## 5. Infrastructure & CI/CD (also test-driven)

- **Terraform** for VPC, ECS Fargate, Aurora, ElastiCache, IAM, Secrets, CloudFront. Validate with `terraform validate` + `terraform test` (or terratest) in CI; plan-on-PR, apply-on-merge via GitHub Actions → OIDC to AWS (no long-lived keys).
- **Images:** gateway pins a specific `ghcr.io/berriai/litellm` tag + our `config.yaml`; control plane built with `uv sync --frozen`. Scanned (trivy) in CI.
- **Pipeline (GitHub Actions):**
  1. `uv sync --frozen`
  2. `uv run ruff check` + `uv run mypy`
  3. `uv run pytest` (unit + contract) — fast gate
  4. integration tests (testcontainers) — on PR
  5. build/scan images → push to ECR
  6. deploy to staging (blue/green via CodeDeploy) → run smoke suite (real providers, tiny budget)
  7. promote to prod on approval
- **Quality gates (block merge):** all suites green, coverage ≥ threshold, no ruff/mypy errors, Terraform plan clean.

---

## 6. Definition of Done (per feature)

- [ ] Failing test written first; now green.
- [ ] Edge cases unit-tested; error paths covered.
- [ ] `ruff` + `mypy` clean; coverage gate met.
- [ ] Contract test for any client-visible behavior.
- [ ] Integration test if it touches DB/Redis/infra; load test if it touches the hot path.
- [ ] Docs/config updated; migration reversible.
- [ ] Reviewed, merged to trunk, deployed to staging, smoke-tested.

---

## 7. Test Taxonomy

| Layer | Scope | Deps | Speed | Runs |
|---|---|---|---|---|
| **Unit** | one function/service | all mocked | ms | every save / CI |
| **Contract** | FastAPI route ↔ client shape | ASGI transport, respx | ms–s | every save / CI |
| **Integration** | DB/Redis/pipeline real | testcontainers/localstack | s | PR / CI |
| **Load** | gateway latency & limits | staging-like | min | pre-merge on hot-path changes |
| **Smoke** | real providers, real AWS | staging | min | post-deploy, quarantined |

---

## 8. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| LiteLLM behavior drift on upgrade | pin image tag; contract tests catch shape changes; upgrade in staging first |
| Flaky tests from real providers | providers mocked everywhere except the small smoke suite |
| Spend/wallet race conditions | Redis atomic ops; integration tests with concurrent calls; reconcile against Postgres |
| Hot-path latency regressions | `locust` gate on p95 overhead; alarms in prod |
| Test suite slows delivery | strict layer separation; fast gate < 60s; slow tests parallelized/gated |

---

### References

- System design — [`system-design.md`](./system-design.md)
- LiteLLM — https://docs.litellm.ai/docs/
- uv — https://docs.astral.sh/uv/
- pytest — https://docs.pytest.org/
- FastAPI testing — https://fastapi.tiangolo.com/tutorial/testing/

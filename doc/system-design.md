# OmniRoute — System Design Document

**An LLM API Gateway / Router (a MixRoute.ai‑style product)**

| | |
|---|---|
| **Status** | Draft v1.0 |
| **Date** | 2026-07-07 |
| **Owner** | Platform Team |
| **Stack** | Python 3.12 · uv · FastAPI · LiteLLM · PostgreSQL · Redis · AWS |
| **Reference product** | [mixroute.ai](https://mixroute.ai/zh-hant/) |

---

## 1. Overview

OmniRoute is a multi-provider **LLM gateway**: a single OpenAI-compatible API endpoint and API key that fans out to 200+ models across OpenAI, Anthropic, Google, Bedrock, Mistral, DeepSeek, and others. It provides intelligent routing, automatic failover, per-tenant virtual keys, budgets, spend tracking, and a usage-analytics dashboard.

We build it on top of **[LiteLLM](https://docs.litellm.ai/docs/)**, which already solves provider normalization, routing, load balancing, retries, fallbacks, virtual keys, and spend tracking. Our job is to wrap LiteLLM with a **control plane** (accounts, billing, dashboard, quotas, provisioning) and operate it reliably on **AWS**.

### 1.1 Goals

- **Unified API** — one base URL + one key, OpenAI SDK-compatible (drop-in `base_url` change).
- **Reliability** — automatic millisecond failover across providers/regions; survive single-provider 429s and outages.
- **Cost transparency** — real-time per-model / per-key spend, consolidated billing, configurable markup (MixRoute markets 0%; we make it a config knob).
- **Multi-tenancy** — organizations → teams → virtual keys, each with budgets and rate limits.
- **Observability** — token/latency/error dashboards per tenant and per model.

### 1.2 Non-Goals (v1)

- Training / fine-tuning orchestration.
- Building our own inference (we broker upstream providers only).
- On-prem / self-host distribution (SaaS first).

### 1.3 What we buy vs. build

| Capability | Source |
|---|---|
| Provider normalization, `/chat/completions`, `/embeddings`, streaming | **LiteLLM** (buy/OSS) |
| Routing strategies, fallbacks, retries, cooldowns, load balancing | **LiteLLM Router** |
| Virtual keys, budgets, rate limits, spend logs | **LiteLLM Proxy** |
| Accounts, orgs, billing, invoices, top-ups | **Build** (Control-plane API) |
| Marketing site, customer dashboard | **Build** (Next.js/React) |
| Provisioning, quotas, reserved-capacity accounting | **Build** |

---

## 2. High-Level Architecture

```
                          ┌───────────────────────────────────────────┐
   Customer app           │                  AWS                        │
   (OpenAI SDK,           │                                             │
    base_url=api.         │   ┌──────────┐      ┌──────────────────┐    │
    omniroute.ai) ──────► │   │  ALB /   │────► │  Gateway (Data    │    │
                          │   │ API GW +  │      │  Plane)           │    │
                          │   │ CloudFront│      │  LiteLLM Proxy    │────┼──► OpenAI
                          │   └──────────┘      │  on ECS Fargate   │    │──► Anthropic
                          │        │            │  (FastAPI wrapper)│    │──► Bedrock
   Dashboard (web) ───────┼────────┘            └───────┬──────────┘    │──► Google / etc.
                          │                             │                │
                          │   ┌──────────────┐   ┌──────▼───────┐        │
                          │   │ Control Plane │   │  RDS Postgres│        │
                          │   │ FastAPI (ECS) │──►│ (keys/spend/ │        │
                          │   │ orgs, billing │   │  orgs/logs)  │        │
                          │   └──────┬────────┘   └──────────────┘        │
                          │          │            ┌──────────────┐        │
                          │          └───────────►│ ElastiCache  │        │
                          │                       │ Redis (rl/   │        │
                          │                       │ router/cache)│        │
                          │   ┌──────────────┐    └──────────────┘        │
                          │   │ Analytics:    │   ┌──────────────┐        │
                          │   │ S3 + Athena / │◄──│ Kinesis/SQS  │        │
                          │   │ ClickHouse    │   │ (usage events)│       │
                          │   └──────────────┘   └──────────────┘        │
                          └───────────────────────────────────────────┘
```

Two logical planes:

- **Data plane** — the hot path serving inference. LiteLLM Proxy (optionally behind a thin FastAPI shim for custom auth/quotas). Must be low-latency, horizontally scalable, stateless per request.
- **Control plane** — accounts, billing, provisioning, dashboard API. Lower QPS, can tolerate higher latency, owns the source-of-truth data.

They share **Postgres** (keys, spend) and **Redis** (rate limits, router state, cache).

---

## 3. Component Design

### 3.1 Gateway (Data Plane) — LiteLLM Proxy + FastAPI shim

The gateway exposes OpenAI-compatible routes: `/v1/chat/completions`, `/v1/completions`, `/v1/embeddings`, `/v1/models`, `/v1/rerank`, `/v1/audio/*`, `/v1/images/*` (whatever LiteLLM supports upstream).

**Deployment options:**

1. **LiteLLM Proxy directly** (fastest path to launch). Configure via `config.yaml`; run the `ghcr.io/berriai/litellm` image on ECS Fargate.
2. **FastAPI shim → LiteLLM Router (SDK)**. Use when we need custom logic LiteLLM Proxy doesn't expose: reserved-capacity accounting, custom markup billing, our own auth model, request shaping. The shim calls `litellm.Router.acompletion(...)` in-process.

**Recommendation:** Start with option 1 + LiteLLM's callback hooks / custom auth for launch speed; graduate the shim (option 2) only where the proxy's extensibility (custom auth, `async_pre_call_hook`, custom routing strategy) is insufficient.

**Routing (LiteLLM Router).** Multiple upstream deployments share one `model_name` (e.g. `gpt-4o` served by both `azure/...` and `openai/...`). Strategy per model group:

- `simple-shuffle` (default, weighted by `rpm`/`tpm`) — best latency, our default.
- `usage-based-routing-v2` / `latency-based` — for hot models where we want smarter balancing (needs Redis).
- `cost-based` — to prefer cheapest healthy deployment.

**Reliability config:** `num_retries`, `allowed_fails`, `cooldown_time`, per-deployment `timeout`, and `fallbacks` chains (primary group → backup group). This is the core of the "millisecond failover / no 429" selling point.

Example `config.yaml`:

```yaml
model_list:
  - model_name: gpt-4o
    litellm_params:
      model: azure/gpt-4o
      api_base: os.environ/AZURE_API_BASE
      api_key: os.environ/AZURE_API_KEY
      rpm: 900
      tpm: 300000
    model_info: { id: azure-4o-primary, region: eastus }

  - model_name: gpt-4o
    litellm_params:
      model: openai/gpt-4o
      api_key: os.environ/OPENAI_API_KEY
      rpm: 1000
      tpm: 500000
    model_info: { id: openai-4o-backup }

  - model_name: claude-sonnet
    litellm_params:
      model: bedrock/anthropic.claude-sonnet-...
      aws_region_name: us-east-1

router_settings:
  routing_strategy: simple-shuffle
  num_retries: 3
  allowed_fails: 3
  cooldown_time: 30
  redis_host: os.environ/REDIS_HOST
  redis_port: os.environ/REDIS_PORT
  redis_password: os.environ/REDIS_PASSWORD

litellm_settings:
  fallbacks:
    - gpt-4o: ["claude-sonnet"]        # cross-provider failover
  drop_params: true
  set_verbose: false

general_settings:
  master_key: os.environ/LITELLM_MASTER_KEY
  database_url: os.environ/DATABASE_URL
```

**Secrets:** upstream provider keys live in **AWS Secrets Manager**, injected as env vars / referenced via `os.environ/...`. Never in the config repo.

### 3.2 Control Plane — FastAPI service

Owns everything LiteLLM doesn't: signup, orgs/teams, human-facing key management, wallet/credits, invoices, reserved-capacity ledger, model catalog/pricing, and the dashboard's read APIs.

**Key responsibilities:**

- **Account model**: `Organization → Team → User`, and `VirtualKey` belonging to a team. Mirrors and provisions into LiteLLM's key store via LiteLLM's `/key/generate`, `/team/new`, `/user/new` management endpoints.
- **Provisioning**: when a customer creates a key in our dashboard, control plane calls LiteLLM's admin API to create the underlying virtual key with the right `max_budget`, `rpm_limit`, `tpm_limit`, `models` allow-list, and `metadata` (org/team ids).
- **Billing**: reads LiteLLM `spend` logs (Postgres) + usage events, applies pricing (upstream cost × (1 + markup)), decrements prepaid wallet or accrues postpaid, generates invoices, integrates **Stripe**.
- **Pricing/markup engine**: markup is a config knob per plan (default 0% to match MixRoute's positioning; can be per-org negotiated).

FastAPI app, async SQLAlchemy over RDS, Pydantic v2 schemas, JWT/session auth for the dashboard.

### 3.3 Data stores

| Store | Purpose | AWS service |
|---|---|---|
| **PostgreSQL** | LiteLLM virtual keys, spend logs, teams; our orgs, wallets, invoices | RDS (Aurora PostgreSQL, Multi-AZ) |
| **Redis** | Router state, rate-limit counters, response cache, cooldowns | ElastiCache for Redis (cluster mode) |
| **Object store** | Raw usage-event archive, request/response logs (opt-in), invoices | S3 |
| **Analytics** | Aggregated usage for dashboards | S3 + Athena, or ClickHouse on ECS for low-latency dashboards |
| **Secrets** | Provider keys, master key, DB creds | Secrets Manager |

**Why two consumers of one Postgres:** LiteLLM already writes spend to Postgres. The control plane reads those tables (or a replica) for billing rather than duplicating tracking. Use a **read replica** for dashboard/billing queries so analytics load never touches the hot spend-write path.

### 3.4 Usage pipeline & analytics

LiteLLM emits a callback on every request (success/failure) with model, tokens, latency, cost, key/team metadata. We register a **custom async callback** that pushes a structured event to **Kinesis Data Firehose → S3** (and optionally ClickHouse for sub-second dashboards). The dashboard reads pre-aggregated rollups (per model, per key, per hour/day). Firehose buffering keeps the hot path from blocking on analytics writes.

### 3.5 Dashboard (web)

Next.js/React SPA on CloudFront + S3. Talks only to the control-plane API. Screens: real-time spend & token charts, per-model breakdown, key management, budget alerts, invoices, provider-status page.

---

## 4. Request Lifecycle (hot path)

```
1. Client → POST api.omniroute.ai/v1/chat/completions  (Authorization: Bearer sk-omni-...)
2. CloudFront → ALB → Gateway task (ECS Fargate)
3. Auth: LiteLLM validates virtual key (Postgres, cached in Redis)
        → checks budget, rpm/tpm, model allow-list
4. Route: Router selects a healthy deployment for the model group
        (strategy + rpm/tpm weights, skips cooled-down deployments)
5. Call upstream provider (Secrets Manager creds); on failure →
        retry (num_retries) → fallback model group → next deployment
6. Stream response back (SSE) to client
7. Post-call: write spend to Postgres, decrement wallet counters (Redis),
        emit usage event → Kinesis → S3/ClickHouse
```

Latency budget: gateway overhead target **< 30 ms p50** on top of upstream latency. Streaming responses proxied token-by-token.

---

## 5. Multi-Tenancy, Quotas & Reliability

- **Isolation:** every request is attributed to a virtual key → team → org. Budgets and `rpm`/`tpm` enforced by LiteLLM at key and team level, backed by Redis counters so limits hold across all gateway replicas.
- **Reserved capacity** (MixRoute's differentiator): we pre-purchase provider throughput and model it as internal capacity pools. The router's `rpm`/`tpm` per deployment reflect our reserved allotment; usage-based routing keeps us under provider ceilings and spreads across regions/timezones for 24/7 utilization. A capacity-ledger (control plane) tracks committed vs. consumed.
- **Failover:** retries + cross-provider `fallbacks` + per-deployment cooldowns give the "no 429 / millisecond switch" behavior. Health of deployments tracked in Redis.
- **Graceful degradation:** if Redis is down, fail open on rate limiting (log & alert) rather than dropping all traffic; if Postgres is down, cache key validation in Redis with a short TTL.

---

## 6. AWS Deployment

### 6.1 Topology

- **VPC** with public subnets (ALB, NAT) and private subnets (ECS tasks, RDS, ElastiCache).
- **Compute:** **ECS Fargate** (start here — no node management). Services:
  - `gateway` (LiteLLM Proxy) — CPU-light, autoscale on RPS/CPU, min 2 tasks across 2 AZs.
  - `control-plane` (FastAPI) — smaller, autoscale on CPU.
  - (optional) `clickhouse` for analytics.
  - Migrate to **EKS** later if we outgrow Fargate scaling/cost or need finer control.
- **Ingress:** CloudFront → ALB (TLS via ACM) → ECS. Consider **API Gateway** only if we need usage plans/WAF at that layer; ALB is cheaper for high-throughput streaming.
- **Data:** Aurora PostgreSQL (Multi-AZ), ElastiCache Redis (cluster mode, Multi-AZ), S3, Secrets Manager, Kinesis Firehose.
- **DNS/TLS:** Route 53 + ACM.
- **WAF** on CloudFront/ALB for abuse protection.

### 6.2 Deployment style: server vs. serverless (AWS-native)

A recurring question: *do we still need a running Python server, or can this be pure AWS-native/serverless?* The answer differs by plane.

**The gateway (hot path) must be a long-lived server.** It:

- holds **streaming (SSE)** connections open token-by-token for seconds to minutes,
- keeps **provider connection pools** and **router state** (cooldowns, latency/usage stats) warm in memory,
- must add < 30 ms overhead per request.

**Lambda is a poor fit for the gateway:** 15-minute cap, cold starts on a latency-critical path, awkward response streaming, and you pay for wall-clock time *while blocked waiting on slow upstream LLMs* — which gets expensive fast at scale. And there is **no AWS-native service that *is* a multi-provider LLM router** — Bedrock only fronts AWS-hosted models. Going "pure native" would collapse OmniRoute into a Bedrock-only product, i.e. a different, smaller product that loses the core value prop (200+ models, cross-provider failover). So the gateway stays a **persistent container (LiteLLM on ECS Fargate)**.

**The control plane is the negotiable part.** Account/key/billing/dashboard APIs are low-QPS CRUD and *can* go serverless.

| Concern | Server (container) | AWS-native / serverless alternative | Verdict |
|---|---|---|---|
| Multi-provider routing, failover, unified API | LiteLLM on Fargate | ❌ none (Bedrock = AWS models only) | **Server — mandatory** |
| Edge auth / rate limit / abuse | shim logic | API Gateway usage plans + WAF + Cognito | Native OK at edge |
| Control-plane CRUD (orgs, keys, billing) | FastAPI on Fargate | API Gateway + Lambda + DynamoDB | Either; see below |
| Usage pipeline | callback code | Kinesis Firehose → S3 → Athena | **Native (already in design)** |
| Scheduled jobs (invoicing, reconciliation) | worker process | EventBridge + Step Functions + Lambda | **Native — preferred** |

**Recommendation for v1:** keep **both gateway and control plane as FastAPI/LiteLLM containers on Fargate** — one language, one deploy model, fewer moving parts. Use AWS-native serverless where it's already the obvious fit: the **usage pipeline** (Firehose/S3/Athena) and **scheduled/async jobs** (EventBridge + Step Functions + Lambda). Peel the control plane onto Lambda + DynamoDB *later* only if the idle cost of a second Fargate service actually justifies splitting the stack across two runtimes.

**Bottom line:** the gateway is irreducibly a Python server; the rest is a hybrid — container core + serverless glue.

### 6.3 Scaling

- Gateway is **stateless** → scale horizontally on RPS/CPU; Redis holds shared rate-limit/router state so counters are correct across tasks.
- Aurora read replica for billing/dashboard queries.
- Redis cluster mode for >1000 RPS (LiteLLM recommends Redis at that scale).
- Provider concurrency capped by reserved capacity, not our fleet size — autoscaling protects against our own overload, capacity ledger protects providers.

### 6.4 IaC & CI/CD

- **Terraform** for all AWS infra (VPC, ECS, RDS, ElastiCache, IAM, Secrets, CloudFront). LiteLLM publishes Terraform modules we can reference.
- **Docker** images: gateway pins a specific `ghcr.io/berriai/litellm` tag + our `config.yaml`; control plane is our own image built with **uv**.
- **CI/CD:** GitHub Actions → build/test with `uv` → push to ECR → deploy to ECS (blue/green via CodeDeploy). Config changes to `config.yaml` are versioned and rolled out the same way.

---

## 7. Python Project & Tooling

- **Python 3.12**, dependency + venv management with **uv** (`uv init`, `uv add fastapi litellm sqlalchemy asyncpg redis pydantic pydantic-settings stripe`, `uv sync`, `uv run`). `uv.lock` committed for reproducible builds; Docker build uses `uv sync --frozen`.
- **FastAPI** for the control plane (and the optional gateway shim). Async throughout (`asyncpg`, `httpx`, async SQLAlchemy).
- **Testing:** `pytest` + `pytest-asyncio`; contract tests against a mocked upstream; load tests with `locust`/`k6`.
- **Quality:** `ruff` (lint+format), `mypy`, pre-commit.

Suggested layout:

```
omniroute/
├── pyproject.toml            # uv-managed
├── uv.lock
├── gateway/                  # LiteLLM config + optional FastAPI shim
│   ├── config.yaml
│   ├── Dockerfile
│   └── shim/                 # custom auth hooks, callbacks, routing
├── control_plane/            # FastAPI app
│   ├── app/
│   │   ├── api/              # orgs, keys, billing, dashboard routes
│   │   ├── models/           # SQLAlchemy
│   │   ├── services/         # billing, provisioning (→ LiteLLM admin API)
│   │   └── main.py
│   └── Dockerfile
├── infra/                    # Terraform
└── doc/
    └── system-design.md
```

---

## 8. Security

- **Customer auth:** virtual keys (`sk-omni-...`) validated by LiteLLM; hashed at rest; scoped to models + budgets.
- **Provider keys:** only in Secrets Manager, injected at task start; never logged; rotate on schedule.
- **Master key** (`LITELLM_MASTER_KEY`) restricted to admin/provisioning calls from the control plane only (private subnet, security-group locked).
- **Network:** RDS/Redis in private subnets, no public access; least-privilege IAM per ECS task role.
- **Data:** encrypt at rest (KMS) and in transit (TLS everywhere). Request/response body logging **off by default** (PII) — opt-in per org, stored encrypted in S3 with retention policy.
- **Abuse:** WAF, per-key rate limits, budget caps, anomaly alerts on spend spikes.

---

## 9. Observability

- **Metrics:** LiteLLM exposes Prometheus metrics → Amazon Managed Prometheus / CloudWatch. Track RPS, p50/p95/p99 latency (gateway vs upstream), error rate per provider, 429 rate, cooldown events, cost/min.
- **Logs:** structured JSON → CloudWatch Logs.
- **Tracing:** OpenTelemetry from FastAPI shim + LiteLLM callbacks → X-Ray/Tempo.
- **Alerting:** provider outage (fallback rate spike), budget breach, Redis/Postgres health, capacity-ledger nearing reserved limits.

---

## 10. Rollout Plan

| Phase | Scope |
|---|---|
| **0 — Spike** | LiteLLM Proxy on Fargate, 2–3 providers, master key only, manual config. Prove the unified API + failover. |
| **1 — MVP** | Virtual keys + budgets, Postgres/Redis, control-plane signup + key management, Stripe prepaid wallet, basic dashboard. |
| **2 — Analytics & scale** | Usage pipeline (Kinesis→S3/ClickHouse), real-time dashboards, autoscaling, read replica, Redis cluster. |
| **3 — Reserved capacity** | Capacity ledger, usage-based/cost-based routing, multi-region provider pools, SLA. |
| **4 — Enterprise** | Orgs/teams RBAC, per-org markup/pricing, invoicing, audit logs, SSO. |

---

## 11. Key Design Decisions & Trade-offs

1. **Build on LiteLLM vs. from scratch** — LiteLLM already solves the hard, boring 80% (provider normalization, routing, keys, spend). We focus on control plane + ops. Risk: coupling to LiteLLM's roadmap; mitigate by keeping the shim boundary clean.
2. **Proxy-direct vs. FastAPI shim** — direct proxy for speed to launch; shim only where custom billing/auth/capacity logic needs in-process control.
3. **ECS Fargate first, EKS later** — minimize ops until scale/cost justifies Kubernetes.
4. **ALB over API Gateway** for the hot path — cheaper and better for long-lived streaming responses; API Gateway reserved for edge features if needed.
5. **Shared Postgres, separate reads** — reuse LiteLLM's spend tables for billing via a read replica instead of a parallel tracking system.
6. **Markup as config** — default 0% to match MixRoute's positioning, but priced-in as a first-class knob for future plans.

---

## 12. Open Questions

- Reserved-capacity commercial model: how do we account for pre-purchased throughput per provider and reconcile with real usage?
- Billing mode: prepaid wallet (simpler, matches "no credit card binding") vs. postpaid invoicing for enterprise?
- Analytics store: Athena (cheap, batch) vs. ClickHouse (real-time, more ops) — decide by dashboard latency SLA.
- Multi-region active-active for the gateway, or single-region with provider-side geo distribution?

---

### References

- MixRoute — https://mixroute.ai/zh-hant/
- LiteLLM docs — https://docs.litellm.ai/docs/
- LiteLLM Proxy deploy — https://docs.litellm.ai/docs/proxy/deploy
- LiteLLM routing — https://docs.litellm.ai/docs/routing
- uv — https://docs.astral.sh/uv/
- FastAPI — https://fastapi.tiangolo.com/

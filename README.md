# OmniRoute

A multi-provider **LLM API gateway** built on [LiteLLM](https://docs.litellm.ai/) —
one OpenAI-compatible endpoint and key that routes across providers with
automatic failover, per-key budgets, and spend tracking.

- Design: [`doc/system-design.md`](doc/system-design.md)
- Plan (TDD): [`doc/implementation-plan.md`](doc/implementation-plan.md)

## What's implemented (Stages 0–4)

A FastAPI gateway shim with a clean, dependency-injected core. Every external
dependency (completions, event sink, rate limiter, key store) sits behind a small
seam, so tests use in-memory fakes — the suite is fast, deterministic, and needs
no network or provider keys.

### Storage

The key store, usage sink, and audit log each sit behind a Protocol seam, and
all three switch backend together based on `OMNIROUTE_DATABASE_URL`:

| Setting | Backend | Use |
|---|---|---|
| unset | in-memory | tests, quick local runs |
| `sqlite:///omniroute.db` | SQLite | **local dev** — a file, zero setup |
| `postgresql+psycopg://…` | Postgres | production |

SQLite and Postgres share one SQLAlchemy Core schema (`app/db.py`), so local dev
and prod differ only by the URL.

### Migrations (Alembic)

The schema is managed by Alembic (`migrations/`). It reads the same
`OMNIROUTE_DATABASE_URL`:

```bash
OMNIROUTE_DATABASE_URL=sqlite:///omniroute.db uv run alembic upgrade head
uv run alembic revision --autogenerate -m "describe change"   # after editing app/db.py
```

**Stage 0–1 — gateway + control plane**
- `POST /v1/chat/completions` — OpenAI-compatible; routes via LiteLLM's `Router`.
- Virtual-key auth (`sk-omni-...`), per-key **budgets** and **model allow-lists**.
- Per-key **spend tracking**.
- `POST /admin/keys`, `GET /admin/keys/{key}/spend` (master-key auth).

**Stage 2 — analytics & scale**
- Usage pipeline: every call emits a `UsageEvent` to an `EventSink`
  (`InMemorySink` / `FirehoseSink` → Kinesis → S3), idempotent on request id.
- `GET /admin/analytics/usage` — rollups by model and by key.
- `RateLimiter` seam (in-memory / shared-Redis) for correct counting across
  replicas; `load/locustfile.py` for the p95-overhead SLO.

**Stage 3 — reserved capacity & smart routing**
- `CapacityLedger` — committed vs. consumed per provider/region, ceiling guards,
  reconciliation (`app/capacity.py`).
- `select_deployment` — usage-based / cost-based selection that skips cooled-down
  deployments and honors tpm headroom (`app/routing.py`).
- Multi-region pool config: `gateway/config.multiregion.yaml`.

**Stage 4 — enterprise**
- `RBAC` — roles → permission matrix with `can` / `require` (`app/rbac.py`).
- Markup/pricing + invoicing — per-org markup (0% default), per-model invoice
  line items, golden-file-pinned rendering (`app/billing.py`).
- Append-only, hash-chained **audit log** (`app/audit.py`); privileged actions
  recorded; `GET /admin/audit` returns entries + chain verification.
- **SSO/OIDC** login mapping verified claims → org-scoped session (`app/sso.py`).

## Develop

```bash
uv sync                      # install deps into .venv, write uv.lock
uv run pytest                # run unit + contract tests
uv run pytest --cov          # with coverage
uv run ruff check .          # lint
```

## Run the shim locally

```bash
export OPENAI_API_KEY=sk-...            # used by LiteLLM's Router
export OMNIROUTE_MASTER_KEY=sk-omni-master-...
export OMNIROUTE_DATABASE_URL=sqlite:///omniroute.db   # optional; omit for in-memory
PYTHONPATH=control_plane uv run uvicorn app.main:app --reload

# issue a key, then call the gateway
curl -sX POST localhost:8000/admin/keys \
  -H "Authorization: Bearer $OMNIROUTE_MASTER_KEY" \
  -d '{"max_budget": 5.0, "models": ["gpt-4o"]}'

curl -sX POST localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer sk-omni-..." \
  -d '{"model":"gpt-4o","messages":[{"role":"user","content":"hi"}]}'
```

## Run the pure LiteLLM proxy (Stage 0 "buy" path)

See [`gateway/config.yaml`](gateway/config.yaml) — run the `ghcr.io/berriai/litellm`
image directly with that config.

## Layout

```
control_plane/app/   routes, auth, store, pricing, completer/sink/ratelimit seams,
                     analytics, capacity ledger, smart routing
control_plane/tests/ unit + contract tests
gateway/             LiteLLM proxy configs (single + multi-region)
load/                locust load test
doc/                 design + implementation-plan
```

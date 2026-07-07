# OmniRoute

A multi-provider **LLM API gateway** built on [LiteLLM](https://docs.litellm.ai/) —
one OpenAI-compatible endpoint and key that routes across providers with
automatic failover, per-key budgets, and spend tracking.

- Design: [`doc/system-design.md`](doc/system-design.md)
- Plan (TDD): [`doc/implementation-plan.md`](doc/implementation-plan.md)

## What's implemented (Stage 0 + Stage 1 start)

A FastAPI gateway shim with a clean, dependency-injected core:

- `POST /v1/chat/completions` — OpenAI-compatible; routes via LiteLLM's `Router`
  (multi-deployment, failover) on the production path.
- Virtual-key auth (`sk-omni-...`), per-key **budgets** and **model allow-lists**.
- Per-key **spend tracking** (recorded after each call).
- Control plane: `POST /admin/keys`, `GET /admin/keys/{key}/spend` (master-key auth).

The completion backend is a `Completer` seam, so tests use a fake — the suite is
fast, deterministic, and needs no network or provider keys.

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
control_plane/app/   FastAPI shim: routes, auth, store, pricing, completer seam
control_plane/tests/ unit + contract tests
gateway/config.yaml  LiteLLM proxy config (Docker path)
doc/                 design + implementation-plan
```

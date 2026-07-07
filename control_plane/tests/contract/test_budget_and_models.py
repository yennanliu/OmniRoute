"""Contract: budget caps and model allow-lists are enforced on the hot path."""


from tests.conftest import MASTER_KEY, auth


async def _issue_key(client, **body):
    r = await client.post("/admin/keys", headers=auth(MASTER_KEY), json=body)
    return r.json()["key"]


async def test_budget_exceeded_returns_429(client, store):
    key = await _issue_key(client, max_budget=0.00001)  # below one call's cost
    payload = {"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]}

    # First call succeeds and pushes spend past the cap.
    first = await client.post("/v1/chat/completions", headers=auth(key), json=payload)
    assert first.status_code == 200
    assert store.get(key).budget_exceeded

    # Second call is rejected.
    second = await client.post("/v1/chat/completions", headers=auth(key), json=payload)
    assert second.status_code == 429


async def test_model_not_in_allow_list_returns_403(client):
    key = await _issue_key(client, models=["gpt-4o"])
    r = await client.post(
        "/v1/chat/completions",
        headers=auth(key),
        json={"model": "claude-sonnet", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 403


async def test_allowed_model_passes(client):
    key = await _issue_key(client, models=["gpt-4o"])
    r = await client.post(
        "/v1/chat/completions",
        headers=auth(key),
        json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 200

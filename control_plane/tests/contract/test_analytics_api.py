"""Contract: usage events flow to analytics and roll up per model/key."""

from tests.conftest import MASTER_KEY, auth


async def _issue_key(client, **body):
    r = await client.post("/admin/keys", headers=auth(MASTER_KEY), json=body)
    return r.json()["key"]


async def _call(client, key, model="gpt-4o"):
    return await client.post(
        "/v1/chat/completions",
        headers=auth(key),
        json={"model": model, "messages": [{"role": "user", "content": "hi"}]},
    )


async def test_usage_rollup_reflects_calls(client):
    key_a = await _issue_key(client)
    key_b = await _issue_key(client)
    await _call(client, key_a)
    await _call(client, key_a)
    await _call(client, key_b)

    r = await client.get("/admin/analytics/usage", headers=auth(MASTER_KEY))
    assert r.status_code == 200
    body = r.json()
    assert body["totals"]["requests"] == 3
    assert body["by_model"]["gpt-4o"]["requests"] == 3
    assert body["by_key"][key_a]["requests"] == 2
    assert body["by_key"][key_b]["requests"] == 1
    assert body["totals"]["cost"] > 0


async def test_analytics_requires_master_key(client):
    r = await client.get("/admin/analytics/usage", headers=auth("nope"))
    assert r.status_code == 403

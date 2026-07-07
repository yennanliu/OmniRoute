"""Contract: control-plane key provisioning and spend read-back."""


from tests.conftest import MASTER_KEY, auth


async def test_create_key_requires_master_key(client):
    r = await client.post("/admin/keys", headers=auth("not-the-master"), json={})
    assert r.status_code == 403


async def test_create_key_returns_usable_key(client):
    r = await client.post(
        "/admin/keys", headers=auth(MASTER_KEY), json={"max_budget": 5.0, "models": ["gpt-4o"]}
    )
    assert r.status_code == 201
    body = r.json()
    assert body["key"].startswith("sk-omni-")
    assert body["max_budget"] == 5.0
    assert body["models"] == ["gpt-4o"]
    assert body["spend"] == 0.0


async def test_spend_endpoint_reflects_usage(client):
    key = (await client.post("/admin/keys", headers=auth(MASTER_KEY), json={})).json()["key"]
    await client.post(
        "/v1/chat/completions",
        headers=auth(key),
        json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]},
    )
    r = await client.get(f"/admin/keys/{key}/spend", headers=auth(MASTER_KEY))
    assert r.status_code == 200
    assert r.json()["spend"] > 0


async def test_spend_unknown_key_is_404(client):
    r = await client.get("/admin/keys/sk-omni-nope/spend", headers=auth(MASTER_KEY))
    assert r.status_code == 404

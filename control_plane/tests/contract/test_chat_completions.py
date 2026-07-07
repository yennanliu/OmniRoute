"""Contract: the OpenAI-compatible chat surface + spend attribution."""


from tests.conftest import MASTER_KEY, auth


async def _issue_key(client, **body):
    r = await client.post("/admin/keys", headers=auth(MASTER_KEY), json=body)
    assert r.status_code == 201
    return r.json()["key"]


async def test_chat_completion_proxies_and_records_spend(client, store):
    key = await _issue_key(client, max_budget=10.0)

    r = await client.post(
        "/v1/chat/completions",
        headers=auth(key),
        json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]},
    )

    assert r.status_code == 200
    assert r.json()["choices"][0]["message"]["content"] == "hi"
    # the behavior we're driving out: spend recorded for this key
    assert store.get(key).spend > 0


async def test_passthrough_params_reach_completer(client, completer):
    key = await _issue_key(client)
    await client.post(
        "/v1/chat/completions",
        headers=auth(key),
        json={
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "hi"}],
            "temperature": 0.2,
        },
    )
    assert completer.calls[-1]["temperature"] == 0.2


async def test_missing_key_is_401(client):
    r = await client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4o", "messages": []},
    )
    assert r.status_code == 401


async def test_invalid_key_is_401(client):
    r = await client.post(
        "/v1/chat/completions",
        headers=auth("sk-omni-does-not-exist"),
        json={"model": "gpt-4o", "messages": []},
    )
    assert r.status_code == 401

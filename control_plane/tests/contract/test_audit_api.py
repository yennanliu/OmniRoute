"""Contract: privileged actions are audited and the chain verifies."""

from tests.conftest import MASTER_KEY, auth


async def test_create_key_is_audited(client):
    r = await client.post("/admin/keys", headers=auth(MASTER_KEY), json={})
    created = r.json()["key"]

    audit = await client.get("/admin/audit", headers=auth(MASTER_KEY))
    assert audit.status_code == 200
    body = audit.json()
    assert body["verified"] is True
    assert body["entries"][-1] == {
        "seq": 0,
        "actor": "master",
        "action": "create_key",
        "target": created,
    }


async def test_audit_requires_master_key(client):
    r = await client.get("/admin/audit", headers=auth("nope"))
    assert r.status_code == 403

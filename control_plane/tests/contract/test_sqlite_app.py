"""End-to-end: a SQLite-backed app persists keys, usage, and audit across restarts."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.audit_sql import SqlAuditLog
from app.config import Settings
from app.db import make_engine
from app.main import create_app
from app.store_sql import SqlKeyStore
from app.usage_sql import SqlSink
from tests.conftest import MASTER_KEY, FakeCompleter, auth


def _build_app(db_url: str):
    engine = make_engine(db_url)
    return create_app(
        store=SqlKeyStore(engine),
        completer=FakeCompleter(),
        settings=Settings(master_key=MASTER_KEY, database_url=db_url),
        sink=SqlSink(engine),
        audit=SqlAuditLog(engine),
    )


async def _client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture
def db_url(tmp_path):
    return f"sqlite:///{tmp_path / 'omniroute.db'}"


async def test_full_flow_persists_across_restart(db_url):
    # First "process": issue a key, make two calls.
    async with await _client(_build_app(db_url)) as c:
        key = (await c.post("/admin/keys", headers=auth(MASTER_KEY), json={})).json()["key"]
        for _ in range(2):
            r = await c.post(
                "/v1/chat/completions",
                headers=auth(key),
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]},
            )
            assert r.status_code == 200

    # Second "process": a fresh app on the same DB still sees everything.
    async with await _client(_build_app(db_url)) as c:
        spend = await c.get(f"/admin/keys/{key}/spend", headers=auth(MASTER_KEY))
        assert spend.json()["spend"] > 0

        usage = await c.get("/admin/analytics/usage", headers=auth(MASTER_KEY))
        assert usage.json()["by_key"][key]["requests"] == 2

        audit = await c.get("/admin/audit", headers=auth(MASTER_KEY))
        assert audit.json()["verified"] is True
        assert audit.json()["entries"][0]["action"] == "create_key"

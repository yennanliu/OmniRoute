"""Shared fixtures.

The gateway is exercised through an in-process ASGI transport with a fake
completer, so tests are fast and deterministic — no network, no provider keys.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app
from app.store import InMemoryKeyStore
from app.usage import InMemorySink

MASTER_KEY = "sk-omni-master-test"


class FakeCompleter:
    """Records calls and returns a canned OpenAI-shaped response."""

    def __init__(self, content: str = "hi", prompt_tokens: int = 5, completion_tokens: int = 1):
        self._content = content
        self._prompt_tokens = prompt_tokens
        self._completion_tokens = completion_tokens
        self.calls: list[dict[str, Any]] = []

    async def acomplete(
        self, *, model: str, messages: list[dict[str, Any]], **kwargs: Any
    ) -> dict[str, Any]:
        self.calls.append({"model": model, "messages": messages, **kwargs})
        return {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": self._content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": self._prompt_tokens,
                "completion_tokens": self._completion_tokens,
                "total_tokens": self._prompt_tokens + self._completion_tokens,
            },
        }


@pytest.fixture
def store() -> InMemoryKeyStore:
    return InMemoryKeyStore()


@pytest.fixture
def completer() -> FakeCompleter:
    return FakeCompleter()


@pytest.fixture
def sink() -> InMemorySink:
    return InMemorySink()


@pytest.fixture
def app(store: InMemoryKeyStore, completer: FakeCompleter, sink: InMemorySink):
    return create_app(
        store=store, completer=completer, settings=Settings(master_key=MASTER_KEY), sink=sink
    )


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def auth(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}

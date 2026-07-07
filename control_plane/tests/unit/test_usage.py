from app.usage import InMemorySink, UsageEvent


def _event(request_id: str = "r1", **kw) -> UsageEvent:
    base = dict(key="sk-omni-a", model="gpt-4o", prompt_tokens=5, completion_tokens=1, cost=0.01)
    base.update(kw)
    return UsageEvent(request_id=request_id, **base)


def test_from_response_parses_usage():
    e = UsageEvent.from_response(
        request_id="r1",
        key="sk-omni-a",
        model="gpt-4o",
        cost=0.02,
        usage={"prompt_tokens": 10, "completion_tokens": 3},
    )
    assert (e.prompt_tokens, e.completion_tokens, e.cost) == (10, 3, 0.02)


def test_emit_is_idempotent_on_request_id():
    sink = InMemorySink()
    assert sink.emit(_event("r1")) is True
    assert sink.emit(_event("r1")) is False  # duplicate ignored
    assert sink.emit(_event("r2")) is True
    assert len(sink.all_events()) == 2

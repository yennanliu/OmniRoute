from app.analytics import rollup
from app.usage import UsageEvent


def _e(request_id, key, model, p, c, cost):
    return UsageEvent(
        request_id=request_id, key=key, model=model, prompt_tokens=p, completion_tokens=c, cost=cost
    )


def test_rollup_totals_and_breakdowns():
    events = [
        _e("1", "sk-a", "gpt-4o", 10, 2, 0.05),
        _e("2", "sk-a", "claude-sonnet", 20, 4, 0.03),
        _e("3", "sk-b", "gpt-4o", 5, 1, 0.01),
    ]
    r = rollup(events)

    assert r["totals"] == {
        "requests": 3,
        "prompt_tokens": 35,
        "completion_tokens": 7,
        "cost": 0.09,
    }
    assert r["by_model"]["gpt-4o"]["requests"] == 2
    assert r["by_model"]["gpt-4o"]["cost"] == 0.06
    assert r["by_key"]["sk-a"]["requests"] == 2
    assert r["by_key"]["sk-b"]["prompt_tokens"] == 5


def test_rollup_empty():
    r = rollup([])
    assert r["totals"]["requests"] == 0
    assert r["by_model"] == {}
    assert r["by_key"] == {}

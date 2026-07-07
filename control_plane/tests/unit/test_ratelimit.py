from app.ratelimit import InMemoryRateLimiter


def test_allows_up_to_limit_then_blocks():
    rl = InMemoryRateLimiter()
    assert [rl.allow("sk-a", limit_per_min=2, minute=100) for _ in range(3)] == [True, True, False]


def test_window_resets_next_minute():
    rl = InMemoryRateLimiter()
    assert rl.allow("sk-a", limit_per_min=1, minute=100) is True
    assert rl.allow("sk-a", limit_per_min=1, minute=100) is False
    assert rl.allow("sk-a", limit_per_min=1, minute=101) is True  # new window


def test_keys_are_independent():
    rl = InMemoryRateLimiter()
    assert rl.allow("sk-a", limit_per_min=1, minute=100) is True
    assert rl.allow("sk-b", limit_per_min=1, minute=100) is True


def test_non_positive_limit_means_unlimited():
    rl = InMemoryRateLimiter()
    assert all(rl.allow("sk-a", limit_per_min=0, minute=100) for _ in range(100))

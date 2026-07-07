from app.routing import Deployment, select_deployment


def _deployments():
    return [
        Deployment(
            "a", "gpt-4o", tpm_limit=1000, tpm_used=800, cost_per_1k=0.01, region="us-east-1"
        ),
        Deployment(
            "b", "gpt-4o", tpm_limit=1000, tpm_used=100, cost_per_1k=0.02, region="eu-west-1"
        ),
        Deployment("c", "gpt-4o", tpm_limit=1000, tpm_used=500, cost_per_1k=0.005, region="ap-1"),
    ]


def test_usage_based_picks_lowest_utilization():
    assert select_deployment(_deployments(), strategy="usage-based").id == "b"


def test_cost_based_picks_cheapest():
    assert select_deployment(_deployments(), strategy="cost-based").id == "c"


def test_skips_cooling_down_deployments():
    deps = _deployments()
    deps[1].cooling_down = True  # b is the usage-based winner, now unhealthy
    assert select_deployment(deps, strategy="usage-based").id == "c"


def test_honors_tpm_headroom_requirement():
    deps = _deployments()
    # need 300 tpm: 'a' has only 200 available and is excluded
    chosen = select_deployment(deps, strategy="cost-based", need_tpm=300)
    assert chosen.id == "c"  # cheapest among those with >=300 headroom


def test_returns_none_when_all_unavailable():
    deps = _deployments()
    for d in deps:
        d.cooling_down = True
    assert select_deployment(deps, strategy="usage-based") is None

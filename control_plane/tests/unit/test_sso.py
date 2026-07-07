import pytest

from app.rbac import Role
from app.sso import Session, SSOError, authorization_url, login


class FakeOIDC:
    def __init__(self, claims):
        self._claims = claims

    def exchange_code(self, code):
        assert code == "auth-code"
        return self._claims


DOMAINS = {"acme.com": "org_acme"}


def test_login_maps_domain_to_org():
    client = FakeOIDC({"email": "alice@acme.com"})
    session = login(client, "auth-code", domain_orgs=DOMAINS)
    assert session == Session("alice@acme.com", "org_acme", Role.MEMBER)


def test_login_honors_default_role():
    client = FakeOIDC({"email": "bob@acme.com"})
    session = login(client, "auth-code", domain_orgs=DOMAINS, default_role=Role.ADMIN)
    assert session.role is Role.ADMIN


def test_unprovisioned_domain_is_refused():
    client = FakeOIDC({"email": "eve@evil.com"})
    with pytest.raises(SSOError):
        login(client, "auth-code", domain_orgs=DOMAINS)


def test_missing_email_is_refused():
    with pytest.raises(SSOError):
        login(FakeOIDC({}), "auth-code", domain_orgs=DOMAINS)


def test_authorization_url_contains_params():
    url = authorization_url(
        authorize_endpoint="https://idp/authorize",
        client_id="cid",
        redirect_uri="https://app/cb",
        state="xyz",
    )
    assert url.startswith("https://idp/authorize?")
    assert "client_id=cid" in url and "state=xyz" in url and "response_type=code" in url

"""SSO / OIDC login (Stage 4).

`OIDCClient` is the seam to the identity provider; production wires a real
client, tests use a fake. `login` turns verified claims into a `Session` by
mapping the email domain to an org and role — so the flow is testable without a
live IdP.
"""

from __future__ import annotations

from typing import Any, Protocol
from urllib.parse import urlencode

from .rbac import Role


class OIDCClient(Protocol):
    def exchange_code(self, code: str) -> dict[str, Any]:
        """Exchange an auth code for verified claims (must include 'email')."""
        ...


class SSOError(Exception):
    """Raised when login is refused (unknown domain, missing claims)."""


class Session:
    def __init__(self, email: str, org_id: str, role: Role) -> None:
        self.email = email
        self.org_id = org_id
        self.role = role

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Session) and (self.email, self.org_id, self.role) == (
            other.email,
            other.org_id,
            other.role,
        )

    def __repr__(self) -> str:
        return f"Session(email={self.email!r}, org_id={self.org_id!r}, role={self.role})"


def authorization_url(
    *, authorize_endpoint: str, client_id: str, redirect_uri: str, state: str
) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email",
        "state": state,
    }
    return f"{authorize_endpoint}?{urlencode(params)}"


def login(
    client: OIDCClient,
    code: str,
    *,
    domain_orgs: dict[str, str],
    default_role: Role = Role.MEMBER,
) -> Session:
    """Complete the OIDC flow and map the user to an org-scoped session."""
    claims = client.exchange_code(code)
    email = claims.get("email")
    if not email or "@" not in email:
        raise SSOError("missing or invalid email claim")

    domain = email.rsplit("@", 1)[1].lower()
    org_id = domain_orgs.get(domain)
    if org_id is None:
        raise SSOError(f"domain '{domain}' is not provisioned")

    return Session(email=email, org_id=org_id, role=default_role)

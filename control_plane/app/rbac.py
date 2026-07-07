"""Role-based access control (Stage 4).

A small, pure policy: roles map to permission sets, and `can` / `require`
answer authorization questions. Wiring (turning a session into a role) lives in
`sso.py`; this module has no I/O so the allow/deny matrix is trivially testable.
"""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class Permission(StrEnum):
    MANAGE_ORG = "manage_org"  # billing settings, members, SSO
    MANAGE_KEYS = "manage_keys"  # create/rotate virtual keys
    VIEW_ANALYTICS = "view_analytics"
    VIEW_BILLING = "view_billing"
    USE_GATEWAY = "use_gateway"


_ALL = frozenset(Permission)

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.OWNER: _ALL,
    Role.ADMIN: _ALL - {Permission.MANAGE_ORG},
    Role.MEMBER: frozenset({Permission.USE_GATEWAY, Permission.VIEW_ANALYTICS}),
    Role.VIEWER: frozenset({Permission.VIEW_ANALYTICS, Permission.VIEW_BILLING}),
}


class AuthorizationError(Exception):
    """Raised when a role lacks a required permission."""


def can(role: Role, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS[role]


def require(role: Role, permission: Permission) -> None:
    if not can(role, permission):
        raise AuthorizationError(f"role '{role.value}' lacks permission '{permission.value}'")

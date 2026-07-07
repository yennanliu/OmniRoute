import pytest

from app.rbac import AuthorizationError, Permission, Role, can, require


def test_owner_has_everything():
    assert all(can(Role.OWNER, p) for p in Permission)


def test_admin_cannot_manage_org_but_can_manage_keys():
    assert not can(Role.ADMIN, Permission.MANAGE_ORG)
    assert can(Role.ADMIN, Permission.MANAGE_KEYS)


def test_member_can_use_gateway_not_manage_keys():
    assert can(Role.MEMBER, Permission.USE_GATEWAY)
    assert not can(Role.MEMBER, Permission.MANAGE_KEYS)


def test_viewer_is_read_only():
    assert can(Role.VIEWER, Permission.VIEW_ANALYTICS)
    assert not can(Role.VIEWER, Permission.USE_GATEWAY)


def test_require_raises_on_denied():
    require(Role.OWNER, Permission.MANAGE_ORG)  # no raise
    with pytest.raises(AuthorizationError):
        require(Role.VIEWER, Permission.MANAGE_KEYS)

"""Unit tests for Story 3 — enforce permissions (``requires_auth`` / ``requires_role``).

The decorators are exercised directly: a dummy function is wrapped and called
inside a ``test_request_context`` carrying (or lacking) an ``Authorization``
header. No HTTP client is involved.

# TODO: replace marker/story name with the actual Jira story ID once assigned
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Callable

import pytest
from flask import Flask, g

from app.common.decorators import ROLE_CLAIM, requires_auth, requires_role
from app.common.errors import AuthenticationError, AuthorizationError
from app.modules.auth.permissions import (
    ALL_ROLES,
    EXTERNAL_ROLES,
    INTERNAL_ROLES,
    Role,
    is_external_role,
    is_internal_role,
)

pytestmark = pytest.mark.story_permissions

# A real route path so ``request.endpoint`` resolves during URL matching
# (needed to assert on the audit log line).
PROTECTED_PATH = "/api/auth/internal-only"


def _call_protected(
    app: Flask, func: Callable[..., Any], token: str | None, path: str = PROTECTED_PATH
) -> Any:
    """Invoke ``func`` inside a request context with an optional bearer token."""
    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    with app.test_request_context(path, headers=headers):
        return func()


def _protected_view() -> str:
    return "ok"


# --------------------------------------------------------------------------
# requires_auth
# --------------------------------------------------------------------------


def test_requires_auth_passes_through_with_valid_token(app: Flask, make_user, token_for) -> None:
    user = make_user(role=Role.ATTENDEE, user_id=7)
    wrapped = requires_auth(_protected_view)

    with app.test_request_context(PROTECTED_PATH, headers={"Authorization": f"Bearer {token_for(user)}"}):
        assert wrapped() == "ok"
        # Identity + role exposed to the route body.
        assert g.current_user_id == "7"
        assert g.current_user_role == "attendee"


def test_requires_auth_missing_token_is_401(app: Flask) -> None:
    wrapped = requires_auth(_protected_view)

    with pytest.raises(AuthenticationError) as exc_info:
        _call_protected(app, wrapped, token=None)

    assert exc_info.value.status_code == 401
    assert exc_info.value.error_code == "authentication_error"


def test_requires_auth_malformed_token_is_401(app: Flask) -> None:
    wrapped = requires_auth(_protected_view)

    with pytest.raises(AuthenticationError) as exc_info:
        _call_protected(app, wrapped, token="this.is.garbage")

    assert exc_info.value.status_code == 401


def test_requires_auth_expired_token_is_401(app: Flask, token_for) -> None:
    wrapped = requires_auth(_protected_view)
    expired = token_for(role=Role.ATTENDEE, expires_delta=timedelta(seconds=-1))

    with pytest.raises(AuthenticationError) as exc_info:
        _call_protected(app, wrapped, token=expired)

    assert exc_info.value.status_code == 401


def test_requires_auth_tampered_signature_is_401(app: Flask, token_for) -> None:
    wrapped = requires_auth(_protected_view)
    header, payload, signature = token_for(role=Role.ATTENDEE).split(".")
    tampered_sig = ("A" if signature[0] != "A" else "B") + signature[1:]

    with pytest.raises(AuthenticationError) as exc_info:
        _call_protected(app, wrapped, token=f"{header}.{payload}.{tampered_sig}")

    assert exc_info.value.status_code == 401


def test_requires_auth_wrong_scheme_is_401(app: Flask, token_for) -> None:
    wrapped = requires_auth(_protected_view)

    with pytest.raises(AuthenticationError):
        with app.test_request_context(PROTECTED_PATH, headers={"Authorization": f"Basic {token_for(role=Role.ATTENDEE)}"}):
            wrapped()


# --------------------------------------------------------------------------
# requires_role
# --------------------------------------------------------------------------


@pytest.mark.parametrize("role", sorted(INTERNAL_ROLES, key=lambda r: r.value))
def test_requires_role_allows_each_permitted_role(app: Flask, token_for, role: Role) -> None:
    wrapped = requires_role(*INTERNAL_ROLES)(_protected_view)

    assert _call_protected(app, wrapped, token=token_for(role=role)) == "ok"


@pytest.mark.parametrize("role", sorted(EXTERNAL_ROLES, key=lambda r: r.value))
def test_requires_role_rejects_wrong_role_with_403(app: Flask, token_for, role: Role) -> None:
    wrapped = requires_role(*INTERNAL_ROLES)(_protected_view)

    with pytest.raises(AuthorizationError) as exc_info:
        _call_protected(app, wrapped, token=token_for(role=role))

    assert exc_info.value.status_code == 403
    assert exc_info.value.error_code == "authorization_error"


def test_requires_role_single_role_boundary(app: Flask, token_for) -> None:
    """Exactly one allowed role: that role passes, its nearest neighbour does not."""
    wrapped = requires_role(Role.VENUE_STAFF)(_protected_view)

    assert _call_protected(app, wrapped, token=token_for(role=Role.VENUE_STAFF)) == "ok"
    with pytest.raises(AuthorizationError):
        _call_protected(app, wrapped, token=token_for(role=Role.EVENT_COORDINATOR))


def test_requires_role_accepts_strings_and_enums_interchangeably(app: Flask, token_for) -> None:
    by_string = requires_role("venue_staff")(_protected_view)
    by_enum = requires_role(Role.VENUE_STAFF)(_protected_view)

    token = token_for(role=Role.VENUE_STAFF)
    assert _call_protected(app, by_string, token=token) == "ok"
    assert _call_protected(app, by_enum, token=token) == "ok"
    assert by_string.allowed_roles == by_enum.allowed_roles == frozenset({"venue_staff"})


def test_requires_role_missing_token_is_401_not_403(app: Flask) -> None:
    """Authentication is checked before authorization."""
    wrapped = requires_role(*INTERNAL_ROLES)(_protected_view)

    with pytest.raises(AuthenticationError) as exc_info:
        _call_protected(app, wrapped, token=None)

    assert exc_info.value.status_code == 401


def test_requires_role_token_without_role_claim_is_403(app: Flask) -> None:
    """A valid token with no role claim must never be treated as any role."""
    from flask_jwt_extended import create_access_token

    wrapped = requires_role(*ALL_ROLES)(_protected_view)
    token = create_access_token(identity="1")  # no ROLE_CLAIM

    with pytest.raises(AuthorizationError) as exc_info:
        _call_protected(app, wrapped, token=token)

    assert exc_info.value.status_code == 403


def test_requires_role_with_unknown_role_value_is_403(app: Flask) -> None:
    from flask_jwt_extended import create_access_token

    wrapped = requires_role(*ALL_ROLES)(_protected_view)
    token = create_access_token(identity="1", additional_claims={ROLE_CLAIM: "superuser"})

    with pytest.raises(AuthorizationError):
        _call_protected(app, wrapped, token=token)


def test_requires_role_with_no_roles_is_a_programming_error() -> None:
    with pytest.raises(ValueError):
        requires_role()


def test_decorators_preserve_function_metadata() -> None:
    """``functools.wraps`` keeps Flask endpoint names stable."""

    def my_view() -> None:
        """Docstring."""

    assert requires_auth(my_view).__name__ == "my_view"
    assert requires_role(Role.ATTENDEE)(my_view).__name__ == "my_view"
    assert requires_role(Role.ATTENDEE)(my_view).__doc__ == "Docstring."


# --------------------------------------------------------------------------
# Consistent error shape + audit logging
# --------------------------------------------------------------------------


def test_401_and_403_share_the_same_error_shape() -> None:
    unauth = AuthenticationError("Missing, invalid or expired token.").to_dict()
    forbidden = AuthorizationError("You do not have permission to perform this action.").to_dict()

    assert set(unauth) == set(forbidden) == {"error", "message"}
    assert unauth["error"] == "authentication_error"
    assert forbidden["error"] == "authorization_error"


def test_forbidden_attempt_is_logged_with_role_endpoint_and_timestamp(
    app: Flask, token_for, caplog: pytest.LogCaptureFixture
) -> None:
    wrapped = requires_role(*INTERNAL_ROLES)(_protected_view)

    with caplog.at_level(logging.WARNING, logger="connectsphere.authz"):
        with pytest.raises(AuthorizationError):
            _call_protected(app, wrapped, token=token_for(role=Role.ATTENDEE))

    records = [r for r in caplog.records if r.name == "connectsphere.authz"]
    assert len(records) == 1
    line = records[0].getMessage()
    assert "reason=forbidden_role" in line
    assert "role=attendee" in line
    assert "endpoint=auth.internal_only" in line
    assert f"path={PROTECTED_PATH}" in line
    assert "timestamp=" in line and "T" in line.split("timestamp=")[1]  # ISO-8601


def test_invalid_token_attempt_is_logged(app: Flask, caplog: pytest.LogCaptureFixture) -> None:
    wrapped = requires_auth(_protected_view)

    with caplog.at_level(logging.WARNING, logger="connectsphere.authz"):
        with pytest.raises(AuthenticationError):
            _call_protected(app, wrapped, token=None)

    line = next(r.getMessage() for r in caplog.records if r.name == "connectsphere.authz")
    assert "reason=invalid_token" in line
    assert "role=None" in line
    assert f"path={PROTECTED_PATH}" in line


def test_successful_call_is_not_logged_as_failure(
    app: Flask, token_for, caplog: pytest.LogCaptureFixture
) -> None:
    wrapped = requires_role(*INTERNAL_ROLES)(_protected_view)

    with caplog.at_level(logging.WARNING, logger="connectsphere.authz"):
        _call_protected(app, wrapped, token=token_for(role=Role.VENUE_STAFF))

    assert not [r for r in caplog.records if r.name == "connectsphere.authz"]


# --------------------------------------------------------------------------
# Policy vocabulary (permissions.py)
# --------------------------------------------------------------------------


def test_role_groups_partition_all_roles() -> None:
    assert INTERNAL_ROLES | EXTERNAL_ROLES == ALL_ROLES
    assert not (INTERNAL_ROLES & EXTERNAL_ROLES)
    assert ALL_ROLES == frozenset(Role)
    assert len(Role) == 5


@pytest.mark.parametrize(
    ("role", "internal"),
    [
        (Role.EVENT_COORDINATOR, True),
        (Role.VENUE_STAFF, True),
        (Role.TECHNICAL_SUPPORT_STAFF, True),
        (Role.EVENT_ORGANISER, False),
        (Role.ATTENDEE, False),
        ("venue_staff", True),
        ("attendee", False),
        ("superuser", False),
    ],
)
def test_is_internal_and_is_external_role(role: Role | str, internal: bool) -> None:
    assert is_internal_role(role) is internal
    known = role in Role.values() if isinstance(role, str) else True
    assert is_external_role(role) is (known and not internal)


def test_role_from_value_rejects_unknown() -> None:
    assert Role.from_value("attendee") is Role.ATTENDEE
    with pytest.raises(ValueError):
        Role.from_value("superuser")


# --------------------------------------------------------------------------
# Support for GET /api/auth/me — resolving the token identity to a user
# --------------------------------------------------------------------------


def test_get_user_by_id_returns_user(mock_session, make_user) -> None:
    from app.modules.auth.services import get_user_by_id

    user = make_user(user_id=7)
    mock_session.get.return_value = user

    assert get_user_by_id("7", session=mock_session) is user
    mock_session.get.assert_called_once()
    assert mock_session.get.call_args.args[1] == 7  # identity claim string → int PK


def test_get_user_by_id_unknown_raises_not_found(mock_session) -> None:
    from app.common.errors import NotFoundError
    from app.modules.auth.services import get_user_by_id

    mock_session.get.return_value = None

    with pytest.raises(NotFoundError) as exc_info:
        get_user_by_id(999, session=mock_session)

    assert exc_info.value.status_code == 404

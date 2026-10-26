"""Unit tests for SCRUM-89 — log out, so the access token stops working (SCRUM-6 AC4).

Logging out keeps the token's ``jti`` in a blocklist until the token expires, and every
protected route then refuses it with the same ``401`` as an expired token (ADR-0110).
Only the token sent with the logout stops working: the user's other sessions, and other
users', carry on. Each logout also deletes the blocklist rows of tokens that have
expired since, and writes one line to the ``connectsphere.authz`` log.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest
from flask import Flask, g
from flask_jwt_extended import decode_token
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.common.decorators import optional_auth
from app.common.errors import INVALID_TOKEN_MESSAGE, AuthenticationError
from app.extensions import db
from app.modules.auth import routes as auth_routes
from app.modules.auth.models import RevokedToken, User
from app.modules.auth.permissions import Role
from app.modules.auth.services import is_token_revoked, revoke_access_token

pytestmark = pytest.mark.scrum_89

CallRoute = Callable[..., Any]
TokenFor = Callable[..., str]

LOGOUT = ("auth.logout", "POST", "/api/auth/logout", {})
PROFILE = ("auth.me", "GET", "/api/auth/me", {})
STAFF_ONLY = ("auth.internal_only", "GET", "/api/auth/internal-only", {})

#: The Event Organiser and an Event Coordinator saved by ``saved_users``.
ORGANISER_ID = 7
COORDINATOR_ID = 3


def _user(saved_users: list[User], user_id: int) -> User:
    for user in saved_users:
        if user.id == user_id:
            return user
    raise AssertionError(f"saved_users has no user {user_id}")


def _blocklist_row(jti: str) -> RevokedToken | None:
    """The blocklist row for ``jti``, read in a fresh session so it shows the commit."""
    db.session.remove()
    return db.session.scalar(select(RevokedToken).where(RevokedToken.jti == jti))


def _saved_jtis() -> list[str]:
    db.session.remove()
    return sorted(db.session.scalars(select(RevokedToken.jti)))


def _block(save: Callable[..., None], jti: str, expires_at: datetime) -> None:
    save(RevokedToken(jti=jti, user_id=ORGANISER_ID, expires_at=expires_at))


def _log_out(token: str) -> None:
    """Revoke ``token`` as ``POST /api/auth/logout`` would."""
    revoke_access_token(decode_token(token))


@optional_auth
def _who_is_asking() -> tuple[Any, Any]:
    return g.current_user_id, g.current_user_role


# --------------------------------------------------------------------------
# The service: the token's jti is kept until the token expires
# --------------------------------------------------------------------------


def test_logging_out_keeps_the_tokens_jti_user_and_expiry(
    saved_users: list[User], token_for: TokenFor
) -> None:
    token = token_for(_user(saved_users, ORGANISER_ID))
    claims = decode_token(token)

    revoke_access_token(claims)
    row = _blocklist_row(claims["jti"])

    assert row is not None
    assert row.user_id == ORGANISER_ID
    assert row.expires_at == datetime.fromtimestamp(claims["exp"], tz=timezone.utc)


def test_only_the_logged_out_token_is_revoked(saved_users: list[User], token_for: TokenFor) -> None:
    organiser = _user(saved_users, ORGANISER_ID)
    logged_out = token_for(organiser)
    still_signed_in = token_for(organiser)

    _log_out(logged_out)

    assert is_token_revoked(decode_token(logged_out)["jti"]) is True
    assert is_token_revoked(decode_token(still_signed_in)["jti"]) is False


def test_logging_out_deletes_the_rows_of_tokens_expired_by_now_and_keeps_the_rest(
    saved_users: list[User], save: Callable[..., None], token_for: TokenFor, now: datetime
) -> None:
    _block(save, "expired-a-second-ago", now - timedelta(seconds=1))
    _block(save, "expires-right-now", now)
    _block(save, "expires-in-a-second", now + timedelta(seconds=1))
    claims = decode_token(token_for(_user(saved_users, ORGANISER_ID)))

    revoke_access_token(claims, now=now)

    assert _saved_jtis() == sorted(["expires-in-a-second", claims["jti"]])


def test_logging_out_writes_one_line_to_the_authz_log(
    saved_users: list[User], token_for: TokenFor, caplog: pytest.LogCaptureFixture
) -> None:
    claims = decode_token(token_for(_user(saved_users, ORGANISER_ID)))

    with caplog.at_level(logging.INFO, logger="connectsphere.authz"):
        revoke_access_token(claims)

    assert [(record.name, record.levelname, record.getMessage()) for record in caplog.records] == [
        (
            "connectsphere.authz",
            "INFO",
            f"logout user_id=7 jti={claims['jti']}",
        )
    ]


def test_a_logout_racing_another_with_the_same_token_rolls_back_quietly(
    mock_session: MagicMock, token_for: TokenFor, caplog: pytest.LogCaptureFixture
) -> None:
    mock_session.commit.side_effect = IntegrityError("INSERT", {}, Exception("duplicate jti"))
    claims = decode_token(token_for(role=Role.ATTENDEE))

    with caplog.at_level(logging.INFO, logger="connectsphere.authz"):
        revoke_access_token(claims, session=mock_session)

    mock_session.rollback.assert_called_once()
    assert caplog.records == []


# --------------------------------------------------------------------------
# The route: POST /api/auth/logout
# --------------------------------------------------------------------------


@pytest.mark.parametrize("role", list(Role), ids=lambda role: role.value)
def test_every_role_can_log_out_and_gets_204_with_no_body(
    role: Role,
    call_route: CallRoute,
    replace_services: Callable[..., dict[str, MagicMock]],
    token_for: TokenFor,
) -> None:
    mocks = replace_services(auth_routes, {"revoke_access_token": None})
    token = token_for(role=role)

    response, status = call_route(*LOGOUT, token)

    assert (status, response.get_data(as_text=True)) == (204, "")
    [call] = mocks["revoke_access_token"].call_args_list
    assert call.args[0]["jti"] == decode_token(token)["jti"]


def test_logging_out_without_a_token_is_401_and_revokes_nothing(
    call_route: CallRoute, replace_services: Callable[..., dict[str, MagicMock]]
) -> None:
    mocks = replace_services(auth_routes, {"revoke_access_token": None})

    with pytest.raises(AuthenticationError) as refused:
        call_route(*LOGOUT, None)

    assert refused.value.status_code == 401
    assert refused.value.message == INVALID_TOKEN_MESSAGE
    mocks["revoke_access_token"].assert_not_called()


# --------------------------------------------------------------------------
# After logging out, the token is refused like an expired one
# --------------------------------------------------------------------------


def test_a_revoked_token_gets_the_same_401_as_an_expired_one(
    saved_users: list[User], call_route: CallRoute, token_for: TokenFor
) -> None:
    organiser = _user(saved_users, ORGANISER_ID)
    revoked = token_for(organiser)
    expired = token_for(organiser, expires_delta=timedelta(seconds=-1))
    _log_out(revoked)

    with pytest.raises(AuthenticationError) as revoked_refusal:
        call_route(*PROFILE, revoked)
    with pytest.raises(AuthenticationError) as expired_refusal:
        call_route(*PROFILE, expired)

    assert revoked_refusal.value.status_code == 401
    assert revoked_refusal.value.message == INVALID_TOKEN_MESSAGE
    assert revoked_refusal.value.to_dict() == expired_refusal.value.to_dict()


def test_a_revoked_staff_token_is_401_on_a_role_route_not_403(
    saved_users: list[User], call_route: CallRoute, token_for: TokenFor
) -> None:
    revoked = token_for(_user(saved_users, COORDINATOR_ID))
    _log_out(revoked)

    with pytest.raises(AuthenticationError) as refused:
        call_route(*STAFF_ONLY, revoked)

    assert refused.value.status_code == 401
    assert refused.value.message == INVALID_TOKEN_MESSAGE


def test_using_a_revoked_token_is_logged_as_an_authz_failure(
    saved_users: list[User],
    call_route: CallRoute,
    token_for: TokenFor,
    caplog: pytest.LogCaptureFixture,
) -> None:
    revoked = token_for(_user(saved_users, ORGANISER_ID))
    _log_out(revoked)
    caplog.clear()  # the logout's own line; only the refusal below is checked

    with caplog.at_level(logging.WARNING, logger="connectsphere.authz"):
        with pytest.raises(AuthenticationError):
            call_route(*PROFILE, revoked)

    [record] = caplog.records
    assert "authz_failure reason=invalid_token" in record.getMessage()
    assert record.getMessage().endswith("detail=Token has been revoked")


def test_a_revoked_token_on_a_public_page_is_read_as_a_visitor(
    app: Flask, saved_users: list[User], token_for: TokenFor
) -> None:
    revoked = token_for(_user(saved_users, ORGANISER_ID))
    _log_out(revoked)

    with app.test_request_context("/", headers={"Authorization": f"Bearer {revoked}"}):
        assert _who_is_asking() == (None, None)


def test_the_users_other_token_and_other_users_tokens_still_work(
    saved_users: list[User], call_route: CallRoute, token_for: TokenFor
) -> None:
    organiser = _user(saved_users, ORGANISER_ID)
    logged_out = token_for(organiser)
    other_device = token_for(organiser)
    other_user = token_for(_user(saved_users, COORDINATOR_ID))
    _log_out(logged_out)

    _response, other_device_status = call_route(*PROFILE, other_device)
    _response, other_user_status = call_route(*PROFILE, other_user)

    assert (other_device_status, other_user_status) == (200, 200)

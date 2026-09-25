"""Unit tests for SCRUM-6 — log in (``authenticate_user``)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from flask import Flask
from flask_jwt_extended import decode_token

from app.common.decorators import ROLE_CLAIM
from app.common.errors import AuthenticationError
from app.modules.auth.permissions import Role
from app.modules.auth.services import (
    INVALID_CREDENTIALS_MESSAGE,
    AuthResult,
    authenticate_user,
    normalise_email,
)

pytestmark = pytest.mark.scrum_6


# --------------------------------------------------------------------------
# Happy path
# --------------------------------------------------------------------------


def test_correct_credentials_return_token_and_user(mock_session: MagicMock, make_user) -> None:
    user = make_user(email="alice@example.com", password="Password123", role=Role.VENUE_STAFF)
    mock_session.scalar.return_value = user

    result = authenticate_user("alice@example.com", "Password123", session=mock_session)

    assert isinstance(result, AuthResult)
    assert result.user is user
    assert isinstance(result.access_token, str) and result.access_token.count(".") == 2


def test_token_payload_contains_role_claim(mock_session: MagicMock, make_user) -> None:
    user = make_user(role=Role.EVENT_COORDINATOR)
    mock_session.scalar.return_value = user

    result = authenticate_user(user.email, "Password123", session=mock_session)
    claims = decode_token(result.access_token)

    assert claims[ROLE_CLAIM] == "event_coordinator"


def test_token_identity_is_the_user_id(mock_session: MagicMock, make_user) -> None:
    user = make_user(user_id=42)
    mock_session.scalar.return_value = user

    result = authenticate_user(user.email, "Password123", session=mock_session)
    claims = decode_token(result.access_token)

    assert claims["sub"] == "42"


def test_token_expiry_matches_configuration(app: Flask, mock_session: MagicMock, make_user) -> None:
    user = make_user()
    mock_session.scalar.return_value = user

    result = authenticate_user(user.email, "Password123", session=mock_session)
    claims = decode_token(result.access_token)

    expected = int(app.config["JWT_ACCESS_TOKEN_EXPIRES"].total_seconds())
    assert claims["exp"] - claims["iat"] == expected
    assert expected > 0  # a defined, finite expiry


def test_login_email_is_case_insensitive(mock_session: MagicMock, make_user) -> None:
    user = make_user(email="alice@example.com")
    mock_session.scalar.return_value = user

    authenticate_user("  ALICE@Example.COM ", "Password123", session=mock_session)

    stmt = mock_session.scalar.call_args.args[0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "alice@example.com" in compiled


def test_normalise_email_trims_and_lowercases() -> None:
    assert normalise_email("  Bob@Example.COM ") == "bob@example.com"


# --------------------------------------------------------------------------
# Failure: wrong password / unknown email — identical, generic error
# --------------------------------------------------------------------------


def test_wrong_password_fails_with_generic_message(mock_session: MagicMock, make_user) -> None:
    mock_session.scalar.return_value = make_user(password="Password123")

    with pytest.raises(AuthenticationError) as exc_info:
        authenticate_user("alice@example.com", "WrongPass99", session=mock_session)

    assert exc_info.value.status_code == 401
    assert exc_info.value.message == INVALID_CREDENTIALS_MESSAGE


def test_unknown_email_fails_with_generic_message(mock_session: MagicMock) -> None:
    mock_session.scalar.return_value = None  # no such user

    with pytest.raises(AuthenticationError) as exc_info:
        authenticate_user("ghost@example.com", "Password123", session=mock_session)

    assert exc_info.value.status_code == 401
    assert exc_info.value.message == INVALID_CREDENTIALS_MESSAGE


def test_unknown_email_and_wrong_password_produce_identical_errors(
    mock_session: MagicMock, make_user
) -> None:
    """No user enumeration: the two failure modes must be indistinguishable."""
    mock_session.scalar.return_value = None
    with pytest.raises(AuthenticationError) as unknown_email:
        authenticate_user("ghost@example.com", "Password123", session=mock_session)

    mock_session.scalar.return_value = make_user(password="Password123")
    with pytest.raises(AuthenticationError) as wrong_password:
        authenticate_user("alice@example.com", "Nope12345", session=mock_session)

    assert unknown_email.value.to_dict() == wrong_password.value.to_dict()
    assert unknown_email.value.status_code == wrong_password.value.status_code


# --------------------------------------------------------------------------
# Boundary: empty / missing inputs
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("email", "password"), [("", "Password123"), ("alice@example.com", ""), ("", "")]
)
def test_empty_credentials_fail_generically(
    email: str, password: str, mock_session: MagicMock, make_user
) -> None:
    mock_session.scalar.return_value = make_user(password="Password123") if email else None

    with pytest.raises(AuthenticationError) as exc_info:
        authenticate_user(email, password, session=mock_session)

    assert exc_info.value.message == INVALID_CREDENTIALS_MESSAGE


def test_user_with_no_password_hash_cannot_log_in(mock_session: MagicMock, make_user) -> None:
    """Defensive: a corrupt row with an empty hash must never authenticate."""
    user = make_user()
    user.password_hash = ""
    mock_session.scalar.return_value = user

    with pytest.raises(AuthenticationError):
        authenticate_user(user.email, "", session=mock_session)

"""Unit tests for SCRUM-65 — create an account (``register_user``)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash

from app.common.errors import ConflictError, ValidationError
from app.modules.auth.models import User
from app.modules.auth.permissions import Role
from app.modules.auth.schemas import UserSchema
from app.modules.auth.services import register_user

pytestmark = pytest.mark.scrum_65


# --------------------------------------------------------------------------
# Happy path
# --------------------------------------------------------------------------


def test_valid_input_creates_user_with_hashed_password(
    mock_session: MagicMock, valid_registration_payload: dict[str, Any]
) -> None:
    user = register_user(valid_registration_payload, session=mock_session)

    assert isinstance(user, User)
    assert user.email == "new.user@example.com"  # normalised
    assert user.full_name == "New User"
    assert user.role is Role.EVENT_ORGANISER
    assert user.organisation == "Acme Events"

    # Hashed, not plaintext, and verifiable.
    assert user.password_hash != valid_registration_payload["password"]
    assert user.password_hash.startswith("scrypt:")
    assert check_password_hash(user.password_hash, valid_registration_payload["password"])

    mock_session.add.assert_called_once_with(user)
    mock_session.commit.assert_called_once()
    mock_session.rollback.assert_not_called()


def test_plaintext_password_is_not_retained_anywhere(
    mock_session: MagicMock, valid_registration_payload: dict[str, Any]
) -> None:
    plaintext = valid_registration_payload["password"]
    user = register_user(valid_registration_payload, session=mock_session)

    # Not on the object, not in its dict form, not in the API serialisation.
    assert plaintext not in [str(v) for v in vars(user).values()]
    assert not hasattr(user, "password")
    assert "password" not in user.to_dict()
    assert "password_hash" not in user.to_dict()
    dumped = UserSchema().dump(user)
    assert "password" not in dumped
    assert "password_hash" not in dumped
    assert plaintext not in str(dumped)


def test_organisation_is_optional(
    mock_session: MagicMock, valid_registration_payload: dict[str, Any]
) -> None:
    valid_registration_payload.pop("organisation")
    user = register_user(valid_registration_payload, session=mock_session)
    assert user.organisation is None


def test_blank_organisation_is_stored_as_null(
    mock_session: MagicMock, valid_registration_payload: dict[str, Any]
) -> None:
    valid_registration_payload["organisation"] = ""
    user = register_user(valid_registration_payload, session=mock_session)
    assert user.organisation is None


@pytest.mark.parametrize("role", Role.values())
def test_every_role_can_register(
    role: str, mock_session: MagicMock, valid_registration_payload: dict[str, Any]
) -> None:
    valid_registration_payload["role"] = role
    user = register_user(valid_registration_payload, session=mock_session)
    assert user.role.value == role


# --------------------------------------------------------------------------
# Boundary: password policy (8+ chars, at least one letter and one digit)
# --------------------------------------------------------------------------


def test_password_exactly_min_length_is_accepted(
    mock_session: MagicMock, valid_registration_payload: dict[str, Any]
) -> None:
    valid_registration_payload["password"] = "abcdefg1"  # 8 chars
    user = register_user(valid_registration_payload, session=mock_session)
    assert user.check_password("abcdefg1")


@pytest.mark.parametrize(
    ("password", "expected_fragment"),
    [
        ("abcdef1", "at least 8 characters"),  # 7 chars — one below the boundary
        ("", "at least 8 characters"),
        ("12345678", "at least one letter"),
        ("abcdefgh", "at least one digit"),
    ],
)
def test_weak_password_is_rejected_with_specific_message(
    password: str,
    expected_fragment: str,
    mock_session: MagicMock,
    valid_registration_payload: dict[str, Any],
) -> None:
    valid_registration_payload["password"] = password

    with pytest.raises(ValidationError) as exc_info:
        register_user(valid_registration_payload, session=mock_session)

    err = exc_info.value
    assert err.status_code == 400
    assert err.details is not None
    assert any(expected_fragment in msg for msg in err.details["password"])
    mock_session.add.assert_not_called()


# --------------------------------------------------------------------------
# Failure: invalid input
# --------------------------------------------------------------------------


@pytest.mark.parametrize("missing_field", ["email", "password", "full_name", "role"])
def test_missing_required_field_is_rejected(
    missing_field: str, mock_session: MagicMock, valid_registration_payload: dict[str, Any]
) -> None:
    valid_registration_payload.pop(missing_field)

    with pytest.raises(ValidationError) as exc_info:
        register_user(valid_registration_payload, session=mock_session)

    assert exc_info.value.status_code == 400
    assert missing_field in (exc_info.value.details or {})
    mock_session.add.assert_not_called()


@pytest.mark.parametrize(
    "bad_email", ["not-an-email", "missing@tld", "@example.com", "a b@example.com"]
)
def test_invalid_email_format_is_rejected(
    bad_email: str, mock_session: MagicMock, valid_registration_payload: dict[str, Any]
) -> None:
    valid_registration_payload["email"] = bad_email

    with pytest.raises(ValidationError) as exc_info:
        register_user(valid_registration_payload, session=mock_session)

    assert "email" in (exc_info.value.details or {})


def test_unknown_role_is_rejected(
    mock_session: MagicMock, valid_registration_payload: dict[str, Any]
) -> None:
    valid_registration_payload["role"] = "superuser"

    with pytest.raises(ValidationError) as exc_info:
        register_user(valid_registration_payload, session=mock_session)

    assert "role" in (exc_info.value.details or {})


@pytest.mark.parametrize("payload", [None, [], "string", 42])
def test_non_object_body_is_rejected(payload: Any, mock_session: MagicMock) -> None:
    with pytest.raises(ValidationError) as exc_info:
        register_user(payload, session=mock_session)
    assert exc_info.value.status_code == 400


# --------------------------------------------------------------------------
# Failure: duplicate email
# --------------------------------------------------------------------------


def test_duplicate_email_raises_conflict(
    mock_session: MagicMock, make_user, valid_registration_payload: dict[str, Any]
) -> None:
    mock_session.scalar.return_value = make_user(email="new.user@example.com")

    with pytest.raises(ConflictError) as exc_info:
        register_user(valid_registration_payload, session=mock_session)

    assert exc_info.value.status_code == 409
    assert exc_info.value.error_code == "conflict"
    mock_session.add.assert_not_called()
    mock_session.commit.assert_not_called()


def test_duplicate_email_lookup_is_case_insensitive(
    mock_session: MagicMock, make_user, valid_registration_payload: dict[str, Any]
) -> None:
    """The lookup must use the normalised (lower-cased) email."""
    mock_session.scalar.return_value = make_user(email="new.user@example.com")
    valid_registration_payload["email"] = "NEW.USER@EXAMPLE.COM"

    with pytest.raises(ConflictError):
        register_user(valid_registration_payload, session=mock_session)

    stmt = mock_session.scalar.call_args.args[0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "new.user@example.com" in compiled
    assert "NEW.USER" not in compiled


def test_race_on_unique_index_is_translated_to_conflict(
    mock_session: MagicMock, valid_registration_payload: dict[str, Any]
) -> None:
    """Pre-check passes, but the DB unique constraint fires on commit."""
    mock_session.commit.side_effect = IntegrityError("INSERT ...", {}, Exception("duplicate key"))

    with pytest.raises(ConflictError) as exc_info:
        register_user(valid_registration_payload, session=mock_session)

    assert exc_info.value.status_code == 409
    mock_session.rollback.assert_called_once()
